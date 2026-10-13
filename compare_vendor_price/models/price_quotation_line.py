# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import models, fields, api


class PriceQuotationLine(models.Model):
    _name = 'price.quotation.line'
    _description = 'Vendor Quotation Line (used for price comparison)'

    quotation_id = fields.Many2one('price.quotation', string='Quotation',
                                    required=True, ondelete='cascade')
    vendor_id = fields.Many2one(related='quotation_id.vendor_id', string='Vendor', store=True)
    enquiry_id = fields.Many2one(related='quotation_id.enquiry_id', string='Enquiry', store=True)

    product_id = fields.Many2one('product.product', string='Product', required=True)
    product_weight = fields.Float(related='product_id.weight', string='Weight', store=True)

    qty_requested = fields.Float(string='Qty Requested')
    qty_offered = fields.Float(string='Total Qty')

    unit_price = fields.Float(string='Unit Price')

    lead_time = fields.Integer(string='Lead Time (Days)')

    # Whether a lead time was actually supplied (via CSV import or manual
    # entry) for this line. Odoo Integer/Date fields cannot truly stay
    # "empty" once written, so this flag drives the view to show a blank
    # cell instead of a misleading 0 / today's date whenever no lead time
    # is available (missing from the vendor's file, or a delivery date that
    # was already in the past at import time).
    has_lead_time = fields.Boolean(string='Has Lead Time', default=True, copy=False)

    # Actual calendar date the vendor is expected to deliver by, derived from
    # lead_time (days) counted from whenever the RFQ was sent to this vendor.
    # Kept as a separate stored field (rather than computed on the fly in the
    # view) so it can be sorted/grouped/filtered like any normal date field.
    expected_delivery_date = fields.Date(
        string='Expected Delivery Date', compute='_compute_expected_delivery_date', store=True)

    is_lowest_price = fields.Boolean(string='Lowest Price', default=False)
    is_lowest_leadtime = fields.Boolean(string='Lowest Lead Time', default=False)
    # is_selected = fields.Boolean(string='Selected for PO', default=False)
    is_po_created = fields.Boolean(string='PO Created', default=False, copy=False)

    @api.depends('lead_time', 'has_lead_time', 'quotation_id.rfq_sent_date')
    def _compute_expected_delivery_date(self):
        for line in self:
            if not line.has_lead_time:
                line.expected_delivery_date = False
                continue
            base_date = ((line.quotation_id.rfq_sent_date and line.quotation_id.rfq_sent_date.date())
                         or fields.Date.context_today(line))
            line.expected_delivery_date = base_date + timedelta(days=line.lead_time or 0)

    @api.onchange('lead_time')
    def _onchange_lead_time(self):
        # Manually typing a lead time (e.g. correcting a blanked line)
        # marks it as having a lead time again.
        for line in self:
            if line.lead_time:
                line.has_lead_time = True

    def _compute_display_name(self):
        # Makes this record show up as the vendor's name wherever it's picked
        # from a dropdown - specifically the "Vendor" selector on the
        # enquiry line, so switching vendors reads naturally.
        # (name_get is deprecated/removed as of Odoo 17+; this is its
        # replacement and is what actually gets called in Odoo 19.)
        for rec in self:
            rec.display_name = rec.vendor_id.name or ''
