from odoo import models, fields


class ProductAccessoryMapping(models.Model):
    _name = 'product.accessory.vts'
    _description = 'Product Accessory Mapping'
    _order = 'category_id'

    category_id = fields.Many2one(
        'product.category',
        string="Main Category",
        required=True,
        help="Select Main Product Category"
    )

    accessory_category_ids = fields.Many2many(
        'product.category',
        string="Accessory Categories",
        help="Accessories Category for the product"
    )

    accessory_product_rule_ids = fields.Many2many(
        'product.rule.vts',
        string="Accessory Rules",
        help="Add multiple rule as per product accessories"
    )