from odoo import models


class PurchaseOrder(models.Model):
    _name = "purchase.order"
    _inherit = ['purchase.order', 'printnode.rule.mixin']


    def button_approve(self, force=False):
        """ Overriding the default method to add custom logic with print rule for
            confirm purchase orders.
        """
        res = super(PurchaseOrder, self).button_approve(force=force)

        self.print_rule('print_purchase_order_document')
        self.print_rule('print_document_on_picking_after_po_confirmation')

        return res

    def _rule_print_document_on_picking_after_po_confirmation(self,rule, report_info, printer_id, total_copies=1, **kwargs):
        """
        Print picking document after PO confirmation
        """

        picking_ids = self.picking_ids.filtered(
            lambda p: p.picking_type_id == self.picking_type_id.warehouse_id.in_type_id)

        printer_id.printnode_print_document(report_info,picking_ids,total_copies=total_copies)