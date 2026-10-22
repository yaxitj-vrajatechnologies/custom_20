from odoo import models, fields


class RepairOrderWizard(models.TransientModel):
    _name = 'repair.order.wizard'
    _description = 'Repair Order Wizard'

    sale_order_id = fields.Many2one(
        comodel_name='sale.order',
        string="Sale Order",
        required=True
    )
    order_line_ids = fields.One2many(
        comodel_name='repair.order.wizard.line',
        inverse_name='wizard_id',
        string="Order Lines"
    )

    def create_repair_orders(self):
        repair_order_obj = self.env['repair.order']
        for line in self.order_line_ids:
            repair_order_obj.create({
                'partner_id': self.sale_order_id.company_id.partner_id.id if self.sale_order_id.company_id else self.env.company.partner_id.id,
                'sale_order_id': self.sale_order_id.id,
                'product_id': line.product_id.id,
                'product_qty': line.quantity,
                'picking_type_id': self.env.ref('repair.picking_type_warehouse0_repair').id
            })
        return {'type': 'ir.actions.act_window_close'}


class RepairOrderLine(models.TransientModel):
    _name = 'repair.order.wizard.line'
    _description = 'Repair Order Line'

    wizard_id = fields.Many2one(
        comodel_name='repair.order.wizard',
        string="Wizard"
    )
    product_id = fields.Many2one(
        comodel_name='product.product',
        string="Product"
    )
    quantity = fields.Float(
        string="Quantity",
        required=True
    )
