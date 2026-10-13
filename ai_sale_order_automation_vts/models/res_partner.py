# -*- coding: utf-8 -*-
from odoo import fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    ai_order_instruction = fields.Text(
        string="AI Order Instructions",
        help="Customer-specific instructions for the Sale Order Automation. "
             "When this customer is selected on an automation record, this "
             "text is added to that record's Extraction Prompt.",
    )
