from odoo import fields,models

class XeroTaxMap(models.Model):
    _name = 'xero.tax.map'
    _description = 'Xero Tax Mapping'

    xero_instance_id = fields.Many2one('xero.connect', string='Xero Instance', )
    xero_tax_id = fields.Char(string='Tax ID')
    xero_tax_name = fields.Char(string='Tax Name')
    tax_id = fields.Many2many('account.tax',string='Taxes',)
    xero_response = fields.Text(string='Xero Tax Response')

    def action_tax_mapping(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Xero Tax Mapping',
            'res_model': 'xero.tax.map',
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'current',
        }
