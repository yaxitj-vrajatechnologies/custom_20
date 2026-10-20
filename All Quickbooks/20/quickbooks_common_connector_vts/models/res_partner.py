# -*- coding: utf-8 *-*
from odoo import models, fields, api

class Partner(models.Model):

	_inherit = "res.partner"

	qk_customer_type = fields.Char(string="Quickbook Customer Type",copy=False)


class ProductTemplate(models.Model):

    _inherit = "product.template"

    quickbook_vendor_product = fields.Boolean(string="Vendor Product", copy=False, default=False)


class Product(models.Model):

    _inherit = "product.product"

    quickbook_vendor_product = fields.Boolean(string="Vendor Product", related='product_tmpl_id.quickbook_vendor_product')


