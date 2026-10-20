# -*- coding: utf-8 -*-
from odoo import models, fields


class QuickbooksProduct(models.Model):

    _name = 'qbo.product.ca.map.vts'
    _description = "Quickbooks product"

    quickbook_instance_id = fields.Many2one('quickbooks.connect', string="Quickbook Instance ID")
    quickbook_product_id = fields.Char(string="Product ID")
    quickbook_product_name = fields.Char(string="Product Name")
    product_id = fields.Many2one('product.template', string="Product")
    company_id = fields.Many2one('res.company', string="Company", default=lambda self: self.env.user.company_id)
    qbo_response = fields.Text(string="JSON Body")

    def product_mapping_view(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Quickbooks Product',
            'res_model': 'qbo.product.ca.map.vts',
            'view_mode': 'form',
            'view_id': self.env.ref('quickbooks_odoo_connector_canada.view_qkb_product_ca_form').id,
            'res_id': self.id,
            'target': 'current'}

