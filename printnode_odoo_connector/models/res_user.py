# -*- coding: utf-8 -*-
from odoo import models, fields, _


class User(models.Model):
    """ User entity. Add 'Default Printer' field (no restrictions).
    """
    _inherit = 'res.users'

    printnode_auto_print = fields.Boolean(string='Enable Direct Printing',default=False)
    printnode_printer_id = fields.Many2one('printnode.printer.vts',string='Default Printer', domain=[('status', '=', 'online')],)
    label_printer_id = fields.Many2one('printnode.printer.vts',string='Shipping Label Printer', domain=[('status', '=', 'online')],)


    def get_printer(self, report_id):
        self.ensure_one()

        report_setting = self.env['printnode.rule'].search([('report_id', '=', report_id),('active','=',True)], limit=1)

        if report_setting.printer_id:
            return report_setting.printer_id

        printer = (self.printnode_printer_id or self.env.company.printnode_printer_id)
        return printer

    def get_label_printer(self, carrier_id=None):
        company = self.env.company

        delivery_carrier_printer = carrier_id.printer_id if carrier_id else None
        deliver_carrier_paper = carrier_id.label_paper_format if carrier_id else None
        total_copies = carrier_id.total_copies

        printer = (delivery_carrier_printer or self.label_printer_id or company.label_printer_id)
        paper = (deliver_carrier_paper or self.env.company.label_paper_id)
        return printer,paper,total_copies





