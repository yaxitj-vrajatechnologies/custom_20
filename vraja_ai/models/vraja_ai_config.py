# -*- coding: utf-8 -*-
from odoo import fields, models


class VrajaAIConfig(models.Model):
    """
    Central AI provider configuration for all Vraja AI modules.

    Supports the following AI providers:
        - OpenAI  (ChatGPT / GPT series)
        - Claude  (Anthropic)
        - Google Gemini

    The ``ai_provider`` radio field controls which credential block is
    shown in the form view. All downstream callers should read
    ``ai_provider`` first to decide which API to invoke.
    """

    _name = 'vraja.ai.config'
    _description = 'VRAJA AI Configuration'
    _rec_name = 'ai_provider'

    name = fields.Char(string="Name")

    # ── Provider selector ────────────────────────────────────────────────────
    ai_provider = fields.Selection(
        selection=[
            ('openai', 'OpenAI (ChatGPT)'),
            ('claude', 'Claude (Anthropic)'),
            ('gemini', 'Google Gemini'),
        ],
        string='AI Provider',
        default='openai',
        required=True,
        help="Select the AI provider to use for all Vraja AI features.\n"
             "OpenAI – uses ChatGPT / GPT series models.\n"
             "Claude – uses Anthropic's Claude series models.\n"
             "Gemini – uses Google's Gemini models.",
    )

    # ── OpenAI credentials ───────────────────────────────────────────────────
    # Kept 100% untouched; existing calling code uses these directly.
    openai_api_key = fields.Char(string='ChatGPT API Key')
    llm_model = fields.Selection(
        selection=[
            ('gpt-4.1', 'GPT-4.1'),
            ('gpt-4.1-mini', 'GPT-4.1 Mini'),
            ('gpt-5', 'GPT-5'),
            ('gpt-5-mini', 'GPT-5 Mini'),
            ('gpt-5.4', 'GPT-5.4'),
            ('gpt-5.4-mini', 'GPT-5.4 Mini'),
        ],
        string='OpenAI Model',
        default='gpt-5.4',
        required=False,
        help='Select the OpenAI model to use when the OpenAI provider is active.',
    )

    # ── Claude (Anthropic) credentials ──────────────────────────────────────
    # Claude Messages API endpoint: POST https://api.anthropic.com/v1/messages
    # Required headers: x-api-key, anthropic-version, content-type
    # Ref: https://docs.anthropic.com/en/api/overview
    claude_api_key = fields.Char(
        string='Claude API Key',
        help='Anthropic API key for Claude models.\n'
             'Obtain from: https://platform.claude.com/settings/keys',
    )
    claude_llm_model = fields.Selection(
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
        string='Max Tokens',
        default=8192,
        required=True,
        help='The maximum number of tokens to generate before stopping.\n'
             'Anthropic requires this parameter to be explicitly set.',
    )

    # ── Google Gemini credentials ────────────────────────────────────────────
    # Gemini API endpoint: POST https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent
    # Required headers: x-goog-api-key, Content-Type
    gemini_api_key = fields.Char(
        string='Gemini API Key',
        help='Google Gemini API key.\n'
             'Obtain from: https://aistudio.google.com/app/apikey',
    )
    gemini_llm_model = fields.Selection(
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
