from odoo import models, fields, api


class QuickbooksPaymentTerms(models.Model):

    _name = 'qbo.payment.terms.vts'
    _description = "Quickbooks Payment Terms"
    _rec_name = "payment_id"

    quickbook_instance_id = fields.Many2one('quickbooks.connect', string="Quickbook Instance ID")
    quickbook_payment_id = fields.Char(string="Payment ID")
    quickbook_payment_name = fields.Char(string="Payment Name")
    payment_id = fields.Many2one('account.payment.term', string="Odoo Payment Terms")
    company_id = fields.Many2one('res.company', string="Company", default=lambda self: self.env.user.company_id)
    qbo_response = fields.Text(string="JSON Body")

    def payment_terms_mapping_view(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Quickbooks Payment Terms',
            'res_model': 'qbo.payment.terms.vts',
            'view_mode': 'form',
            'view_id': self.env.ref('quickbooks_common_connector_vts.view_qbo_payment_terms_form').id,
            'res_id': self.id,
            'target': 'current',
        }



