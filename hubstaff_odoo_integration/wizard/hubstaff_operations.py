from odoo import models, fields, _
from datetime import timedelta
from odoo.exceptions import UserError

IMPORT_OPERATIONS = [
    ("import_project", "Import Project"),
    ("import_task", "Import Tasks"),
    ("import_task_entries", "Import Task Entries"),
]


class HubstaffOperations(models.TransientModel):
    _name = 'hubstaff.operations'
    _description = 'Hubstaff Import Export'

    def _get_default_to_date(self):
        """
        This method is used to to_date for order, product.
        """
        to_date = fields.Datetime.now()
        to_date = fields.Datetime.to_string(to_date)
        return to_date

    def _get_default_from_date_project(self):
        """
        This method is used to set from_date for order.
        """
        context = dict(self.env.context) or {}
        instance_id = context.get('active_id')
        instance_id = self.env['hubstaff.instance.integration'].search([('id', '=', instance_id)], limit=1)
        from_date_order = instance_id.last_project_synced_date if instance_id.last_project_synced_date else fields.Datetime.now() - timedelta(
            30)
        from_date_order = fields.Datetime.to_string(from_date_order)
        return from_date_order

    instance_id = fields.Many2one(
        comodel_name='hubstaff.instance.integration',
        string='Instance',
        default=lambda self: self.env.context.get('active_id'),
        help="Hubstaff instance on which the selected import or export operation will be performed."
    )

    import_operations = fields.Selection(
        selection=IMPORT_OPERATIONS,
        string='Import Operations',
        default='import_project',
        help="Select the type of operation you want to perform, such as importing projects, tasks, users, or exporting data."
    )

    def action_submit(self):
        context = dict(self.env.context or {})

        instance = self.env['hubstaff.instance.integration'].browse(
            context.get('active_id')
        )

        if not instance:
            raise UserError(_("Hubstaff instance not found."))

        if instance.state != 'confirm':
            raise UserError(
                _("Please authenticate the Hubstaff instance before performing this operation.")
            )

        # --------------------------------------------
        # Decide process name
        # --------------------------------------------
        process_map = {
            "import_project": "project",
            "import_task": "task",
            "import_task_entries": "task_entry",
        }
        process_label_map = {
            "import_project": "Projects",
            "import_task": "Tasks",
            "import_task_entries": "Task Entries",
        }

        process_name = process_map.get(self.import_operations)
        process_label = process_label_map.get(self.import_operations, "")

        # --------------------------------------------
        # Prepare context
        # --------------------------------------------
        context.update({
            "import_operations": True,
            "process_name": process_name,
        })

        instance = instance.with_context(context)

        # --------------------------------------------
        # Create main log
        # --------------------------------------------
        main_log_id = instance._create_log(
            log_type="import",
            force_new_log=True
        )

        instance = instance.with_context(import_log_id=main_log_id)

        # --------------------------------------------
        # Run operation
        # --------------------------------------------
        if self.import_operations == "import_project":
            instance._sync_hubstaff_projects()

        elif self.import_operations == "import_task":
            instance._sync_hubstaff_projects()
            instance._sync_hubstaff_tasks()

        elif self.import_operations == "import_task_entries":
            instance._sync_hubstaff_task_entries()
