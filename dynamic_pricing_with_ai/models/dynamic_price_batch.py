# -*- coding: utf-8 -*-
import json
from odoo import models, fields,api
from odoo.exceptions import UserError

class DpBatch(models.Model):
    _name = 'vraja.dp.batch'
    _description = 'Dynamic Pricing AI Batch'
    _order = 'batch_index asc'
    _rec_name = 'name'

    # ── Identification ────────────────────────────────────────────────────────
    name = fields.Char(string='Batch',help='Auto-generated name, e.g. "Batch 1 of 3".')
    card_id = fields.Many2one('vraja.ai.card', string='Card', ondelete='cascade',
                              help='The Dynamic Pricing card this batch belongs to.')

    # ── State ─────────────────────────────────────────────────────────────────
    state = fields.Selection([
        ('draft',   'Draft'),    # Waiting to be picked up by cron
        ('running', 'Running'),  # Currently being processed by cron
        ('done',    'Done'),     # Successfully processed
        ('error','Error')
    ], default='draft', string='State')

    # ── Position in the batch sequence ───────────────────────────────────────
    batch_index    = fields.Integer(string='Batch #',
                                    help='1-based position in the full batch sequence.')
    total_batches  = fields.Integer(string='Total Batches',
                                    help='Total number of batches for this card run.')
    products_count = fields.Integer(string='Products',
                                    help='Number of product rows in this batch.')

    # ── Data ──────────────────────────────────────────────────────────────────
    csv_rows = fields.Text(
        string='CSV Rows',
        help='CSV slice for this batch (header + data rows). Uploaded to OpenAI on processing.',
    )
    result_json = fields.Text(
        string='Result JSON',
        help='Parsed AI result for this batch. Stored for audit purposes after processing.',
    )
    file_id = fields.Char(
        string='OpenAI File ID',
        help='Temporary file ID from OpenAI Files API. Cleared after the AI call completes.',
    )
    error_message = fields.Text(
        string='Error',
        help='Populated when the batch fails. Batch is reset to draft for the next cron retry.',
    )
    segment_rules_json = fields.Text(
        string='Segment Rules',
        help='Snapshot of segment configuration at the time this batch was created.',
    )
    # ── Computed Stats ────────────────────────────────────────────────────────
    segment_count = fields.Integer(
        string='Segments',
        compute='_compute_batch_stats',
        store=False,
    )
    result_count = fields.Integer(
        string='Total Rows Analysed',
        compute='_compute_batch_stats',
        store=False,
    )

    @api.depends('segment_rules_json', 'result_json')
    def _compute_batch_stats(self):
        for rec in self:
            try:
                rec.segment_count = len(json.loads(rec.segment_rules_json or '[]'))
            except Exception:
                rec.segment_count = 0
            try:
                rec.result_count = len(json.loads(rec.result_json or '[]'))
            except Exception:
                rec.result_count = 0

    def action_run_batch_manually(self):
        self.ensure_one()
        if self.state != 'draft':
            raise UserError('Only draft batches can be run manually.')
        self.env['vraja.ai.card'].action_cron_dp_run_analysis(batch_id=self.id)
