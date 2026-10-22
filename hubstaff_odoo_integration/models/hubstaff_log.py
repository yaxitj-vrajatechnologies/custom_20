from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)


class HubstaffLog(models.Model):
    _name = 'hubstaff.log'
    _description = 'Hubstaff Log'
    _order = 'id DESC'

    name = fields.Char(string='Log Reference', readonly=True)
    process_type = fields.Selection(
        [('import', 'Import'), ('export', 'Export'), ('delete', 'Delete')],
        string="Process Type", help="Type of operation performed for this log (Import, Export, or Delete)."
    )

    process_name = fields.Selection(
        [('project', 'Project'), ('task', 'Task'),('task_entry', 'Task Entries'), ('user', 'User'),('token','Token')],
        string="Process Name",
    )

    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Company',
        default=lambda self: self.env.user.company_id.id, help="Company for which this log entry was created."
    )
    instance_id = fields.Many2one(
        comodel_name='hubstaff.instance.integration',
        string='Hubstaff Instance',
        help="Hubstaff instance related to this log entry.",
        ondelete='cascade'
    )
    log_line_ids = fields.One2many(
        comodel_name="hubstaff.log.line",
        inverse_name="log_id",
        string="Log Lines", help="Detailed log lines describing each step or message of this operation."
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if isinstance(vals, dict) and not vals.get('name'):
                company = self.env['res.company'].browse(
                    self.env.context.get('company_id', self.env.user.company_id.id)
                )
                seq_name = self.with_context(company_id=company.id).env['ir.sequence'].next_by_code(
                    'hubstaff.log') or '/'
                vals['name'] = seq_name
        return super().create(vals_list)


class HubstaffLogLine(models.Model):
    _name = 'hubstaff.log.line'
    _description = 'Hubstaff Log Line'
    _order = 'id DESC'

    message = fields.Text(string="Message")
    log_id = fields.Many2one(
        comodel_name='hubstaff.log',
        string='Parent Log', required=True, ondelete='cascade')
    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Company',
        default=lambda self: self.env.user.company_id.id
    )

    api_request = fields.Text(string="API Request")
    api_response = fields.Text(string="API Response")

