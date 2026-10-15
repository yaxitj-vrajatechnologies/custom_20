# -*- coding: utf-8 -*-
from odoo import fields, models, _, tools


class ApprovalMatrixRejectWizard(models.TransientModel):
    _name = 'approval.matrix.reject.wizard'
    _description = 'Reject Quotation - Reason'

    sale_order_id = fields.Many2one('sale.order', required=True, readonly=True)
    reason = fields.Text(required=True, string='Rejection Reason')

    def action_confirm_reject(self):
        self.ensure_one()
        order = self.sale_order_id
        order.write({
            'approval_state': 'rejected',
            'approval_manager_id': self.env.user.id,
            'approval_date': fields.Datetime.now(),
            'approval_reject_reason': self.reason,
        })
        order._close_approval_activities()
        order.message_post(
            body=tools.html_sanitize(_("Quotation rejected by %(user)s.<br/>Reason: %(reason)s")) 
            % {'user': self.env.user.name, 'reason': self.reason},
            partner_ids=order._get_salesperson_partner_ids(),
        )
        # Rejection needs the salesperson to actually do something (revise the
        # quote and re-request approval), so give them an activity, not just a
        # notification they might skim past.
        if order.user_id:
            order.activity_schedule(
                'mail.mail_activity_data_todo',
                summary=_('Quotation Rejected: %s') % order.name,
                note=_(
                    "Your quotation was rejected by %(user)s.<br/>Reason: %(reason)s<br/>"
                    "Please revise it and request approval again."
                ) % {'user': self.env.user.name, 'reason': self.reason},
                user_id=order.user_id.id,
            )
        return {'type': 'ir.actions.act_window_close'}
