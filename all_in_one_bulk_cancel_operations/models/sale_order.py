from odoo import models, fields, api
from odoo.exceptions import ValidationError


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    register_payment_journal_id = fields.Many2one('account.journal', string="Register Payment Journal")

    @api.model
    def create(self, vals):
        """
        Create method inherited to add journal id from company.
        """
        res = super(SaleOrder, self).create(vals)
        if res.company_id and res.company_id.register_payment_journal_id:
            res.register_payment_journal_id = res.company_id.register_payment_journal_id.id
        return res

    def all_in_one_bulk_cancel_sale_order(self):
        """
        - This method is called when Cancel order called from action of list view of sale order
        - From this method sale order cancel process get done &
        with that if invoice available then invoices get cancelled & deleted.
        """
        if self.filtered(lambda r: r.state == 'cancel'):
            raise ValidationError('One or many records are already cancelled.')
        for rec in self:
            rec.with_context(disable_cancel_warning=True).action_cancel()
            if rec.picking_ids:
                done_picking = rec.picking_ids.filtered(lambda r: r.state == 'done')
                for picking in done_picking:
                    picking.action_cancel()
            if rec.invoice_ids:
                rec.invoice_ids.with_context(force_delete=True).all_in_one_force_delete_invoice_and_related_payment()

    def all_in_one_action_return_order(self):
        """
        - This method is called when Return order button called from sale order form view
        - From this method sale order cancel process get done,
        with that if posted but not paid invoice available then invoices get cancelled & deleted &
        for paid & posted invoice refund invoice process get done.
        """
        if self.state == 'cancel':
            raise ValidationError('Record already cancelled.')
        for rec in self:
            rec.with_context(disable_cancel_warning=True).action_cancel()
            invoice_records = rec.invoice_ids.filtered(lambda r: r.move_type == 'out_invoice')
            if invoice_records:
                paid_posted_invoice_records = invoice_records.filtered(
                    lambda r: r.payment_state in ['paid', 'in_payment', 'partial'] and r.state == 'posted')
                remaining_invoice = invoice_records - paid_posted_invoice_records

                # For Paid invoice process of refund invoice & register payment
                for p_invoice in paid_posted_invoice_records:
                    if p_invoice.reversal_move_ids:
                        continue
                    # To add credit note in invoice
                    credit_note_wizard = self.env['account.move.reversal'].with_context(
                        {'active_ids': [p_invoice.id], 'active_id': p_invoice.id,
                         'active_model': 'account.move'}).create({'reason': 'Reverse invoice against ' + str(rec.name),
                                                                  'journal_id': p_invoice.journal_id.id, })
                    response_credit_note_wizard = credit_note_wizard.reverse_moves()
                    if response_credit_note_wizard.get('res_id'):
                        new_reversal_move_id = self.env['account.move'].browse(
                            response_credit_note_wizard.get('res_id'))
                        if new_reversal_move_id and new_reversal_move_id.state == 'draft':
                            new_reversal_move_id.action_post()
                            if new_reversal_move_id.state == 'posted':
                                # To register payment in invoice
                                journal_id = rec.register_payment_journal_id or self.env['account.journal']
                                payment_method_line = journal_id.inbound_payment_method_line_ids.filtered(
                                    lambda x: x.name.lower() == 'manual')
                                if payment_method_line:
                                    pmt_wizard = self.env['account.payment.register'].with_context(
                                        active_model='account.move',
                                        active_ids=new_reversal_move_id.ids).create(
                                        {'payment_date': new_reversal_move_id.date,
                                         'journal_id': journal_id.id,
                                         'payment_method_line_id': payment_method_line.id,
                                         'currency_id': new_reversal_move_id.currency_id and new_reversal_move_id.currency_id.id,
                                         'amount': new_reversal_move_id.amount_total,
                                         'group_payment': True,
                                         'communication': new_reversal_move_id.name or new_reversal_move_id.display_name or ' '})
                                    pmt_wizard._create_payments()

                # For remaining invoice process of cancel & unlink
                for r_invoice in remaining_invoice:
                    r_invoice.with_context(force_delete=True).all_in_one_force_delete_invoice_and_related_payment()
