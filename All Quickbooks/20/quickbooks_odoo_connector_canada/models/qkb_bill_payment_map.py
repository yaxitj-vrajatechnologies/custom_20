# -*- coding: utf-8 -*-
from odoo import models, fields

class QuickbooksCategoryMapping(models.Model):
    _name = 'qbo.bill.payment.ca.map.vts'
    _description = "QuickBooks Bill Payment Mapping"

    quickbook_instance_id = fields.Many2one('quickbooks.connect', string="QuickBooks Instance")
    quickbook_bill_payment_id = fields.Char(string="Bill ID")
    quickbook_bill_payment_number = fields.Char(string="Bill Number")
    partner_id = fields.Many2one('res.partner', string="Vendor")
    payment_id = fields.Many2one('account.payment', string="Bill Payment")
    company_id = fields.Many2one('res.company', string="Company", default=lambda self: self.env.user.company_id)
    qbo_response = fields.Text(string="JSON Body")

    def bill_payment_mapping_view(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Quickbooks Customer Payment',
            'res_model': 'qbo.bill.payment.ca.map.vts',
            'view_mode': 'form',
            'view_id': self.env.ref('quickbooks_odoo_connector_canada.view_qkb_bill_payment_ca_form').id,
            'res_id': self.id,
            'target': 'current'}
