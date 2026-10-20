# -*- coding: utf-8 -*-
from odoo import models, fields


class QuickbooksPaymentMethod(models.Model):

    _name = 'qbo.payment.method.vts'
    _description = "Quickbooks Payment Method"
    _rec_name = "journal_id"

    quickbook_instance_id = fields.Many2one('quickbooks.connect', string="Quickbook Instance ID")
    quickbook_id = fields.Char(string="Quickbooks ID")
    quickbook_payment_method_name = fields.Char(string="Journal Name")
    journal_id = fields.Many2one('account.journal', string="Odoo Journal")
    company_id = fields.Many2one('res.company', string="Company", default=lambda self: self.env.user.company_id)
    qbo_response = fields.Text(string="JSON Body")

    def payment_method_mapping_view(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Quickbooks Payment Method',
            'res_model': 'qbo.payment.method.vts',
            'view_mode': 'form',
            'view_id': self.env.ref('quickbooks_common_connector_vts.view_qbo_payment_method_form').id,
            'res_id': self.id,
        }
