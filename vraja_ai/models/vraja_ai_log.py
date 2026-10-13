# -*- coding: utf-8 *-*
from odoo import models, fields, api
from datetime import timedelta


class VrajaAILog(models.Model):
    _name = 'vraja.ai.log'
    _description = 'Vraja AI Log'
    _order = 'run_date desc'

    name = fields.Char(string='Reference', readonly=True, default='New')
    run_date = fields.Datetime(string='Run Date', default=fields.Datetime.now, readonly=True)
    vraja_common_log_store = fields.Selection(selection=[], string='AI Feature')
    status = fields.Selection([
        ('success', 'Success'),
        ('failed', 'Failed'),
    ], string='Status', readonly=True)
    line_ids = fields.One2many('vraja.ai.log.line', 'log_id', string='Log Lines')
    ai_provider = fields.Selection([
        ('openai', 'OpenAI'),
        ('claude', 'Claude'),
        ('gemini', 'Gemini'),
    ], string='AI Provider', help="AI provider used to perform the analysis")

    ai_llm_model = fields.Char(string='LLM Model')

    def _cron_delete_old_ai_logs(self):
        """Delete AI logs older than 30 days."""
        old_date = fields.Datetime.now() - timedelta(days=30)

        old_logs = self.sudo().search([('run_date', '<', old_date)])
        old_logs.unlink()

    @api.model_create_multi
    def create(self, vals_list):
        config = self.env['vraja.ai.config'].sudo().search([], limit=1)
        if config:
            provider = config.ai_provider or 'openai'
            if provider == 'claude':
                model = config.claude_llm_model or 'claude-sonnet-4-6'
            elif provider == 'gemini':
                model = config.gemini_llm_model or 'gemini-3.5-flash'
            else:
                model = config.llm_model or ''
        else:
            provider, model = 'openai', ''

        for vals in vals_list:
            if not vals.get('name') or vals['name'] == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('vraja.ai.log')
            # Auto-set provider and model if not explicitly passed
            if not vals.get('ai_provider'):
                vals['ai_provider'] = provider
            if not vals.get('ai_llm_model'):
                vals['ai_llm_model'] = model

        return super().create(vals_list)


class VrajaAILogLine(models.Model):
    _name = 'vraja.ai.log.line'
    _description = 'Vraja AI Log Line'

    log_id = fields.Many2one(
        'vraja.ai.log',
        string='Log',
        ondelete='cascade',
    )
