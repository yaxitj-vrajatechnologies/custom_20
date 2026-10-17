from odoo import models, fields


class XeroAnalyticAccount(models.Model):
    _name = 'xero.analytic.account.map'
    _description = 'Xero Analytic Account Mapping'

    xero_instance_id = fields.Many2one('xero.connect',string='Xero Instance')
    xero_analytic_acc_id = fields.Char(string='Tracking Option ID',)
    xero_analytic_acc_name = fields.Char(string='Tracking Option Name')
    analytic_account_id = fields.Many2one('account.analytic.account',string='Odoo Analytic Account')
    analytic_plan_id = fields.Many2one('account.analytic.plan',string='Odoo Analytic Plan')
    xero_analytic_plan_id = fields.Char(string='Tracking Category ID')
    xero_response = fields.Text(string='Analytic Account Response')

    def action_analytic_account_mapping(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Xero Analytic Account Mapping',
            'res_model': 'xero.analytic.account.map',
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'current',
        }
