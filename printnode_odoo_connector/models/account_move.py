from odoo import models

class AccountMove(models.Model):
    _name = 'account.move'
    _inherit = ['account.move', 'printnode.rule.mixin']


    def action_post(self):
        res = super(AccountMove,self).action_post()

        for move in self:
            if move.move_type in ['out_invoice', 'out_refund', 'in_invoice', 'in_refund'] and move.state == 'posted':
                move.print_rule('print_document_on_invoice_validation')

        return res