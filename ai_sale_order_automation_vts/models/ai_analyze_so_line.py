# -*- coding: utf-8 -*-
from odoo import api, fields, models


class AiSaleOrderDraftLine(models.Model):
    _name = "ai.sale.order.draft.line"
    _description = "AI Sale Order Draft Line"
    _order = "id"

    draft_id = fields.Many2one(
        "order.automation",
        string="Draft",
        required=True,
        ondelete="cascade",
        index=True,
    )
    source_reference = fields.Char(
        string="Source Ref.",
        help="Product reference/code exactly as read from the source document.",
    )
    source_description = fields.Char(
        string="Description",
        help="Product description exactly as read from the source document.",
    )
    source_quantity = fields.Float(
        string="Source Quantity",
        help="Quantity exactly as extracted by the AI from the source "
             "document.",
    )
    quantity = fields.Float(
        string="Quantity",
        store=True,
        readonly=False,
        help="Quantity that is applied to the sale order line when 'Update "
             "Sale Order' is clicked. It starts with the same value as the "
             "Source Quantity (or the quantity really created on the sale "
             "order) and can be changed by the user.",
    )
    source_uom = fields.Char(string="Source UoM")
    document_unit_price = fields.Float(string="Unit Price")
    line_number = fields.Integer(string="Line No.", readonly=True)
    sale_order_status = fields.Selection(
        [
            ("pending", "Pending"),
            ("added", "Added to Sale Order"),
            ("not_added", "Not Added"),
        ],
        string="Order Status",
        default="pending",
        readonly=True,
    )
    odoo_product_id = fields.Many2one(
        "product.product",
        string="Odoo Product",
        help="Odoo product mapped to this extracted line. Set "
             "automatically when the AI finds a confident match; "
             "otherwise map it manually here (or correct a wrong match) "
             "and use 'Update Sale Order' to apply it.",
    )
    sale_order_line_id = fields.Many2one(
        "sale.order.line",
        string="Sale Order Line",
        readonly=True,
        copy=False,
        help="Existing sale order line this extracted line corresponds "
             "to, once a sale order has been created. Used by 'Update "
             "Sale Order' to update this exact line instead of creating "
             "a duplicate.",
    )
