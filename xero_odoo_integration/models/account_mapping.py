from odoo import fields,models

class XeroAccountMap(models.Model):
    _name = 'xero.account.map'
    _description = 'Xero Account Mapping'

    xero_instance_id = fields.Many2one('xero.connect', string='Xero Instance')
    xero_account_id = fields.Char(string='Account ID')
    xero_account_name = fields.Char(string='Account Name')
    account_id = fields.Many2one('account.account',string='Account',)
    xero_response = fields.Text(string='Xero Account Response')
    xero_account_code = fields.Char(string="Xero Account Code")

    def action_account_mapping(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Xero Account Mapping',
            'res_model': 'xero.account.map',
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'current',
        }
