from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    register_payment_journal_id = fields.Many2one('account.journal', string="Register Payment Journal")
