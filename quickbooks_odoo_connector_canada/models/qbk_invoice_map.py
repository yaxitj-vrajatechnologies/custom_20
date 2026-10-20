# -*- coding: utf-8 -*-
from odoo import models, fields

class QuickbooksInvoiceMapping(models.Model):
    _name = 'qbo.invoice.map.vts'
    _description = "QuickBooks Invoice Mapping"

    quickbook_instance_id = fields.Many2one('quickbooks.connect', string="QuickBooks Instance")
    qbk_invoice_id = fields.Char(string="QuickBooks Invoice ID")
    quickbook_invoice_number = fields.Char(string="Invoice Number")
    customer_id = fields.Many2one('res.partner', string="Customer")
    invoice_id = fields.Many2one('account.move', string="Odoo Invoice")
    company_id = fields.Many2one('res.company', string="Company", default=lambda self: self.env.user.company_id)
    qbo_response = fields.Text(string="JSON Body")

    def invoice_mapping_view(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'QuickBooks Invoice',
            'res_model': 'qbo.invoice.map.vts',
            'view_mode': 'form',
            'view_id': self.env.ref('quickbooks_odoo_connector_canada.view_qbo_invoice_map_form').id,
            'res_id': self.id,
            'target': 'current'
        }
