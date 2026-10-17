# -*- coding: utf-8 *-*
from odoo import models, fields, api

class Partner(models.Model):

	_inherit = "res.partner"

	qck_instance_id = fields.Many2one('quickbooks.connect',string="Quickbook Instance",copy=False)
	qk_customer_type = fields.Char(string="Quickbook Customer Type",copy=False)
	qbk_id = fields.Char(string="Quickbook Customer ID",copy=False)


class ProductTemplate(models.Model):

    _inherit = "product.template"

    quickbook_vendor_product = fields.Boolean(string="Vendor Product", copy=False, default=False)


class Product(models.Model):

    _inherit = "product.product"

    quickbook_vendor_product = fields.Boolean(string="Vendor Product", related='product_tmpl_id.quickbook_vendor_product')


