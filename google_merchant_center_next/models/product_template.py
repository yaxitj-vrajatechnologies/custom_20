# -*- coding: utf-8 -*-
from odoo import models, fields


class ProductTemplate(models.Model):
    _inherit = "product.template"

    google_product_category_id = fields.Many2one(
        "google.product.taxonomy",
        string="Google Product Category",
        help=(
            "Select the Google product taxonomy category for this product. "
            "This is submitted to Google Merchant Center as the 'google_product_category' attribute."
        ),
    )
    gmc_condition = fields.Selection(
        [
            ("new", "New"),
            ("refurbished", "Refurbished"),
            ("used", "Used"),
        ],
        string="Product Condition",
        default="new",
        help="Condition of the product as required by Google Merchant Center.",
    )
    gmc_brand = fields.Char(
        string="Brand (GMC)",
        help="Brand name as submitted to Google Merchant Center. Overrides company name if set.",
    )
    gmc_mpn = fields.Char(
        string="MPN",
        help="Manufacturer Part Number.",
    )
    gmc_custom_label_0 = fields.Char(string="Custom Label 0")
    gmc_custom_label_1 = fields.Char(string="Custom Label 1")
    gmc_custom_label_2 = fields.Char(string="Custom Label 2")
    gmc_exclude_from_feed = fields.Boolean(
        string="Exclude from GMC Feed",
        default=False,
        help="When checked, this product will be omitted from all Google Merchant Center feeds.",
    )
