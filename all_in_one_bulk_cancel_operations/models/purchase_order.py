from odoo import models, fields, api
from odoo.exceptions import ValidationError


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    def button_cancel(self):
        for order in self:
            pickings = order.picking_ids.filtered(lambda p: p.state == 'done')
            if pickings:
                for picking in pickings:
                    picking.action_cancel()
            for inv in order.invoice_ids:
                if inv and inv.state in ('posted'):
                    inv.with_context(force_delete=True).all_in_one_force_delete_invoice_and_related_payment()
        return super(PurchaseOrder, self).button_cancel()

    def all_in_one_bulk_cancel_purchase_order(self):
        """
        - This method is called when Cancel order called from action of list view of purchase order
        - From this method purchase order cancel process get done &
        with that if invoice available then invoices get cancelled & deleted.
        """
        if self.filtered(lambda r: r.state == 'cancel'):
            raise ValidationError('One or many records are already cancelled.')
        for rec in self:
            rec.button_cancel()


