from odoo import models, fields, api, _
from odoo.exceptions import UserError
from odoo.tools import html2plaintext
from odoo.tools import html_sanitize
from markupsafe import Markup, escape
import logging

_logger = logging.getLogger(__name__)


class HubstaffExportProjectWizard(models.TransientModel):
    _name = 'hubstaff.export.project.wizard'
    _description = 'Export Projects to Hubstaff'

    instance_id = fields.Many2one('hubstaff.instance.integration', string='Hubstaff Instance', required=True,
                                  help="Select the Hubstaff instance to which the selected projects will be exported.")

    def action_export_projects(self):
        self.ensure_one()
        instance = self.instance_id
        context = dict(self.env.context or {})

        # ----------------------------------
        # Determine process type
        # ----------------------------------
        process_name = "task" if context.get('task_export') else "project"
        context.update({"process_name": process_name, "manual_export": True})
        instance = instance.with_context(context)

        main_log_id = instance._create_log(
            log_type="export",
            force_new_log=True
        )
        context.update({"export_log_id": main_log_id})
        instance = instance.with_context(context)

        # ----------------------------------
        # Export tasks or projects
        # ----------------------------------
        if context.get('task_export'):
            task_ids = self.env[context.get('default_res_model')].browse(
                context.get('active_ids') or []
            )
            context.update({"task_export_manually": True})

            if task_ids.filtered(lambda t: t.project_id.hubstaff_project_id):
                for task in task_ids.filtered(lambda t: t.project_id.hubstaff_project_id):
                    self.with_context(context)._export_single_task(task, task.project_id, instance)
            else:
                context.update({
                    "process_name": "project",
                    "project_export_manually": True
                })
                for project in task_ids.mapped('project_id'):
                    self.with_context(context)._export_single_project(project, instance)
        else:
            project_ids = self.env[context.get('default_res_model')].browse(
                context.get('active_ids') or []
            )
            context.update({"project_export_manually": True})
            for project in project_ids:
                self.with_context(context)._export_single_project(project, instance)

        return {
            "type": "ir.actions.client",
            "tag": "reload",
        }

    def _validate_project_for_export(self, project, instance):
        errors = []

        if not project.name:
            errors.append("Project name missing")

        if not project.user_id or not project.user_id.hubstaff_user_id:
            errors.append("Project manager not mapped with Hubstaff user")

        if errors:
            error_msg = ", ".join(errors)

            instance._create_log(
                message=f"{project.name or 'Unknown'} → Export skipped. Missing: {error_msg}",
                log_type="export",
            )

            self.with_context(response={"error": error_msg}).create_schedule_activity(project, instance)
            return False

        return True

    def _validate_task_for_export(self, task, project, instance):
        errors = []

        if not task.name:
            errors.append("Task name missing")

        if not project.hubstaff_project_id:
            errors.append("Project not exported to Hubstaff")

        if not task.user_ids or not task.user_ids[0].hubstaff_user_id:
            errors.append("Task assignee not mapped with Hubstaff")

        if errors:
            error_msg = ", ".join(errors)

            instance._create_log(
                message=f"{task.name or 'Unknown'} → Export skipped. Missing: {error_msg}",
                log_type="export",
            )

            self.with_context(response={"error": error_msg}).create_schedule_activity(project, instance, task=task)

            return False

        return True

    def _export_single_project(self, project, instance):
        instance = instance.with_context(self.env.context)
        context = self.env.context or {}

        if project.hubstaff_project_id:
            instance._create_log(
                message=f"{project.name} → Already exported, skipped.",
                log_type="export",
            )
            return

        if not self._validate_project_for_export(project, instance):
            return

        endpoint = f"/v2/organizations/{instance.hubstaff_organization_id}/projects"
        payload = {
            "name": project.name,
            "description": html2plaintext(project.description) or "",
            "metadata": [{"key": "odoo_project_id", "value": str(project.id)}],
            "members": self._prepare_project_members(project),
        }

        try:
            data, response = instance._hubstaff_api_call(
                method="POST",
                endpoint=endpoint,
                payload=payload,
            )

            hs_id = data.get("project", {}).get("id")
            if hs_id:
                project.write({
                    "hubstaff_project_id": str(hs_id),
                    "hubstaff_instance_id": instance.id,
                    "hubstaff_organization_id": instance.hubstaff_organization_id
                })
                instance._create_log(
                    message=f"{project.name} → Exported successfully.",
                    log_type="export",
                )
                # Export tasks if manual export
                if context.get('task_export_manually') or context.get('project_export_manually'):
                    self.with_context(context)._export_project_tasks(project, instance)
            else:
                error_msg = "No project ID returned."
                instance._create_log(
                    message=f"{project.name} → {error_msg}",
                    log_type="export",
                )
                self.with_context(response={"error": error_msg}) \
                    .create_schedule_activity(project, instance)

        except Exception as e:
            error_msg = str(e) or "Unexpected error during export"
            instance._create_log(
                message=f"{project.name} → Exception: {error_msg}",
                log_type="export",
            )
            self.with_context(response={"error": error_msg}).create_schedule_activity(project, instance)

    def _prepare_project_members(self, project):
        """Prepare Hubstaff members dynamically using mapped() + filtered(),
           exclude manager, and assign remaining users with role='user'
        """
        members = []

        manager_id = project.user_id.hubstaff_user_id if project.user_id else False

        if manager_id:
            members.append({
                "user_id": int(manager_id),
                "role": "manager"
            })

        task_users = project.task_ids.mapped('user_ids').filtered(
            lambda user: user.hubstaff_user_id and user.hubstaff_user_id != manager_id
        )

        for user in task_users:
            members.append({
                "user_id": int(user.hubstaff_user_id),
                "role": "user"
            })

        return members

    def _export_project_tasks(self, project, instance):
        """Loop tasks of 1 project"""
        tasks = self.env['project.task'].search([('project_id', '=', project.id)])
        for task in tasks:
            self._export_single_task(task, project, instance)

    def _export_single_task(self, task, project, instance):
        instance = instance.with_context(self.env.context)

        if task.hubstaff_task_id:
            instance._create_log(
                message=f"{task.name} → Already exported, skipped.",
                log_type="export",
            )
            return

        if not self._validate_task_for_export(task, project, instance):
            return

        endpoint = f"/v2/projects/{project.hubstaff_project_id}/tasks"
        payload = {
            "name": task.name,
            "summary": html2plaintext(task.name or ''),
            "status": "active",
            "assignee_id": task.user_ids[0].hubstaff_user_id if task.user_ids else False
        }

        try:
            data, response = instance._hubstaff_api_call(
                method="POST",
                endpoint=endpoint,
                payload=payload,
            )

            hs_task_id = data.get("task", {}).get("id")
            if hs_task_id:
                task.write({
                    "hubstaff_task_id": str(hs_task_id),
                    "hubstaff_instance_id": instance.id
                })
                instance._create_log(
                    message=f"{task.name} → Exported successfully.",
                    log_type="export",
                )

            else:
                error_msg = "No task ID returned."
                instance._create_log(
                    message=f"{task.name} → {error_msg}",
                    log_type="export",
                )
                self.with_context(response={"error": error_msg}) \
                    .create_schedule_activity(project, instance, task=task)

        except Exception as e:
            error_msg = str(e) or "Unexpected error during export"
            instance._create_log(
                message=f"{task.name} → Exception: {error_msg}",
                log_type="export",
            )
            self.with_context(response={"error": error_msg}).create_schedule_activity(project, instance, task=task)

    def create_schedule_activity(self, project, instance, task=None):
        """
        Create activity when Hubstaff export fails.
        Activity user comes from instance configuration.
        Handles both project and task failures.
        """

        failure_user = instance.failure_activity_user_id
        if not failure_user:
            return

        context = dict(self.env.context or {})
        error_msg = ""

        if context.get('response'):
            error_msg = context.get('response').get('error', '')

        project_name = escape(project.name or "")
        task_name = escape(task.name or "") if task else ""
        error_msg = escape(error_msg or "")

        if task:
            summary = "Hubstaff Task Export Failed"
            description = (
                f"Task '{task_name}' from project '{project_name}' "
                f"failed to export to Hubstaff."
            )
        else:
            summary = "Hubstaff Project Export Failed"
            description = (
                f"Project '{project_name}' failed to export to Hubstaff."
            )

        body = f"<div>{description}</div>"
        if error_msg:
            body += f"<div><b>Error:</b> {error_msg}</div>"

        body = html_sanitize(Markup(body))

        record = task if task else project
        record.activity_schedule(
            'mail.mail_activity_data_todo',
            summary=summary,
            note=body,
            user_id=failure_user.id,
        )