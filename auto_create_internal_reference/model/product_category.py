# -*- coding: utf-8 -*-
from odoo import models, fields


class ProductCategory(models.Model):
    _inherit = 'product.category'


    prefix = fields.Char(string="Prefix", help="Enter Product Category Prefix")