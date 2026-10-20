# -*- coding: utf-8 -*-
from odoo import models, fields

class QuickbooksCategoryMapping(models.Model):
    _name = 'qbo.category.ca.map.vts'
    _description = "QuickBooks Category Mapping"

    quickbook_instance_id = fields.Many2one('quickbooks.connect', string="QuickBooks Instance")
    quickbook_category_id = fields.Char(string="Category ID")
    quickbook_category_name = fields.Char(string="Category Name")
    category_id = fields.Many2one('product.category', string="Product Category")
    company_id = fields.Many2one('res.company', string="Company", default=lambda self: self.env.user.company_id)
    qbo_response = fields.Text(string="JSON Body")

    def category_mapping_view(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'QuickBooks Category',
            'res_model': 'qbo.category.ca.map.vts',
            'view_mode': 'form',
            'view_id': self.env.ref('quickbooks_odoo_connector_canada.view_qbo_category_map_form').id,
            'res_id': self.id,
            'target': 'current'}