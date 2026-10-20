# -*- coding: utf-8 -*-
from odoo import models, _


class SaleOrder(models.Model):
    _name = "sale.order"
    _inherit = ['sale.order', 'printnode.rule.mixin']

    def action_confirm(self):
        """ Overriding the default method to add custom logic for confirm sale orders.
        """
        res = super(SaleOrder, self).action_confirm()
        
        self.print_rule('print_sales_order_document')
        self.print_rule('print_picking_document_after_sale_order_confirmation')

        return res

    def _rule_print_picking_document_after_sale_order_confirmation(self, rule ,report_info, printer_id, total_copies=1):
        """
        Print picking document after Sale Order confirmation
        """

        print_result=False

        if self.warehouse_id.delivery_steps == 'ship_only':
            print_picking_type = self.warehouse_id.out_type_id
        else:
            print_picking_type = self.warehouse_id.pick_type_id

        picking_ids = self.picking_ids.filtered(
            lambda p: p.picking_type_id == print_picking_type)

        if picking_ids:
            print_result = printer_id.printnode_print_document(report_info,picking_ids,total_copies=total_copies)

        return print_result
