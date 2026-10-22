# -*- coding: utf-8 -*-
from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    # ── Fruugo-specific fields ────────────────────────────────────────────────
    fruugo_category_id = fields.Many2one(
        'fruugo.category',
        string='Fruugo Category',
        help=(
            'Map this product to a valid Fruugo Category.\n'
            'This overrides the category mapping set on the Product Category level.'
        ),
    )
    fruugo_brand = fields.Char(
        string='Fruugo Brand',
        help=(
            'Brand name as it should appear on Fruugo.\n'
            'If left empty, the product internal category name will be used as fallback.'
        ),
    )
    fruugo_ean_exception = fields.Boolean(
        string='EAN Exception (Manufacturer)',
        default=False,
        help=(
            'Tick this if you are the product\'s manufacturer and have no EAN/barcode.\n'
            'The feed will export "EXCEP" as the EAN value to satisfy Fruugo\'s requirement.'
        ),
    )
    fruugo_excluded = fields.Boolean(
        string='Exclude from Fruugo',
        default=False,
        help='If ticked, this product will not appear in any Fruugo feed.',
    )
    fruugo_lead_time = fields.Integer(
        string='Fruugo Lead Time (days)',
        default=0,
        help=(
            'Number of days from order to dispatch (when product is INSTOCK).\n'
            'Only include this if the lead time is more than 1 day (Fruugo default is 1).'
        ),
    )
    fruugo_country_restriction = fields.Char(
        string='Fruugo Country Restrictions',
        help=(
            'Space-separated ISO 3166 two-letter country codes to limit where this product is visible.\n'
            'Example: IE FR DE\n'
            'Leave blank for no restriction (default account settings apply).'
        ),
    )
