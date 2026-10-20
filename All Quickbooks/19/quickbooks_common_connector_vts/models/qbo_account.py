from odoo import models, fields, api


class QuickbooksAccount(models.Model):

    _name = 'qbo.account.vts'
    _description = "Quickbooks Account"
    _rec_name = "account_id"

    quickbook_instance_id = fields.Many2one('quickbooks.connect', string="Quickbook Instance ID")
    quickbook_account_id = fields.Char(string="Account ID")
    quickbook_account_name = fields.Char(string="Account Name")
    account_id = fields.Many2one('account.account', string="Odoo Accounts")
    company_id = fields.Many2one('res.company', string="Company", default=lambda self: self.env.user.company_id)
    qbo_response = fields.Text(string="JSON Body")

    def account_mapping_view(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Quickbooks Accounts',
            'res_model': 'qbo.account.vts',
            'view_mode': 'form',
            'view_id': self.env.ref('quickbooks_common_connector_vts.view_qbo_account_form').id,
            'res_id': self.id,
            'target': 'current',
        }
