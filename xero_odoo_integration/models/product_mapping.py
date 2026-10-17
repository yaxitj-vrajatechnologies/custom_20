from odoo import models, fields


class XeroProductMap(models.Model):
    _name = 'xero.product.map'
    _description = 'Xero Product Mapping'

    xero_instance_id = fields.Many2one('xero.connect',string='Xero Instance',)
    xero_product_id = fields.Char(string='Product ID',)
    xero_product_name = fields.Char(string='Product Name')
    product_id = fields.Many2one('product.template',string='Product')
    xero_response = fields.Text(string='Xero Product Response')

    def action_product_mapping(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Xero Product Mapping',
            'res_model': 'xero.product.map',
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'current',
        }
