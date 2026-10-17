# -*- coding: utf-8 *-*
import pprint
import requests
from odoo import models, fields, api
from odoo.exceptions import ValidationError


class PurchaseOrder(models.Model):
    _inherit = "purchase.order"

    xero_instance_id = fields.Many2one('xero.connect', string="Xero Instance")
    xero_po_id = fields.Char(string="Xero Purchase Order Id")
    xero_po_number = fields.Char(string="Xero Purchase Order Number")
