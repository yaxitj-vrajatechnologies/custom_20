from odoo import models, fields, api, _
import logging

_logger = logging.getLogger(__name__)
from odoo.tools import html2plaintext


class ProjectTask(models.Model):
    _inherit = 'project.task'

    hubstaff_task_id = fields.Char(
        string="Hubstaff Task ID",
        index=True, copy=False,
        help="Unique identifier of this task in Hubstaff. This value is automatically set when the task is synchronized with Hubstaff."
    )
    hubstaff_instance_id = fields.Many2one(
        'hubstaff.instance.integration', string="Hubstaff Instance", copy=False,
        help="Hubstaff instance through which this task is connected and synchronized with Hubstaff."
    )

    def write(self, vals):
        res = super().write(vals)
        context = dict(self.env.context) or {}
        for rec in self:
            if ('name' in vals) or ('active' in vals) or ('user_ids' in vals):
                if rec.hubstaff_task_id and rec.hubstaff_instance_id.is_update_task and not context.get(
                        'update_task_odoo') and not context.get("import_project"):
                    rec.with_context(context).update_in_hubstaff(vals)
        return res

    # ---------------------------------------------------------
    # UPDATE TASK IN HUBSTAFF (PUT)
    # ---------------------------------------------------------
    def update_in_hubstaff(self, vals):
        """Update task in Hubstaff using lock_version"""
        self.ensure_one()

        instance = self.hubstaff_instance_id
        if not instance:
            return False

        context = dict(self.env.context or {})
        context.update({"process_name": "task"})
        instance = instance.with_context(context)

        lock_version = self.with_context(context)._get_task_lock_version(instance)

        if not lock_version:
            instance._create_log(
                message=f"Skipping update, missing lock_version for task: {self.name}",
                log_type='export'
            )
            return False

        payload = {
            "lock_version": int(lock_version),
            "summary": vals.get('name') or self.name,
            "status": "completed" if vals.get('active') is False else "active",
            "assignee_ids": self._prepare_hubstaff_assignee(instance),
        }

        try:
            data, response = instance._hubstaff_api_call(
                method="PUT",
                endpoint=f"/v2/tasks/{self.hubstaff_task_id}",
                payload=payload,
            )

            if response and response.status_code in (200, 201):
                instance._create_log(
                    message=f"Hubstaff task updated successfully: {self.name}",
                    log_type='export'
                )
                return True

            instance._create_log(
                message=f"Hubstaff task update failed: {response.text}",
                log_type='export'
            )
            return False

        except Exception as e:
            instance._create_log(
                message=f"Hubstaff task exception: {str(e)}",
                log_type='export',
                api_response=str(e)
            )
            return False

    # ---------------------------------------------------------
    # GET TASK LOCK VERSION (GET)
    # ---------------------------------------------------------
    def _get_task_lock_version(self, instance):
        """Fetch task lock_version from Hubstaff"""

        try:
            task_data, response = instance._hubstaff_api_call(
                method="GET",
                endpoint=f"/v2/tasks/{self.hubstaff_task_id}",
            )

            if response and response.status_code == 200:
                return task_data.get("task", {}).get("lock_version")

            return False

        except Exception as e:
            instance._create_log(
                message=f"GET Task exception: {str(e)}",
                log_type='export',
                api_response=str(e)
            )
            return False

    # ---------------------------------------------------------
    # PREPARE ASSIGNEES
    # ---------------------------------------------------------
    def _prepare_hubstaff_assignee(self, instance):
        """Prepare assignee list using Hubstaff user IDs"""

        if not self.user_ids:
            instance._create_log(
                message=f"No users assigned to task: {self.name}",
                log_type='export'
            )
            return []

        valid_users = self.user_ids.filtered(lambda u: u.hubstaff_user_id)
        return valid_users.mapped(lambda u: int(u.hubstaff_user_id))

    # ---------------------------------------------------------
    # MANUAL UPDATE BUTTON (GET)
    # ---------------------------------------------------------
    def action_update_hubstaff_task(self):
        self.ensure_one()

        instance = self.hubstaff_instance_id
        context = dict(self.env.context or {})

        context.update({
            "update_task_odoo": True,
            "process_name": "task",
        })

        if not instance or not self.hubstaff_task_id:
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": _("Task Sync Warning"),
                    "message": _("Hubstaff instance or Task ID is missing for: %s") % self.name,
                    "type": "warning",
                    "sticky": False,
                },
            }

        main_log_id = instance.with_context(context)._create_log(
            log_type='import',
            force_new_log=True
        )

        context.update({
            "import_log_id": main_log_id,
            "export_log_id": main_log_id,
        })

        instance = instance.with_context(context)

        try:
            hs_task_data, response = instance._hubstaff_api_call(
                method="GET",
                endpoint=f"/v2/tasks/{self.hubstaff_task_id}",
            )

            if not response or response.status_code != 200:
                instance._create_log(
                    message=f"Failed to fetch Hubstaff task: {self.name}",
                    log_type='import'
                )
                return {"type": "ir.actions.client", "tag": "reload"}

            hs_task = hs_task_data.get("task", {})

            self.with_context(context).write({
                "name": hs_task.get("summary")
            })

            assignees = hs_task.get("assignee_ids") or []

            matched_users = self.env['res.users'].search([
                ('hubstaff_user_id', 'in', [str(i) for i in assignees])
            ])

            if matched_users:
                self.with_context(context).write({
                    "user_ids": [(6, 0, matched_users.ids)]
                })

            instance._create_log(
                message=f"Hubstaff task updated successfully: {self.name}",
                log_type='import'
            )

            return {"type": "ir.actions.client", "tag": "reload"}

        except Exception as e:
            instance._create_log(
                message=f"Unexpected error: {str(e)}",
                log_type='import',
                api_response = str(e)

            )
            return {"type": "ir.actions.client", "tag": "reload"}
