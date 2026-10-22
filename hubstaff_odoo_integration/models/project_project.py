from odoo import models, fields, api
import logging
from odoo.tools import html2plaintext

_logger = logging.getLogger(__name__)


class ProjectProject(models.Model):
    _inherit = 'project.project'

    hubstaff_project_id = fields.Char(string="Hubstaff Project ID", readonly=True, store=True, copy=False,
                                      help="Unique identifier of this project in Hubstaff. This value is automatically set when the project is synchronized with Hubstaff.")
    hubstaff_organization_id = fields.Char(string="Hubstaff Organization ID", readonly=True, store=True, copy=False,
                                           help="Unique identifier of the Hubstaff organization to which this project belongs.")

    hubstaff_instance_id = fields.Many2one(
        'hubstaff.instance.integration', string="Hubstaff Instance", copy=False,
        help="Hubstaff instance through which this project is connected and synchronized with Hubstaff."
    )

    def write(self, vals):
        context = dict(self.env.context) or {}
        for rec in self:
            if (
                    ('name' in vals or 'description' in vals or 'active' in vals or 'user_id' in vals)
                    and rec.hubstaff_project_id
                    and rec.hubstaff_instance_id.is_update_project
                    and not context.get('update_project_odoo')
                    and not context.get('import_project')
            ):
                rec.update_in_hubstaff(vals)
        return super().write(vals)

    def update_in_hubstaff(self, vals):
        instance = self.hubstaff_instance_id
        if not instance:
            return

        context = dict(self.env.context or {})
        context.update({"process_name": "project"})
        instance = instance.with_context(context)

        try:
            # -------------------------------------------------
            # Update Project Basic Data
            # -------------------------------------------------
            if {'name', 'description', 'active'}.intersection(vals.keys()):

                payload = {
                    "name": vals.get('name', self.name),
                    "description": html2plaintext(
                        vals.get('description', self.description)
                    ) or "",
                    "status": "archived" if vals.get('active') is False else "active",
                }

                data, response = instance._hubstaff_api_call(
                    method="PUT",
                    endpoint=f"/v2/projects/{self.hubstaff_project_id}",
                    payload=payload,
                )

                if not response or response.status_code not in (200, 201):
                    instance._create_log(
                        message=f"Project update failed: {response.text if response else 'No response'}",
                        log_type="export",
                    )
                    return

                instance._create_log(
                    message=f"Project updated successfully: {self.name}",
                    log_type="export",
                )

            # -------------------------------------------------
            # Update Project Manager
            # -------------------------------------------------
            if 'user_id' in vals and vals.get('user_id'):

                new_manager = self.env['res.users'].browse(vals['user_id'])

                if new_manager and new_manager.hubstaff_user_id:

                    members_payload = {
                        "members": [{
                            "user_id": int(new_manager.hubstaff_user_id),
                            "role": "manager"
                        }]
                    }

                    data, response = instance._hubstaff_api_call(
                        method="PUT",
                        endpoint=f"/v2/projects/{self.hubstaff_project_id}/update_members",
                        payload=members_payload,
                    )

                    if not response or response.status_code not in (200, 201):
                        instance._create_log(
                            message=f"Project manager update failed: {response.text if response else 'No response'}",
                            log_type="export",
                        )
                        return

                    instance._create_log(
                        message=f"Project manager updated successfully: {self.name}",
                        log_type="export",
                    )

        except Exception as e:
            instance._create_log(
                message=f"Unexpected error syncing project {self.name}: {str(e)}",
                log_type="export",
            )

    def action_update_hubstaff_project(self):
        self.ensure_one()

        instance = self.hubstaff_instance_id

        context = dict(self.env.context or {})
        context.update({
            "update_project_odoo": True,
            "process_name": "project"
        })

        if not instance or not self.hubstaff_project_id:
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": "Hubstaff Sync Warning",
                    "message": f"Hubstaff instance or Project ID is missing for: {self.name}.",
                    "type": "warning",
                    "sticky": False,
                },
            }

        instance = instance.with_context(context)

        try:
            # --------------------------------------------------
            # Create ONLY ONE main log
            # --------------------------------------------------
            main_log_id = instance._create_log(
                log_type='import',
                force_new_log=True
            )

            instance = instance.with_context(import_log_id=main_log_id)

            # --------------------------------------------------
            # Fetch project from Hubstaff
            # --------------------------------------------------
            response_data, raw_response = instance._hubstaff_api_call(
                method="GET",
                endpoint=f"/v2/projects/{self.hubstaff_project_id}",
            )

            if not response_data:
                instance._create_log(
                    message=f"Failed to fetch project from Hubstaff for: {self.name}",
                    log_type='import'
                )
                return {
                    "type": "ir.actions.client",
                    "tag": "display_notification",
                    "params": {
                        "title": "Hubstaff Sync Warning",
                        "message": f"Failed to fetch project from Hubstaff for: {self.name}.",
                        "type": "warning",
                    },
                }

            hs_project = response_data.get("project", {})

            if not hs_project:
                instance._create_log(
                    message=f"No project data returned from Hubstaff for: {self.name}",
                    log_type='import'
                )
                return {
                    "type": "ir.actions.client",
                    "tag": "display_notification",
                    "params": {
                        "title": "Hubstaff Sync Warning",
                        "message": f"No project data returned from Hubstaff for: {self.name}.",
                        "type": "warning",
                    },
                }

            # --------------------------------------------------
            # Update manager
            # --------------------------------------------------
            manager_user = self.with_context(
                import_log_id=main_log_id,
                process_name="project"
            )._update_hubstaff_project_manager(instance)

            # --------------------------------------------------
            # Prepare values
            # --------------------------------------------------
            vals = {
                "name": hs_project.get("name"),
                "description": hs_project.get("description"),
            }

            if manager_user:
                vals["user_id"] = manager_user.id

            vals = {k: v for k, v in vals.items() if v is not None}

            self.with_context(
                import_log_id=main_log_id,
                update_project_odoo=True
            ).write(vals)

            # --------------------------------------------------
            # Success log line
            # --------------------------------------------------
            instance._create_log(
                message=f"Hubstaff project updated successfully: {self.name}",
                log_type='import'
            )

            return {
                "type": "ir.actions.client",
                "tag": "reload",
            }

        except Exception as e:
            instance._create_log(
                message=f"Failed to update Hubstaff project: {self.name}. Error: {str(e)}",
                log_type='import',
                api_response=str(e)
            )

            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": "Hubstaff Sync Warning",
                    "message": f"Error while connecting Hubstaff for: {self.name}.",
                    "type": "warning",
                },
            }

    def _update_hubstaff_project_manager(self, instance):
        """Fetch Hubstaff project members and return manager user"""

        try:
            # --------------------------------------------------
            # Fetch all project members using pagination
            # --------------------------------------------------
            members = instance._hubstaff_paginated_fetch(
                endpoint=f"/v2/projects/{self.hubstaff_project_id}/members",
                data_key="members"
            )

            if not members:
                return False

            manager_user_id = False

            for mem in members:
                if mem.get("membership_role") == "manager" and mem.get("membership_status") == "active":
                    manager_user_id = str(mem.get("user_id"))
                    break

            if not manager_user_id:
                return False

            user = self.env['res.users'].search(
                [("hubstaff_user_id", "=", manager_user_id)],
                limit=1
            )

            return user if user else False

        except Exception as e:
            _logger.exception("Error while syncing Hubstaff project members for %s", self.name)
            instance._create_log(
                message=f"Error while syncing Hubstaff project members for %s: {self.name}. Error: {str(e)}",
                log_type='import',
                api_response=str(e)
            )
            return False

