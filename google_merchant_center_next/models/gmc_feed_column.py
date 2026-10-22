# -*- coding: utf-8 -*-
from odoo import models, fields


class GMCFeedColumn(models.Model):
    _name = "gmc.feed.column"
    _description = "Google Merchant Center Feed Column"
    _order = "sequence asc, id asc"

    feed_id = fields.Many2one(
        "gmc.feed",
        string="Feed",
        required=True,
        ondelete="cascade",
        index=True,
    )
    sequence = fields.Integer(string="Sequence", default=10)
    name = fields.Char(
        string="Column Label",
        required=True,
        help="Human-readable label, e.g. 'Google Product Category'.",
    )
    column_key = fields.Selection([
        ('g:id', 'ID (g:id)'),
        ('title', 'Title (title)'),
        ('description', 'Description (description)'),
        ('link', 'Link (link)'),
        ('g:image_link', 'Image Link (g:image_link)'),
        ('g:additional_image_link', 'Additional Image Link (g:additional_image_link)'),
        ('g:mobile_link', 'Mobile Link (g:mobile_link)'),
        ('g:availability', 'Availability (g:availability)'),
        ('g:availability_date', 'Availability Date (g:availability_date)'),
        ('g:price', 'Price (g:price)'),
        ('g:sale_price', 'Sale Price (g:sale_price)'),
        ('g:sale_price_effective_date', 'Sale Price Effective Date (g:sale_price_effective_date)'),
        ('g:cost_of_goods_sold', 'Cost of Goods Sold (g:cost_of_goods_sold)'),
        ('g:unit_pricing_measure', 'Unit Pricing Measure (g:unit_pricing_measure)'),
        ('g:unit_pricing_base_measure', 'Unit Pricing Base Measure (g:unit_pricing_base_measure)'),
        ('g:installment', 'Installment (g:installment)'),
        ('g:subscription_cost', 'Subscription Cost (g:subscription_cost)'),
        ('g:loyalty_program', 'Loyalty Program (g:loyalty_program)'),
        ('g:google_product_category', 'Google Product Category (g:google_product_category)'),
        ('g:product_type', 'Product Type (g:product_type)'),
        ('g:brand', 'Brand (g:brand)'),
        ('g:gtin', 'GTIN (g:gtin)'),
        ('g:mpn', 'MPN (g:mpn)'),
        ('g:identifier_exists', 'Identifier Exists (g:identifier_exists)'),
        ('g:condition', 'Condition (g:condition)'),
        ('g:adult', 'Adult (g:adult)'),
        ('g:multipack', 'Multipack (g:multipack)'),
        ('g:is_bundle', 'Is Bundle (g:is_bundle)'),
        ('g:item_group_id', 'Item Group ID (g:item_group_id)'),
        ('g:age_group', 'Age Group (g:age_group)'),
        ('g:color', 'Color (g:color)'),
        ('g:gender', 'Gender (g:gender)'),
        ('g:material', 'Material (g:material)'),
        ('g:pattern', 'Pattern (g:pattern)'),
        ('g:size', 'Size (g:size)'),
        ('g:size_type', 'Size Type (g:size_type)'),
        ('g:size_system', 'Size System (g:size_system)'),
        ('g:energy_efficiency_class', 'Energy Efficiency Class (g:energy_efficiency_class)'),
        ('g:min_energy_efficiency_class', 'Min Energy Efficiency Class (g:min_energy_efficiency_class)'),
        ('g:max_energy_efficiency_class', 'Max Energy Efficiency Class (g:max_energy_efficiency_class)'),
        ('g:custom_label_0', 'Custom Label 0 (g:custom_label_0)'),
        ('g:custom_label_1', 'Custom Label 1 (g:custom_label_1)'),
        ('g:custom_label_2', 'Custom Label 2 (g:custom_label_2)'),
        ('g:custom_label_3', 'Custom Label 3 (g:custom_label_3)'),
        ('g:custom_label_4', 'Custom Label 4 (g:custom_label_4)'),
        ('g:promotion_id', 'Promotion ID (g:promotion_id)'),
        ('g:lifestyle_image_link', 'Lifestyle Image Link (g:lifestyle_image_link)'),
        ('g:product_highlight', 'Product Highlight (g:product_highlight)'),
        ('g:product_detail', 'Product Detail (g:product_detail)'),
        ('g:shipping', 'Shipping (g:shipping)'),
        ('g:shipping_weight', 'Shipping Weight (g:shipping_weight)'),
        ('g:shipping_length', 'Shipping Length (g:shipping_length)'),
        ('g:shipping_width', 'Shipping Width (g:shipping_width)'),
        ('g:shipping_height', 'Shipping Height (g:shipping_height)'),
        ('g:transit_time_label', 'Transit Time Label (g:transit_time_label)'),
        ('g:max_handling_time', 'Max Handling Time (g:max_handling_time)'),
        ('g:min_handling_time', 'Min Handling Time (g:min_handling_time)'),
        ('g:return_policy_label', 'Return Policy Label (g:return_policy_label)'),
        ('g:expiration_date', 'Expiration Date (g:expiration_date)'),
        ('custom', 'Custom Tag...'),
    ], string="Feed Key", required=True, help="Standard Google XML tag used in the exported feed.")
    custom_column_key = fields.Char(
        string="Custom Feed Key",
        help="Provide your exact custom XML tag, e.g. 'g:my_custom_tag'.",
    )
    field_id = fields.Many2one(
        'ir.model.fields',
        string="Model Field",
        domain=[('model', 'in', ['product.template', 'product.product'])],
        help="Select the specific Odoo field to be synced.",
    )
    static_value = fields.Char(
        string="Static Value",
        help="A fixed string written to every row (used if no model field is selected).",
    )
    active = fields.Boolean(string="Active", default=True)
    is_required = fields.Boolean(
        string="Required",
        help="Mark mandatory GMC attributes so they are never accidentally removed.",
    )
    notes = fields.Char(string="Notes / Hint")

    # Computed / special keywords supported:
    # image_url        → full public URL of product image
    # product_url      → full public website URL of the product
    # availability     → mapped from qty_available (in_stock / out_of_stock / preorder)
    # price_with_currency → list_price + currency code
