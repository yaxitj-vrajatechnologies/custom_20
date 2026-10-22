# -*- coding: utf-8 -*-
from odoo import models, _
from odoo.exceptions import UserError

class ProductProduct(models.Model):
    _inherit = 'product.product'

    def action_customize_image(self):
        color_attribute_line = self.product_tmpl_id.attribute_line_ids.filtered(
            lambda line: (line.attribute_id.name or '').strip().lower() == 'color'
        )

        if color_attribute_line:
            color_value = self.product_template_attribute_value_ids.filtered(
                lambda value: (value.attribute_id.name or '').strip().lower() == 'color'
            )

            if color_value:
                for current_image in self.variant_image_ids:
                    current_image.attribute_value_ids = [(6, 0, color_value.ids)]

                # Odoo 20 stores variant_image_ids and does not recompute it when an
                # image's attribute values change, so refresh it for every variant.
                variants = self.product_tmpl_id.product_variant_ids
                variants._compute_variant_image_ids()
                variants._set_main_image_from_extra_images()

            return True

        else:
            raise UserError('Product variant does not have a valid color attribute.')