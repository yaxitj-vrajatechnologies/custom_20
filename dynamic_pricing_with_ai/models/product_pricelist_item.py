# -*- coding: utf-8 -*-

from odoo import fields, models

class ProductPricelistItem(models.Model):
    _inherit = 'product.pricelist.item'

    is_ai_price = fields.Boolean(
        string='AI Generated Product Price',
        default=False,
        help='Indicates that this pricelist item was created or updated by Dynamic AI Pricing.'
    )

