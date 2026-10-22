# -*- coding: utf-8 -*-
"""
vraja_bank_recon_wizard.py
============================
Transient model for the Bank Reconciliation AI wizard.

The wizard provides an alternative, form-based entry point to trigger an AI
reconciliation analysis. While the primary workflow uses the OWL dashboard
(vraja.bank.recon.dashboard.data.run_full_ai_analysis), this wizard allows
accountants to scope the analysis to a specific date range — useful for
reconciling a historical period or a specific bank statement import.

Wizard workflow:
    1. User opens the wizard, selects a bank journal and a date range.
    2. On "Generate Analysis", the wizard:
        a. Fetches all unreconciled statement lines within the date range.
        b. Fetches all unreconciled journal items (account.move.line) up to date_to.
        c. Builds an AI prompt and calls OpenAI to classify each statement line.
        d. Persists the results as a vraja.bank.recon.analysis record.
        e. Redirects the user to the analysis form view for review.

Dependency:
    Requires a valid OpenAI API key in vraja.ai.config. Raises UserError if absent.

"""

from odoo import models, fields, api
from odoo.exceptions import UserError
import requests
import json
import logging

_logger = logging.getLogger(__name__)


class VrajaBankReconWizard(models.TransientModel):
    """
    Transient wizard for date-range-scoped AI bank reconciliation.

    TransientModel records are automatically cleaned up by the Odoo vacuum
    scheduler — no manual deletion needed. The wizard's purpose is to collect
    user input and trigger the AI reconciliation pipeline for a specific period.

    Fields:
        card_id   : Links the resulting analysis to a vraja.ai.card entry.
        journal_id: The bank journal to analyse (restricted to bank-type journals).
        date_from : Start of the date range for filtering statement lines.
        date_to   : End of the date range (defaults to today).
    """

    _name = 'vraja.bank.recon.wizard'
    _description = 'Bank Reconciliation AI Wizard'

    # ── Input fields ──────────────────────────────────────────────────────────
    card_id = fields.Many2one(
        'vraja.ai.card',
        string='AI Card',
        required=True,
        help="The vraja.ai.card record to link the resulting analysis to. "
             "Determines which AI tool entry appears in the AI hub."
    )
    journal_id = fields.Many2one(
        'account.journal',
        string='Bank Journal',
        required=True,
        domain=[('type', '=', 'bank')],
        help="Bank journal to analyse. Only bank-type journals are shown."
    )
    date_from = fields.Date(
        string='Date From',
        required=True,
        help="Start date for filtering unreconciled bank statement lines."
    )
    date_to = fields.Date(
        string='Date To',
        default=fields.Date.context_today,
        required=True,
        help="End date for filtering. Statement lines with date > date_to are excluded. "
             "Defaults to today to match the most common use-case."
    )

    def action_generate_analysis(self):
        """
        Execute the AI-assisted reconciliation pipeline for the wizard's date range.

        This method replicates a simplified version of the 7-step pipeline from
        vraja.bank.recon.dashboard.data.run_full_ai_analysis(), scoped to the
        wizard's journal and date range. It is a synchronous call (no bus events
        or stepper animation) appropriate for the wizard context.

        Steps:
            1. Planning & Data Collection
                 – Fetch unreconciled statement lines within [date_from, date_to].
                 – Raise UserError if no lines found (prevents empty AI calls).

            2. Internal Review
                 – Fetch unreconciled journal items (account.move.line) on reconcilable
                   accounts with date <= date_to and state = 'posted'.
                 – These are the candidates the AI will attempt to match against.

            3. AI Call (OpenAI)
                 – Build a system prompt describing the output schema.
                 – Build a user prompt containing the JSON-serialised statement and AML data.
                 – POST to OpenAI with the configured model and API key.
                 – Parse the JSON response, handling both list and dict-wrapped formats.
                 – Raises UserError on communication failure or JSON parse error.

            4. Persist Analysis
                 – Create a vraja.bank.recon.analysis header record.
                 – Bulk-create all vraja.bank.recon.analysis.line child records
                   from the AI response.

            5. Redirect
                 – Return an ir.actions.act_window action to open the newly created
                   analysis record in form view for the accountant to review.

        Response format handling:
            The AI may return either a plain JSON array or a dict with a 'statements' key.
            Both are handled. Markdown code fences (```json...```) are also stripped.

        Raises:
            UserError: If no unreconciled statement lines exist for the selected period.
            UserError: If OpenAI API key is not configured in vraja.ai.config.
            UserError: If the API call fails or the response cannot be parsed as JSON.

        Returns:
            dict: ir.actions.act_window action to open the resulting analysis form.
        """
        self.ensure_one()

        # ── Step 1: Planning & Data Collection ───────────────────────────────
        # Fetch unreconciled statement lines within the wizard's date range.
        # The date range allows this wizard to target historical bank statement imports.
        statement_lines = self.env['account.bank.statement.line'].search([
            ('journal_id', '=', self.journal_id.id),
            ('date', '>=', self.date_from),
            ('date', '<=', self.date_to),
            ('is_reconciled', '=', False),
        ])

        if not statement_lines:
            # Fail fast with a clear message — an empty AI call wastes tokens.
            raise UserError("No unreconciled bank statement lines found for the selected period.")

        # ── Step 2: Internal Review ───────────────────────────────────────────
        # Fetch unreconciled AMLs on reconcilable accounts, up to date_to.
        # We do NOT filter by date_from because older open items may still match
        # newer bank statement lines (e.g., delayed payment of an old invoice).
        aml_records = self.env['account.move.line'].search([
            ('account_id.reconcile', '=', True),    # A/R or A/P accounts only
            ('reconciled', '=', False),              # Not yet fully reconciled
            ('date', '<=', self.date_to),            # On or before the analysis end date
            ('parent_state', '=', 'posted'),         # Confirmed journal entries only
        ])  # Limit intentionally removed; a production implementation may add it for token safety.

        # Build the JSON payload for the AI prompt.
        # Keep payloads concise — only fields the AI needs for matching decisions.
        stm_data = []
        for stm in statement_lines:
            stm_data.append({
                'id': stm.id,
                'date': str(stm.date),
                'amount': stm.amount,
                'payment_ref': stm.payment_ref or '',
                'partner': stm.partner_id.name if stm.partner_id else '',
            })

        aml_data = []
        for aml in aml_records:
            aml_data.append({
                'id': aml.id,
                'date': str(aml.date),
                'amount_residual': aml.amount_residual,  # Outstanding balance
                'name': aml.name or '',
                'ref': aml.ref or '',
                'partner': aml.partner_id.name if aml.partner_id else '',
            })

        # ── Step 3: AI Call ───────────────────────────────────────────────────
        # Supports both OpenAI and Claude (Anthropic) based on the active provider
        # configured in vraja.ai.config. Raises UserError if no key is available.
        config = self.env['vraja.ai.config'].sudo().search([], limit=1)

        # Detect which provider is active and whether it has a key.
        ai_provider = config.ai_provider if config else 'openai'
        use_openai = (ai_provider == 'openai') and bool(config and config.openai_api_key)
        use_claude = (ai_provider == 'claude') and bool(config and config.claude_api_key)

        if not (use_openai or use_claude):
            raise UserError(
                'No AI API key configured.\n\n'
                'Please set your OpenAI or Claude API key in:\n'
                'Vraja AI → Configuration → AI Configuration.'
            )

        # System prompt: defines the AI's role and the output schema.
        system_prompt = """
        You are an elite AI bank reconciliation Agent for Odoo.
        Your goal is to parse Bank Statement Lines and match them to Unreconciled Journal Items.

        Output must be valid JSON ONLY.

        Categories of outcome for each Bank Statement Line:
        1. 'matched': Found exact or highly probable matched A/R, A/P. Include AML IDs in 'matched_aml_ids'.
        2. 'rule': Regular predictable pattern (like bank fees, SMS charges). No exact AML matched, but fits a known rule.
        3. 'check': Cannot find match, flag for user manual review.

        JSON Format requested:
        [
            {
                "statement_id": <int>,
                "status": "<matched|rule|check>",
                "ai_explanation": "<string explanation>",
                "matched_aml_ids": [<int list of aml ids if matched>]
            },...
        ]
        """

        # User prompt: the actual bank statement and AML data serialised as JSON.
        user_prompt = "Bank Statements:\n" + json.dumps(stm_data) + "\n\nUnreconciled Journal Items:\n" + json.dumps(aml_data)

        try:
            import requests

            if use_claude:
                # ── Claude (Anthropic) Messages API ───────────────────────────
                # Endpoint : POST https://api.anthropic.com/v1/messages
                # Auth     : x-api-key header (NOT 'Authorization: Bearer')
                # Version  : anthropic-version: 2023-06-01 (mandatory)
                # System   : top-level 'system' key — NOT inside the messages array
                # max_tokens: required field for Claude
                # Ref      : https://docs.anthropic.com/en/api/overview
                claude_model = config.claude_llm_model or 'claude-sonnet-4-6'
                payload = {
                    'model': claude_model,
                    'max_tokens': 8192,
                    'system': system_prompt,
                    'messages': [
                        {'role': 'user', 'content': user_prompt},
                    ],
                }
                response = requests.post(
                    'https://api.anthropic.com/v1/messages',
                    json=payload,
                    headers={
                        'x-api-key': config.claude_api_key,
                        'anthropic-version': '2023-06-01',
                        'content-type': 'application/json',
                    },
                    timeout=120,
                )
                response.raise_for_status()
                # Claude response: {'content': [{'type': 'text', 'text': '<str>'}], ...}
                ai_text = response.json()['content'][0]['text']

            else:
                # ── OpenAI Chat Completions API (existing logic — 100% untouched) ────
                payload = {
                    "model": config.llm_model or 'gpt-4o',
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    # Enable structured JSON output mode for GPT-4 models.
                    "response_format": {"type": "json_object"} if 'gpt-4' in (config.llm_model or '') else None,
                }
                # For models that don't support json_object natively, append a JSON instruction.
                if payload.get('response_format') is None:
                    payload['messages'][0]['content'] += "\nEnsure you output standard JSON."

                response = requests.post(
                    "https://api.openai.com/v1/chat/completions",
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {config.openai_api_key}",
                        "Content-Type": "application/json",
                    },
                    timeout=120,
                )
                response.raise_for_status()
                ai_text = response.json()["choices"][0]["message"]["content"]

            # ── Shared response parsing (identical for both providers) ─────────
            # Strip optional markdown code fence if model wraps JSON in ```...```.
            if ai_text.startswith('```'):
                ai_text = ai_text.split('\n', 1)[-1].rsplit('```', 1)[0]

            # Parse the AI response.
            parsed_data = json.loads(ai_text)

            # Handle models that wrap the array in a dict with a 'statements' key.
            if isinstance(parsed_data, dict) and 'statements' in parsed_data:
                parsed_data = parsed_data['statements']

        except Exception as e:
            # Provide a clear, actionable error message to the accountant.
            # Identifies which provider failed and includes raw AI text if available.
            provider_name = 'Claude (Anthropic)' if use_claude else 'OpenAI'
            raise UserError(
                f"Error communicating with {provider_name} or parsing response: {str(e)}\n\n"
                f"{ai_text if 'ai_text' in locals() else ''}"
            )

        # ── Step 4: Persist Analysis ──────────────────────────────────────────
        # Create the analysis header record linking to the wizard's card and journal.
        # state='done' marks it immediately as a completed run.
        analysis_record = self.env['vraja.bank.recon.analysis'].create({
            'card_id': self.card_id.id,
            'journal_id': self.journal_id.id,
            'state': 'done',
        })

        # Bulk-build One2many line vals using the ORM (0, 0, vals) syntax.
        # (6, 0, ids) on matched_aml_ids replaces the set with the AI-provided IDs.
        line_vals = []
        for match in parsed_data:
            line_vals.append((0, 0, {
                'statement_line_id': match.get('statement_id'),
                'status': match.get('status'),
                'ai_explanation': match.get('ai_explanation'),
                'matched_aml_ids': [(6, 0, match.get('matched_aml_ids', []))],
            }))

        analysis_record.write({'line_ids': line_vals})

        # ── Step 5: Redirect to analysis form view ────────────────────────────
        # Open the newly created analysis record in form view so the accountant
        # can review AI decisions before confirming reconciliation.
        return {
            'name': 'AI Bank Reconciliation Review',
            'type': 'ir.actions.act_window',
            'res_model': 'vraja.bank.recon.analysis',
            'res_id': analysis_record.id,
            'view_mode': 'form',
            'target': 'current',
        }
