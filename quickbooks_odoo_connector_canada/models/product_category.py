# -*- coding: utf-8 -*-
from odoo import models, fields

class ProductCategory(models.Model):
    
    _inherit = 'product.category'

    qck_instance_id = fields.Char(string='QuickBooks Instance ID', help='Instance from QuickBooks CA')
    qkca_category_ID = fields.Char(string='QuickBooks CA Category ID', help='ID from QuickBooks CA')
