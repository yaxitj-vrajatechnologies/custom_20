# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import ValidationError


class PriceEnquiryLine(models.Model):
    _name = 'price.enquiry.line'
    _description = 'Vendor Price Enquiry Line (Product + Required Qty)'

    enquiry_id = fields.Many2one('price.enquiry', string='Enquiry',required=True, ondelete='cascade')
    product_id = fields.Many2one('product.product', string='Product', required=True)
    qty = fields.Float(string='Required Qty', required=True, default=1.0)
    winning_line_id = fields.Many2one(
        'price.quotation.line', string='Vendor',
        domain="[('product_id', '=', product_id), ('enquiry_id', '=', enquiry_id), "
               "('quotation_id.state', '=', 'received'), ('quotation_id.import_file', '!=', False)]",
    )
    unit_price = fields.Float(related='winning_line_id.unit_price', string='Price', store=True, readonly=True)
    lead_time = fields.Integer(related='winning_line_id.lead_time', string='Lead Time (Days)',
                                store=True, readonly=True)
    has_lead_time = fields.Boolean(related='winning_line_id.has_lead_time', string='Has Lead Time',
                                    store=True, readonly=True)
    expected_delivery_date = fields.Date(related='winning_line_id.expected_delivery_date', string='Lead Date',
                                          store=True, readonly=True)

    @api.constrains('qty')
    def _check_qty(self):
        for line in self:
            if line.qty < 1:
                raise ValidationError(
                    'Required Qty for %s must be at least 1 (got %s).'
                    % (line.product_id.display_name or 'the product', line.qty)
                )

