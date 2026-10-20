from odoo import models, fields, api
import pprint


class QuickbooksLog(models.Model):
    _name = 'quickbooks.log.vts'
    _inherit = ['mail.thread']
    _description = 'Quickbooks Log'
    _order = 'id DESC'

    name = fields.Char(string='Name')
    quickbooks_operation_name = fields.Selection(selection=[('customer', 'Customer'),
                                                         ('account', 'Account'),
                                                         ('taxes', 'Taxes'),
                                                         ('payment_term', 'Payment Term'),
                                                         ('vendor','Vendor'),
                                                         ('payment_method','Payment Method')],
                                              string="Process Name")
    quickbooks_operation_type = fields.Selection(selection=[('export', 'Export'),('import', 'Import')], string="Process Type")
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.user.company_id)
    qkb_instance_id = fields.Many2one('quickbooks.connect', string='Quickbooks Instance',help='Select Instance Id')
    quickbooks_operation_line_ids = fields.One2many("quickbooks.log.vts.line", "quickbooks_operation_id",
                                                 string="Operation",ondelete='cascade')
    quickbooks_operation_message = fields.Char(string="Message")
    create_date = fields.Datetime(string='Created on')

    @api.model_create_multi
    def create(self, vals_list):
        """
        In this method auto generated sequence added in log name.
        """
        for vals in vals_list:
            sequence = self.env.ref("quickbooks_common_connector_vts.seq_quickbooks_log")
            name = sequence and sequence.next_by_id() or '/'
            company_id = self._context.get('company_id', self.env.user.company_id.id)
            if type(vals) == dict:
                vals.update({'name': name, 'company_id': company_id})
        return super(QuickbooksLog, self).create(vals_list)

    def generate_quickbooks_logs(self, quickbooks_operation_name, quickbooks_operation_type, instance=None, quickbooks_operation_message=None):
        """
        From this method quickbooks log's record will create.
        """
        log_id = self.create({
            'quickbooks_operation_name': quickbooks_operation_name,
            'quickbooks_operation_type': quickbooks_operation_type,
            'qkb_instance_id': instance,
            'quickbooks_operation_message': quickbooks_operation_message,
        })
        return log_id


class QuickbooksLogLine(models.Model):
    _name = 'quickbooks.log.vts.line'
    _rec_name = 'quickbooks_operation_id'
    _description = 'Quickbooks Details Line'

    _order = 'id DESC'

    quickbooks_operation_id = fields.Many2one('quickbooks.log.vts', string='Process')
    quickbooks_operation_name = fields.Selection(selection=[('customer', 'Customer'),
                                                         ('account', 'Account'),
                                                         ('taxes', 'Taxes'),
                                                         ('payment_term', 'Payment'),('vendor','Vendor'),
                                                         ('payment_method','Payment Method')],
                                              string="Process Name")
    quickbooks_operation_type = fields.Selection([('export', 'Export'),
                                               ('import', 'Import')], string="Process Type")
    company_id = fields.Many2one("res.company", "Company", default=lambda self: self.env.user.company_id)
    qkb_instance_id = fields.Many2one('quickbooks.connect', string='Instance',
                                  help='Select Instance Id')
    process_request_message = fields.Char("Request Message")
    process_response_message = fields.Text("Response Message")
    fault_operation = fields.Boolean("Fault Process", default=False)
    quickbooks_operation_message = fields.Char("Message")
    create_date = fields.Datetime(string='Created on')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if type(vals) == dict:
                quickbooks_operation_id = vals.get('quickbooks_operation_id')
                operation = quickbooks_operation_id and self.env['quickbooks.log.vts'].browse(quickbooks_operation_id).id or False
                company_id = quickbooks_operation_id and self.env['quickbooks.log.vts'].browse(quickbooks_operation_id) and quickbooks_operation_id and self.env['quickbooks.log.vts'].browse(quickbooks_operation_id).company_id.id or self.env.user.company_id.id
                vals.update({'company_id': company_id})
        return super(QuickbooksLogLine, self).create(vals_list)

    def generate_quickbooks_process_line(self, quickbooks_operation_name, quickbooks_operation_type, instance=None,
                                      quickbooks_operation_message=None, process_request_message=None, process_response_message=None,
                                      log_id=None, fault_operation=False):
        """
        From this method quickbooks log line's record will create.
        """
        vals = {}
        log_line_id = vals.update({
            'quickbooks_operation_name': quickbooks_operation_name,
            'quickbooks_operation_type': quickbooks_operation_type,
            'qkb_instance_id': instance,
            'quickbooks_operation_message': quickbooks_operation_message,
            'process_request_message': pprint.pformat(process_request_message) if process_request_message else False,
            'process_response_message': pprint.pformat(process_response_message) if process_response_message else False,
            'quickbooks_operation_id': log_id and log_id.id,
            'fault_operation': fault_operation
        })

        self.create(vals)
        return log_line_id

    def unlink(self):
        parent_logs = self.mapped('quickbooks_operation_id')
        res = super(QuickbooksLogLine, self).unlink()
        for log in parent_logs:
            if not log.quickbooks_operation_line_ids:
                log.unlink()
        return res
