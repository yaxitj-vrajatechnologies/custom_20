from odoo import fields, models


class AiProviderConfig(models.Model):
    """Simple configuration record to store which AI provider is used
    to generate Email Marketing templates.

    Only one provider is active at a time, selected using a Selection
    field. The API key is stored per provider so switching providers
    does not erase previously saved keys.
    """
    _name = 'ai.provider.config'
    _description = 'AI Provider Configuration'
    _rec_name = 'ai_provider'

    name = fields.Char(default='AI Provider Settings', required=True)

    ai_provider = fields.Selection(
        selection=[
            ('openai', 'OpenAI (ChatGPT)'),
            ('anthropic', 'Anthropic (Claude)'),
            ('gemini', 'Google Gemini'),
        ],
        string="Active AI Provider",
        default='openai',
        required=True,
    )

    openai_api_key = fields.Char(string="OpenAI API Key")
    anthropic_api_key = fields.Char(string="Anthropic API Key")
    gemini_api_key = fields.Char(string="Gemini API Key")

    openai_model = fields.Selection(
        selection=[
            ('gpt-4.1', 'GPT-4.1'),
            ('gpt-4.1-mini', 'GPT-4.1 Mini'),
            ('gpt-5', 'GPT-5'),
            ('gpt-5-mini', 'GPT-5 Mini'),
            ('gpt-5.4', 'GPT-5.4'),
            ('gpt-5.4-mini', 'GPT-5.4 Mini'),
        ],
        default='gpt-5',
    )
    anthropic_model = fields.Selection(
        selection=[
            # Active models only — Source: platform.claude.com/docs/en/about-claude/model-deprecations
            ('claude-opus-4-8',           'Claude Opus 4.8 (Latest, Most Capable)'),
            ('claude-opus-4-7',           'Claude Opus 4.7'),
            ('claude-opus-4-6',           'Claude Opus 4.6'),
            ('claude-sonnet-4-6',         'Claude Sonnet 4.6'),
            ('claude-haiku-4-5-20251001', 'Claude Haiku 4.5 (Fast & Lightweight)'),
        ],
        string='Claude Model',
        default='claude-sonnet-4-6',
        required=False,
        help='Select the Claude model to use when the Claude provider is active.\n'
             'Opus → most capable; Sonnet → balanced; Haiku → fast & lightweight.\n'
             'All models are currently ACTIVE on the Anthropic API (June 2026).\n'
             'Ref: https://platform.claude.com/docs/en/about-claude/model-deprecations',
    )
    claude_max_tokens = fields.Integer(
        string="Max Tokens",
        default=8001,
        help="Maximum number of tokens Claude is allowed to generate in a "
             "single response. Only used when Anthropic (Claude) is the "
             "active provider.",
    )
    gemini_model =  fields.Selection(
        selection=[
            ('gemini-3.5-flash', 'Gemini 3.5 Flash'),
            ('gemini-3.1-pro-preview', 'Gemini 3.1 Pro (High)'),
            ('gemini-2.5-flash', 'Gemini 2.5 Flash'),
            ('gemini-2.5-pro', 'Gemini 2.5 Pro'),
            ('gemini-flash-latest', 'Gemini Flash (Latest)'),
            ('gemini-pro-latest', 'Gemini Pro (Latest)'),
        ],
        string='Gemini Model',
        default='gemini-3.5-flash',
        required=False,
        help='Select the Gemini model to use when the Gemini provider is active.',
    )

    active = fields.Boolean(default=True)

    def get_provider_credential(self):
        """Return the API key that matches the currently selected
        provider on this record.
        """
        self.ensure_one()
        if self.ai_provider == 'openai':
            return self.openai_api_key, self.openai_model
        if self.ai_provider == 'anthropic':
            return self.anthropic_api_key, self.anthropic_model
        return self.gemini_api_key, self.gemini_model
