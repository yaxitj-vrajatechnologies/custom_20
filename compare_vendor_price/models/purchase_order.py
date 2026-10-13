# -*- coding: utf-8 -*-
from odoo import models, fields


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    price_enquiry_ids = fields.Many2many('price.enquiry', string='Source Enquiry',
                                        readonly=True, copy=False)
