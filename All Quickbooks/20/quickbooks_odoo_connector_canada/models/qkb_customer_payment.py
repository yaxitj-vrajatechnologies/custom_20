# -*- coding: utf-8 -*-
from odoo import models, fields


class QuickbooksCustomerPayment(models.Model):

    _name = 'qbo.payment.ca.map.vts'
    _description = "Quickbooks Customer Payment"

    quickbook_instance_id = fields.Many2one('quickbooks.connect', string="Quickbook Instance ID")
    quickbook_cust_payment_id = fields.Char(string="Payment ID")
    payment_id = fields.Many2one('account.payment', string="Payment")
    partner_id = fields.Many2one('res.partner', string="Customer")
    company_id = fields.Many2one('res.company', string="Company", default=lambda self: self.env.user.company_id)
    qbo_response = fields.Text(string="JSON Body")

    def customer_payment_mapping_view(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Quickbooks Customer Payment',
            'res_model': 'qbo.payment.ca.map.vts',
            'view_mode': 'form',
            'view_id': self.env.ref('quickbooks_odoo_connector_canada.view_qkb_customer_payment_ca_form').id,
            'res_id': self.id,
            'target': 'current'}