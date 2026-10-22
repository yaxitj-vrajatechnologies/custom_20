# -*- coding: utf-8 -*-
from odoo import api, fields, models


class FruugoFeedLog(models.Model):
    _name = 'fruugo.feed.log'
    _description = 'Fruugo Feed Generation Log'
    _order = 'create_date desc'
    _rec_name = 'name'

    feed_id = fields.Many2one(
        'fruugo.feed',
        string='Feed',
        ondelete='cascade',
        index=True,
    )
    name = fields.Char(string='Log Entry', compute='_compute_name', store=True)

    status = fields.Selection(
        [('success', 'Success'), ('error', 'Error')],
        string='Status',
        default='success',
    )
    message = fields.Text(string='Message')
    trigger = fields.Selection(
        [('manual', 'Manual'), ('scheduled', 'Scheduled (Cron)')],
        string='Triggered By',
        default='manual',
    )

    # ── File Attachment ───────────────────────────────────────────────────────
    attachment_id = fields.Many2one(
        'ir.attachment',
        string='Generated XML File',
        readonly=True,
        ondelete='set null',
    )
    attachment_name = fields.Char(
        string='Filename',
        related='attachment_id.name',
        readonly=True,
    )
    file_size_kb = fields.Float(string='File Size (KB)', digits=(10, 2))

    # ── Stats ─────────────────────────────────────────────────────────────────
    product_count = fields.Integer(string='Products Exported')
    duration_seconds = fields.Float(string='Duration (s)', digits=(10, 2))
    create_date = fields.Datetime(string='Date / Time', readonly=True)

    @api.depends('create_date', 'feed_id', 'trigger')
    def _compute_name(self):
        for rec in self:
            dt = (rec.create_date or fields.Datetime.now()).strftime('%Y-%m-%d %H:%M')
            trigger_label = dict(rec._fields['trigger'].selection).get(rec.trigger, rec.trigger or '')
            rec.name = '[%s] %s — %s' % (dt, rec.feed_id.name or 'Feed', trigger_label)
