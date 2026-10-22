# -*- coding: utf-8 -*-
from odoo import api, models, fields


class GMCFeedLog(models.Model):
    _name = "gmc.feed.log"
    _description = "Google Merchant Center Feed Upload Log"
    _order = "create_date desc"
    _rec_name = 'feed_id'

    feed_id = fields.Many2one(
        "gmc.feed",
        string="Feed",
        ondelete="cascade",
        index=True,
    )
    name = fields.Char(string="Log Entry", compute="_compute_name", store=True)
    remote_filename = fields.Char(string="Remote Filename")
    status = fields.Selection(
        [
            ("success", "Success"),
            ("error", "Error"),
            ("warning", "Warning"),
        ],
        string="Status",
        default="success",
    )
    message = fields.Text(string="Message")
    warnings_text = fields.Text(
        string="Missing Required Fields",
        help="Products that were exported with one or more required GMC fields left empty.",
    )
    warnings_count = fields.Integer(
        string="Warnings",
        compute="_compute_warnings_count",
        store=True,
        help="Number of required-field issues detected during this upload.",
    )
    product_count = fields.Integer(string="Products Exported")
    file_size_kb = fields.Float(string="File Size (KB)", digits=(10, 2))
    duration_seconds = fields.Float(string="Duration (s)", digits=(10, 2))
    trigger = fields.Selection(
        [
            ("manual", "Manual"),
            ("scheduled", "Scheduled"),
        ],
        string="Trigger",
        default="manual",
    )
    create_date = fields.Datetime(
        string="Date/Time",
        readonly=True,
    )

    @api.depends("create_date", "remote_filename")
    def _compute_name(self):
        for rec in self:
            rec.name = "[%s] %s" % (
                (rec.create_date or fields.Datetime.now()).strftime("%Y-%m-%d %H:%M"),
                rec.remote_filename or "feed",
            )

    @api.depends("warnings_text")
    def _compute_warnings_count(self):
        for rec in self:
            if not rec.warnings_text:
                rec.warnings_count = 0
                continue
            # Parse "Total missing cells : N" from the Summary block
            count = 0
            for line in rec.warnings_text.splitlines():
                if "Total missing cells" in line:
                    parts = line.rsplit(":", 1)
                    if len(parts) == 2:
                        try:
                            count = int(parts[1].strip())
                        except ValueError:
                            pass
                    break
            # Fallback: count bullet lines if summary line not found
            if not count:
                count = rec.warnings_text.count("\n  • ")
            rec.warnings_count = count
