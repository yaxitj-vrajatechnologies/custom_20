# -*- coding: utf-8 *-*
from odoo import models, fields, api
import pprint


class PrintNodeLog(models.Model):
    _name = 'printnode.log.vts'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'PrintNode Log'
    _order = 'id DESC'

    name = fields.Char(string='Name')
    printnode_opr_name = fields.Selection(selection=[('printer','Printer'),('computer','Computer'),('printer_configuration','Configuration'),
                                                    ('printjob_request','PrintJob')], string="Process Name")
    printnode_opr_type = fields.Selection(selection=[('import', 'Import'),('print_request','Create')], string="Process Type")
    printnode_instance_id = fields.Many2one('printnode.connect', string='PrintNode Instance',ondelete='cascade',help='Selected Instance Id')
    printnode_opr_line_ids = fields.One2many("printnode.log.vts.line", "printnode_opr_id", string="Operation",ondelete='cascade')
    printnode_opr_message = fields.Char(string="Message")
    create_date = fields.Datetime(string='Created on')

    @api.model_create_multi
    def create(self, vals_list):
        """
        In this method auto generated sequence added in log name.
        """
        for vals in vals_list:
            sequence = self.env.ref("printnode_odoo_connector.printnode_log_sequence")
            name = sequence and sequence.next_by_id() or '/'
            # company_id = self._context.get('company_id', self.env.user.company_id.id)
            if type(vals) == dict:
                vals.update({'name': name})
        return super(PrintNodeLog, self).create(vals_list)

    def generate_printnode_logs(self, printnode_opr_name, printnode_opr_type, instance=None, printnode_opr_message=None):
        """
        This method creates a log for PrintNode operations
        """
        log_id = self.create({
            'printnode_opr_name': printnode_opr_name,
            'printnode_opr_type': printnode_opr_type,
            'printnode_instance_id': instance,
            'printnode_opr_message': printnode_opr_message,
        })
        return log_id

    def unlink(self):
        """
        This method is used for unlink appropriate log and logline both from both log model
        """
        for selected_main_log in self:
            if selected_main_log.printnode_opr_line_ids:
                selected_main_log.printnode_opr_line_ids.unlink()
        return super(PrintNodeLog, self).unlink()


class PrintNodeLogLine(models.Model):
    _name = 'printnode.log.vts.line'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _rec_name = 'printnode_opr_id'
    _description = 'PrintNodeDetails Line'
    _order = 'id DESC'

    printnode_opr_id = fields.Many2one('printnode.log.vts', string='Process')
    printnode_opr_name = fields.Selection(selection=[('printer','Printer'),('computer','Computer'),('printer_configuration','Printer Configuration'),('printjob_request','PrintJob'),],string="Process Name")
    printnode_opr_type = fields.Selection([('import', 'Import'),('print_request','Create'),], string="Process Type")
    printnode_instance_id = fields.Many2one('printnode.connect', string='Instance',ondelete='cascade',help='Select Instance Id')
    process_request_message = fields.Char("Request Message")
    process_response_message = fields.Text("Response Message")
    fault_operation = fields.Boolean("Fault Process", default=False)
    printnode_opr_message = fields.Char("Message")
    create_date = fields.Datetime(string='Created on')

    def generate_printnode_process_line(self, printnode_opr_name, printnode_opr_type, instance=None,
                                      printnode_opr_message=None, process_request_message=None, process_response_message=None,
                                      log_id=None, fault_operation=False):
        """
        This Method Creates a Log Line for PrintNode Operations.
        """
        vals = {}
        log_line_id = vals.update({
            'printnode_opr_name': printnode_opr_name,
            'printnode_opr_type': printnode_opr_type,
            'printnode_instance_id': instance,
            'printnode_opr_message': printnode_opr_message,
            'process_request_message': pprint.pformat(process_request_message) if process_request_message else False,
            'process_response_message': pprint.pformat(process_response_message) if process_response_message else False,
            'printnode_opr_id': log_id and log_id.id,
            'fault_operation': fault_operation
        })

        self.create(vals)
        return log_line_id

    def unlink(self):

        logs = self.mapped('printnode_opr_id')
        res = super(PrintNodeLogLine, self).unlink()

        for log in logs:
            if not log.printnode_opr_line_ids:
                log.unlink()

        return res
