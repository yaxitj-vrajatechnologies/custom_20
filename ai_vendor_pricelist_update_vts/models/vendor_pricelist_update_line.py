# -*- coding: utf-8 -*-
from odoo import fields, models


class VendorPricelistUpdateLine(models.Model):
    """One row per product line coming back from the AI analysis.
    Holds both matched and unmatched rows - `matched` tells them apart so a
    single tab/list can be filtered/grouped in the view, while keeping the
    model simple (one2many on the main record).
    """
    _name = 'vendor.pricelist.update.line'
    _description = 'Vendor Pricelist AI Update - Product Match Line'
    _order = 'matched desc, id'

    update_id = fields.Many2one(
        'vendor.pricelist.update', string='Update', required=True,
        ondelete='cascade', index=True,
    )
    vendor_id = fields.Many2one(related='update_id.vendor_id', store=True, string='Vendor')
    company_id = fields.Many2one(related='update_id.company_id', store=True, string='Company')

    matched = fields.Boolean(string='Matched', default=False)

    # -- identification (as returned by the AI / vendor file) --------------
    vendor_product_code = fields.Char(
        string='Vendor Product Code',
        help='Product code used to match against the existing Vendor Pricelist lines '
             '(product.supplierinfo product_code) for this vendor.',
    )
    product_name = fields.Char(string='Product Name')

    # -- resolved Odoo product ----------------------------------------------
    product_tmpl_id = fields.Many2one('product.template', string='Product', readonly=True)
    product_id = fields.Many2one(
        'product.product', string='Product Variant',
        help='For unmatched lines: the product selected by the user, either to '
             'map this line to (Map with Existing) or to duplicate (Create New Product).',
    )

    # -- resolution of unmatched lines (set by the user in the "Unmatched
    # Products" tab, applied via vendor.pricelist.update.action_process_unmatched)
    unmatched_action = fields.Selection([
        ('map_existing', 'Map with Existing'),
        ('create_new', 'Create New Product'),
    ], string='Action')

    # -- values coming from the AI ------------------------------------------
    price = fields.Float(string='Unit Price', digits='Product Price')
    quantity = fields.Float(string='Quantity', digits='Product Unit', default=1.0)
    uom_id = fields.Many2one('uom.uom', string='Unit')
    discount = fields.Float(string='Discount (%)')
    delay = fields.Float(string='Lead Time')
    date_start = fields.Date(string='Start Date')
    date_end = fields.Date(string='End Date')
    note = fields.Char(string='Note')

    # -- application tracking ------------------------------------------------
    apply_state = fields.Selection([
        ('pending', 'Pending'),
        ('updated', 'Updated Existing Line'),
        ('created', 'Created New Line'),
    ], string='Apply Result', default='pending', readonly=True)

    applied_supplierinfo_id = fields.Many2one(
        'product.supplierinfo', string='Resulting Pricelist Line', readonly=True,
    )
