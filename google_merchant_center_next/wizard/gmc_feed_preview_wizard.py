# -*- coding: utf-8 -*-
from odoo import models, fields


class GMCFeedPreviewWizard(models.TransientModel):
    _name = "gmc.feed.preview.wizard"
    _description = "Google Merchant Center Feed Preview"

    feed_id = fields.Many2one("gmc.feed", string="Feed", readonly=True)
    content = fields.Text(
        string="Feed Preview",
        readonly=True,
    )
