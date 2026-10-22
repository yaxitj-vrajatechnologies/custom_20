# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import ValidationError

class GoogleProductTaxonomy(models.Model):
    _name = "google.product.taxonomy"
    _description = "Google Product Taxonomy"
    _rec_name = "full_path"
    _order = "full_path asc"

    google_id = fields.Integer(
        string="Google ID",
        required=True,
        index=True,
        help="The numeric identifier assigned by Google to this product category.",
    )
    name = fields.Char(
        string="Category Name",
        required=True,
        help="The leaf-level name of this taxonomy entry.",
    )
    full_path = fields.Char(
        string="Full Path",
        required=True,
        index=True,
        help="Full breadcrumb path, e.g. 'Animals & Pet Supplies > Pet Supplies > Dog Supplies'.",
    )
    parent_id = fields.Many2one(
        "google.product.taxonomy",
        string="Parent Category",
        ondelete="set null",
        index=True,
    )
    child_ids = fields.One2many(
        "google.product.taxonomy",
        "parent_id",
        string="Sub-categories",
    )
    product_count = fields.Integer(
        string="Products",
        compute="_compute_product_count",
        store=False,
    )

    @api.constrains("google_id")
    def _check_unique_google_id(self):
        for rec in self:
            if rec.google_id:
                count = self.search_count([
                    ("google_id", "=", rec.google_id),
                    ("id", "!=", rec.id),
                ])
                if count > 0:
                    raise ValidationError("A taxonomy entry with this Google ID already exists!")

    @api.depends()
    def _compute_product_count(self):
        """Count product.templates linked to each taxonomy node."""
        for rec in self:
            rec.product_count = self.env["product.template"].search_count(
                [("google_product_category_id", "=", rec.id)]
            )

    def action_view_products(self):
        self.ensure_one()
        return {
            "name": "Products",
            "type": "ir.actions.act_window",
            "res_model": "product.template",
            "view_mode": "list,form",
            "domain": [("google_product_category_id", "=", self.id)],
        }
