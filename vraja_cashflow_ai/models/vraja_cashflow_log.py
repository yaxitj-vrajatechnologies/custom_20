# -*- coding: utf-8 -*-
from odoo import fields, models


class VrajaAILogCashflow(models.Model):
    """Extends the common vraja.ai.log to add Cashflow AI specific fields."""
    _inherit = 'vraja.ai.log'

    # ── Selection extension ───────────────────────────────────────────────────
    vraja_common_log_store = fields.Selection(
        selection_add=[('cashflow', 'Cashflow AI')],
        ondelete={'cashflow': 'set null'},
    )

    # ── Link back to the analysis record ─────────────────────────────────────
    cashflow_analysis_id = fields.Many2one(
        'vraja.cashflow.analysis',
        string='Cashflow Analysis',
        ondelete='set null',
        readonly=True,
    )

    # ── Analysis period ────────────────────────────────────────────────────────
    date_from = fields.Date(string='Period From', readonly=True)
    date_to = fields.Date(string='Period To', readonly=True)

    # ── Financial snapshot at time of run ────────────────────────────────────
    bank_balance = fields.Float(string='Bank Balance', digits=(16, 2), readonly=True)
    inflow_30d = fields.Float(string='Total Inflows (Last 30d)', digits=(16, 2), readonly=True)
    outflow_30d = fields.Float(string='Total Outflows (Last 30d)', digits=(16, 2), readonly=True)
    avg_daily_net_outflow = fields.Float(string='Avg Daily Net Outflow', digits=(16, 4), readonly=True)

    # ── AI KPI results ────────────────────────────────────────────────────────
    cash_runway_days = fields.Integer(string='Cash Runway (Days)', readonly=True)
    zero_cash_date = fields.Date(string='Zero Cash Date (Projected)', readonly=True)
    runway_message = fields.Char(string='Runway Message', readonly=True)
    liquidity_status = fields.Char(string='Liquidity Status', readonly=True)
    liquidity_score = fields.Float(string='Liquidity Score (0-100)', digits=(6, 1), readonly=True)

    # ── LLM / token usage ────────────────────────────────────────────────────
    prompt_tokens = fields.Integer(string='Prompt Tokens', readonly=True)
    completion_tokens = fields.Integer(string='Completion Tokens', readonly=True)
    total_tokens = fields.Integer(string='Total Tokens', readonly=True)

    # ── Outcome fields ────────────────────────────────────────────────────────
    executive_summary = fields.Text(string='Executive Summary', readonly=True)
    error_message = fields.Text(string='Error Message', readonly=True)


class VrajaAILogLineCashflow(models.Model):
    """Extends the common vraja.ai.log.line with cashflow-specific metric fields."""
    _inherit = 'vraja.ai.log.line'

    metric_name = fields.Char(string='Metric')
    metric_value = fields.Float(string='Value', digits=(16, 2))
    metric_currency = fields.Boolean(string='Is Currency?')
