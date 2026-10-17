# -*- coding: utf-8 -*-
from odoo import models, fields, api


class DynamicPricingLog(models.Model):
    _inherit = 'vraja.ai.log'

    vraja_common_log_store = fields.Selection(
        selection_add=[('dynamic_pricing', 'Dynamic Pricing with AI')]
    )
    dp_log_message = fields.Text(string='Log Message')
    dp_total_products = fields.Integer(string='Products Analysed', readonly=True)
    dp_total_tokens = fields.Integer(string='Total Tokens Used', default=0)

    # NEW: applied status
    dp_applied = fields.Boolean(string='Applied to Pricelists', default=False)
    dp_pricelists_updated = fields.Integer(string='Pricelist Items Updated')

    # NEW: computed decision counters
    dp_increase_count = fields.Integer(string='Increased', compute='_compute_dp_counts', store=True)
    dp_decrease_count = fields.Integer(string='Decreased', compute='_compute_dp_counts', store=True)
    dp_hold_count = fields.Integer(string='Held', compute='_compute_dp_counts', store=True)
    dp_skip_count = fields.Integer(string='Skipped', compute='_compute_dp_counts', store=True)


    @api.depends('line_ids.dp_decision')
    def _compute_dp_counts(self):
        for rec in self:
            lines = rec.line_ids
            rec.dp_increase_count = len(lines.filtered(lambda l: l.dp_decision == 'increase'))
            rec.dp_decrease_count = len(lines.filtered(lambda l: l.dp_decision == 'decrease'))
            rec.dp_hold_count = len(lines.filtered(lambda l: l.dp_decision == 'hold'))
            rec.dp_skip_count = len(lines.filtered(lambda l: l.dp_decision == 'skip'))


class DynamicPricingLogLine(models.Model):
    _inherit = 'vraja.ai.log.line'

    dp_product_id = fields.Many2one('product.product', string='Product', readonly=True)
    dp_product_name = fields.Char(string='Product Name', readonly=True)
    dp_segment_name = fields.Char(string='Segment', readonly=True)
    dp_old_price = fields.Float(string='Current Price', readonly=True)
    dp_ai_suggested_price = fields.Float(string='AI Suggested Price', readonly=True)
    dp_decision = fields.Selection([
        ('increase', 'Increase'),   
        ('decrease', 'Decrease'),
        ('hold', 'Hold'),
        ('skip', 'Skip'),
    ], string='Decision', readonly=True)
    dp_margin_before = fields.Float(string='Margin Before (%)', readonly=True)
    dp_margin_after = fields.Float(string='Margin After (%)', readonly=True)
    dp_status = fields.Selection([
        ('success', 'Success'),
        ('skipped', 'Skipped'),
        ('failed', 'Failed'),
    ], string='Status', default='success', readonly=True)
