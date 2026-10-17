from odoo import models, fields, api
import pprint


class XeroLog(models.Model):
    _name = 'xero.log.vts'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Xero Log'
    _order = 'id DESC'

    name = fields.Char(string='Name')
    xero_operation_name = fields.Selection(selection=[('partner', 'Partner'),('account', 'Account'),('product','Product'),('taxes', 'Taxes'),('invoice','Invoice'),
                                                      ('payment', 'Payment'),('tracking_category','Tracking Category'),('contact_group','Contact Group'),
                                                      ('purchase_order','Purchase Order'),('credit_note','Credit Note'),('pre_payment','Pre Payment'),('over_payment','Over Payment')], string="Process Name")
    xero_operation_type = fields.Selection(selection=[('export', 'Export'),('import', 'Import'),('delete','Delete')], string="Process Type")
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.user.company_id)
    xero_instance_id = fields.Many2one('xero.connect', string='Xero Instance',help='Select Instance Id')
    xero_operation_line_ids = fields.One2many("xero.log.vts.line", "xero_operation_id", string="Operation",ondelete='cascade')
    xero_operation_message = fields.Char(string="Message")
    create_date = fields.Datetime(string='Created on')

    @api.model_create_multi
    def create(self, vals_list):
        """
        In this method auto generated sequence added in log name.
        """
        for vals in vals_list:
            sequence = self.env.ref("xero_odoo_integration.xero_log_sequence")
            name = sequence and sequence.next_by_id() or '/'
            company_id = self._context.get('company_id', self.env.user.company_id.id)
            if type(vals) == dict:
                vals.update({'name': name, 'company_id': company_id})
        return super(XeroLog, self).create(vals_list)

    def generate_xero_logs(self, xero_operation_name, xero_operation_type, instance=None, xero_operation_message=None):
        """
        This method creates a log for xero operations
        """
        log_id = self.create({
            'xero_operation_name': xero_operation_name,
            'xero_operation_type': xero_operation_type,
            'xero_instance_id': instance,
            'xero_operation_message': xero_operation_message,
        })
        return log_id

    def unlink(self):
        """
        This method is used for unlink appropriate log and logline both from both log model
        """
        for selected_main_log in self:
            if selected_main_log.xero_operation_line_ids:
                selected_main_log.xero_operation_line_ids.unlink()
        return super(XeroLog, self).unlink()


class XeroLogLine(models.Model):
    _name = 'xero.log.vts.line'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _rec_name = 'xero_operation_id'
    _description = 'Xero Details Line'
    _order = 'id DESC'

    xero_operation_id = fields.Many2one('xero.log.vts', string='Process')
    xero_operation_name = fields.Selection(selection=[('partner', 'Partner'),
                                                         ('account', 'Account'),('tracking_category','Tracking Category'),
                                                      ('taxes', 'Taxes'),('product', 'Product'),('invoice', 'Invoice'),
                                                         ('payment', 'Payment'),('vendor','Vendor'),('payment_method','Payment Method'),
                                                      ('contact_group','Contact Group'),('purchase_order','Purchase Order'),
                                                      ('credit_note','Credit Note'),('pre_payment','Pre Payment'),('over_payment','Over Payment')],string="Process Name")
    xero_operation_type = fields.Selection([('export', 'Export'),('import', 'Import'),('delete',"Delete")], string="Process Type")
    company_id = fields.Many2one("res.company", "Company", default=lambda self: self.env.user.company_id)
    xero_instance_id = fields.Many2one('xero.connect', string='Instance',help='Select Instance Id')
    process_request_message = fields.Char("Request Message")
    process_response_message = fields.Text("Response Message")
    fault_operation = fields.Boolean("Fault Process", default=False)
    xero_operation_message = fields.Char("Message")
    create_date = fields.Datetime(string='Created on')

    def generate_xero_process_line(self, xero_operation_name, xero_operation_type, instance=None,
                                      xero_operation_message=None, process_request_message=None, process_response_message=None,
                                      log_id=None, fault_operation=False):
        """
        This Method Creates a Log Line for Xero Operations.
        """
        vals = {}
        log_line_id = vals.update({
            'xero_operation_name': xero_operation_name,
            'xero_operation_type': xero_operation_type,
            'xero_instance_id': instance,
            'xero_operation_message': xero_operation_message,
            'process_request_message': pprint.pformat(process_request_message) if process_request_message else False,
            'process_response_message': pprint.pformat(process_response_message) if process_response_message else False,
            'xero_operation_id': log_id and log_id.id,
            'fault_operation': fault_operation
        })

        self.create(vals)
        return log_line_id

    def unlink(self):

        logs = self.mapped('xero_operation_id')
        res = super(XeroLogLine, self).unlink()

        for log in logs:
            if not log.xero_operation_line_ids:
                log.unlink()

        return res
