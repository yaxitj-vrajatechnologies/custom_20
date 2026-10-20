# -*- coding: utf-8 -*-
from odoo import models, fields


class InvoiceBill(models.Model):
    _name = 'qbo.bill.ca.map.vts'

    quickbook_instance_id = fields.Many2one('quickbooks.connect', string="QuickBooks Instance")
    quickbook_bill_id = fields.Char(string="Bill ID")
    quickbook_bill_number = fields.Char(string="Bill Number")
    partner_id = fields.Many2one('res.partner', string="Vendor")
    bill_id = fields.Many2one('account.move', string="Bill")
    company_id = fields.Many2one('res.company', string="Company", default=lambda self: self.env.user.company_id)
    qbo_response = fields.Text(string="JSON Body")

    def vendor_bill_mapping_view(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Quickbooks Vendor Bills',
            'res_model': 'qbo.bill.ca.map.vts',
            'view_mode': 'form',
            'view_id': self.env.ref('quickbooks_odoo_connector_canada.view_qkb_vendor_bill_ca_form').id,
            'res_id': self.id,
            'target': 'current'}

