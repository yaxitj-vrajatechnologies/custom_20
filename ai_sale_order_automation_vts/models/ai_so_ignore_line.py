# -*- coding: utf-8 -*-
from odoo import fields, models


class AiSaleOrderDraftIgnoredLine(models.Model):
    _name = "ai.sale.order.draft.ignored.line"
    _description = "AI Sale Order Draft Ignored Line"
    _order = "id"

    draft_id = fields.Many2one(
        "order.automation",
        string="Draft",
        required=True,
        ondelete="cascade",
        index=True,
    )
    source_reference = fields.Char(string="Source Ref.")
    source_description = fields.Char(string="Description")
    quantity_raw = fields.Char(
        string="Qty (as written)",
        help="Empty/zero/crossed-out quantity as read from the document, "
        "if any.",
    )
