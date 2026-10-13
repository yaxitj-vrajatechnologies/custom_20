# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class AiProductMapping(models.Model):
    """Learned mapping between a product name/description as it appears on
    a customer's source document and the actual Odoo product it refers to.

    Records are created/updated from the 'Extracted Lines' tab of an
    'order.automation' draft whenever the user maps (or corrects) a
    product and clicks 'Update Sale Order'. The full table is then passed
    back to the AI on every future 'Create Sale Order' call so it can
    reuse these confirmed matches instead of guessing again.
    """
    _name = "ai.product.mapping"
    _description = "AI Product Mapping"
    _order = "source_product_name"
    _rec_name = "source_product_name"

    source_product_name = fields.Char(
        string="Extracted Product Name",
        required=True,
        index=True,
        help="Product name/description exactly as it comes from the "
             "source document (AI extraction).",
    )
    product_id = fields.Many2one(
        "product.product",
        string="Odoo Product",
        required=True,
        help="Odoo product to use whenever the source document names a "
             "product matching the Extracted Product Name.",
    )

    quantity = fields.Float(
        string="Quantity",
        default=1.0,
        help="Number of units of the Odoo Product that make up ONE unit of "
             "the Extracted Product Name.",
    )

    _source_product_name_uniq = models.Constraint(
        "unique(source_product_name)",
        "This product name is already mapped to an Odoo product.",
    )

    @api.constrains("quantity")
    def _check_quantity(self):
        for mapping in self:
            if mapping.quantity <= 0:
                raise ValidationError(_(
                    "The Quantity of a product mapping must be greater "
                    "than zero."
                ))

    @api.model
    def upsert_mapping(self, source_product_name, product):
        """Create the mapping for `source_product_name` -> `product`, or
        update it if a mapping for that name already exists. Safe to call
        repeatedly - always keeps exactly one mapping per source name.

        `product` may be a product.product recordset or an id.
        """
        source_product_name = (source_product_name or "").strip()
        if not source_product_name or not product:
            return self.browse()

        product_id = product.id if hasattr(product, "id") else product

        existing = self.sudo().search(
            [("source_product_name", "=", source_product_name)], limit=1
        )
        if existing:
            if existing.product_id.id != product_id:
                existing.write({"product_id": product_id})
            return existing

        return self.sudo().create({
            "source_product_name": source_product_name,
            "product_id": product_id,
        })
