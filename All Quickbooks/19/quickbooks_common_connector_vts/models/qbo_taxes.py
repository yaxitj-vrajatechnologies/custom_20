from odoo import models, fields, api


class QuickbooksTaxes(models.Model):

    _name = 'qbo.taxes.vts'
    _description = "Quickbooks Taxes"
    _rec_name = "tax_id"

    quickbook_instance_id = fields.Many2one('quickbooks.connect', string="Quickbook Instance ID")
    quickbook_tax_id = fields.Char(string="Tax ID")
    quickbook_tax_name = fields.Char(string="Tax Name")
    tax_id = fields.Many2one('account.tax', string="Odoo Taxes")
    company_id = fields.Many2one('res.company', string="Company", default=lambda self: self.env.user.company_id)
    qbo_response = fields.Text(string="JSON Body")

    def taxes_mapping_view(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Quickbooks Taxes',
            'res_model': 'qbo.taxes.vts',
            'view_mode': 'form',
            'view_id': self.env.ref('quickbooks_common_connector_vts.view_qbo_taxes_form').id,
            'res_id': self.id,
            'target': 'current',
        }
