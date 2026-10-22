# -*- coding: utf-8 -*-
from odoo import fields, models

class ProductCategory(models.Model):
    _inherit = 'product.category'

    fruugo_category_id = fields.Many2one(
        'fruugo.category',
        string='Fruugo Category',
        help='Map this internal category to a valid Fruugo Category path. Products in this category will use it automatically unless overridden on the product.',
    )
