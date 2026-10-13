# -*- coding: utf-8 -*-
from odoo import models, api


class ProductProduct(models.Model):
    _inherit = 'product.product'


    @api.model_create_multi
    def create(self, vals):
        products = super(ProductProduct, self).create(vals)
        for product in products:
            matched_products = self.env['product.product'].search([('categ_id', '=', product.categ_id.id),('id', '!=', product.id),('default_code', '!=', False),])

            prefix_list = []
            for rec in matched_products:
                if rec.default_code.isdigit():
                    prefix_list.append(rec.default_code)

            if prefix_list:
                max_prefix_list = max(prefix_list, key=int)
                prefix = int(max_prefix_list)
                internal_reference = prefix + 1
                product.default_code = str(internal_reference)

            else:
                category = product.categ_id
                internal_reference = False
                counter = "00001"
                if category.prefix and category.parent_id.prefix and category.parent_id.parent_id.prefix:
                    parent_prefix = category.parent_id.parent_id.prefix
                    sub_prefix1 = category.parent_id.prefix
                    current_prefix = category.prefix
                    internal_reference = parent_prefix + sub_prefix1 + current_prefix + counter

                elif category.prefix and category.parent_id.prefix and not category.parent_id.parent_id:
                    parent_prefix = category.parent_id.prefix
                    sub_prefix1 = "00"
                    current_prefix = category.prefix
                    internal_reference = parent_prefix + current_prefix + sub_prefix1 + counter

                elif category.prefix and not category.parent_id:
                    current_prefix = category.prefix
                    sub_prefix1 = "00"
                    parent_prefix = "00"
                    internal_reference = current_prefix + sub_prefix1 + parent_prefix + counter
                else:
                    product.message_post(body="Prefix configuration missing for selected category.")


                product.default_code = internal_reference if internal_reference else False

        return products

