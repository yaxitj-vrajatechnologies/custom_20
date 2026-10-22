# -*- coding: utf-8 -*-
"""
vraja_bank_recon_dashboard_data.py
===================================
Central server-side controller for the Bank Reconciliation AI Dashboard.

This model acts as a "service layer" â€” it has no stored fields of its own and
exists purely to expose RPC-callable methods invoked by the OWL dashboard
component (bank_recon_dashboard.js) over JSON-RPC.

Responsibilities:
    1. KPI aggregation  â€“ gather totals/rates from account.bank.statement.line
                          and vraja.bank.recon.analysis.line for the header cards.
    2. 7-step AI agent  â€“ orchestrate the full reconciliation pipeline:
                          planning â†’ data collection â†’ internal review â†’
                          auto-matching â†’ rule application â†’ AI categorization â†’
                          final persistence.
    3. Confirm & Review â€“ auto-reconcile matched/rule lines and redirect the user
                          to the native Odoo bank reconciliation widget.
    4. Helpers          â€“ serialise analysis records to JSON-safe dicts and write
                          structured audit logs to vraja.ai.log.

Author : Vraja Technologies
Version: 19.0
"""

from odoo import models, fields, api
import logging
import json

_logger = logging.getLogger(__name__)


class VrajaBankReconDashboardData(models.Model):
    """
    Service-layer model for the Bank Reconciliation AI Dashboard.

    This model holds NO database columns; all methods are @api.model and are
    called exclusively via JSON-RPC from the OWL frontend.

    Model name is intentionally verbose for easy traceability in RPC logs.
    """

    _name = 'vraja.bank.recon.dashboard.data'
    _description = 'Bank Reconciliation Dashboard Statistics'

    # -------------------------------------------------------------------------
    # SECTION 1 â€“ Basic KPI data (used on initial load)
    # -------------------------------------------------------------------------

    @api.model
    def get_dashboard_data(self):
        """
        Return a comprehensive KPI dict consumed by the OWL dashboard on load.

        This is the FIRST server call made by the OWL component's onWillStart hook.
        It consolidates all data the idle-state dashboard needs into a single
        RPC round-trip to minimise page-load latency.

        Data returned:
            total_lines          (int)  â€“ Total bank statement lines (all bank journals).
            reconciled_lines     (int)  â€“ Lines already reconciled.
            unreconciled_lines   (int)  â€“ Lines still pending (total - reconciled).
            ai_matched           (int)  â€“ All-time count of 'matched' analysis lines.
            rule_matched         (int)  â€“ All-time count of 'rule' analysis lines.
            time_saved_formatted (str)  â€“ Human-readable time saved, e.g. "2h 15m".
                                          Calculated at 2 minutes per AI-processed transaction.
            reconciliation_rate  (int)  â€“ Percentage of reconciled lines (0-100).
            last_analysis        (dict|None) â€“ Serialised last completed analysis,
                                              None if no analysis has run yet.
            bank_journals        (list) â€“ List of {id, name} dicts for bank journals.

        Business Notes:
            - is_reconciled on account.bank.statement.line is a computed field.
            - time_saved is a heuristic: 2 min manual work saved per AI-processed line.
            - last_analysis is pre-loaded so the dashboard auto-restores the last run.

        Returns:
            dict: KPI summary as described above.
        """
        BankStatementLine = self.env['account.bank.statement.line']
        AIRecLine = self.env['vraja.bank.recon.analysis.line']

        # -- Count total vs reconciled bank statement lines -------------------
        # Domain restricts to bank-type journals only (excludes cash/credit-card).
        total_lines = BankStatementLine.search_count(
            [('journal_id.type', 'in', ['bank'])]
        )
        reconciled_lines = BankStatementLine.search_count(
            [('journal_id.type', 'in', ['bank']), ('is_reconciled', '=', True)]
        )
        # Derived to avoid an extra DB call.
        unreconciled_lines = total_lines - reconciled_lines

        # -- Fetch AI vs rule-based counts from analysis lines -----------------
        # These accumulate across ALL historical runs â€” an all-time total.
        ai_matched_count = AIRecLine.search_count([('status', '=', 'matched')])
        rule_matched_count = AIRecLine.search_count([('status', '=', 'rule')])

        # -- Estimate time saved (2 minutes per AI/rule processed transaction) -
        total_ai_processed = ai_matched_count + rule_matched_count
        time_saved_minutes = total_ai_processed * 2
        hours_saved = time_saved_minutes // 60
        minutes_saved = time_saved_minutes % 60

        # -- Load the most recent completed analysis for dashboard pre-population
        # The OWL component restores the 'results' phase if this is not None,
        # so users always see the last run without re-triggering the agent.
        Analysis = self.env['vraja.bank.recon.analysis']
        last_analysis = Analysis.search([('state', '=', 'done')], order='run_date desc', limit=1)
        last_analysis_data = None
        if last_analysis:
            last_analysis_data = self._serialize_analysis(last_analysis)

        # -- Fetch bank journals for the journal picker ------------------------
        # search_read avoids browse overhead; returns only id + name fields.
        bank_journals = self.env['account.journal'].search_read(
            [('type', '=', 'bank')],
            ['id', 'name'],
            order='name'
        )

        return {
            'total_lines': total_lines,
            'reconciled_lines': reconciled_lines,
            'unreconciled_lines': unreconciled_lines,
            'ai_matched': ai_matched_count,
            'rule_matched': rule_matched_count,
            'time_saved_formatted': f"{hours_saved}h {minutes_saved}m",
            # Guard against division-by-zero when no lines exist yet.
            'reconciliation_rate': round(reconciled_lines / total_lines * 100) if total_lines else 0,
            'last_analysis': last_analysis_data,
            'bank_journals': bank_journals,
        }

    # -------------------------------------------------------------------------
    # SECTION 2 â€“ 7-Step AI Agent Runner (main dashboard action)
    # -------------------------------------------------------------------------

    # STEPS defines the canonical reconciliation pipeline stages shared between
    # Python (bus events) and JavaScript (stepper animation).
    # Tuple format: (step_number, step_key, step_label, step_description)
    # âš ï¸� Keep in sync with STEPS constant in bank_recon_dashboard.js
    #    and accordion panels in bank_recon_dashboard.xml.
    STEPS = [
        (1, 'planning',          'ðŸ§  Planning',           'Analysing journal context and defining strategy'),
        (2, 'data_collection',   'ðŸ“¥ Data Collection',    'Fetching unreconciled bank statement lines'),
        (3, 'internal_review',   'ðŸ”� Internal Review',    'Loading open journal items and invoices'),
        (4, 'auto_matching',     'âš™ï¸� Auto Matching',      'Running exact and fuzzy amount matching'),
        (5, 'rule_application',  'ðŸ“‹ Rule Application',   'Applying historical and pre-defined rules'),
        (6, 'categorization',    'ðŸ—‚ï¸� Categorization',     'Sorting results into Matched / Rule / Check'),
        (7, 'final_analysis',    'âœ… Final Analysis',      'Generating analysis record and AI log'),
    ]

    def _publish_step(self, channel, step_num, step_key, step_label, step_desc, status='active'):
        """
        Publish a real-time bus event so the OWL stepper can animate progress.

        Uses Odoo's long-polling bus (bus.bus) to push a bank_recon_step event
        to the user-specific channel. The OWL component subscribes to the pattern
        'bank_recon_dashboard_{uid}' and updates the stepper reactively on receipt.

        Bus event payload:
            step        (int) â€“ 1-based step number (1-7).
            key         (str) â€“ Step key matching the OWL STEPS constant.
            label       (str) â€“ Short display label, e.g. 'ðŸ“¥ Data Collection'.
            description (str) â€“ Text for the live status bar below the stepper.
            status      (str) â€“ 'active' | 'done' | 'error'.

        Design: Bus failures are caught as warnings â€” the analysis continues even if
        the UI update fails (e.g., user navigated away from the dashboard).

        Args:
            channel    (str): Bus channel, typically 'bank_recon_dashboard_{uid}'.
            step_num   (int): Step number 1-7.
            step_key   (str): Unique step identifier.
            step_label (str): Short display label.
            step_desc  (str): Longer description for the live status bar.
            status     (str): 'active' while processing, 'done' on completion.
        """
        try:
            self.env['bus.bus']._sendone(
                channel,
                'bank_recon_step',
                {
                    'step': step_num,
                    'key': step_key,
                    'label': step_label,
                    'description': step_desc,
                    'status': status,   # active | done | error
                }
            )
        except Exception as e:
            _logger.warning("BankRecon: bus publish failed â€“ %s", e)

    @api.model
    def run_full_ai_analysis(self, journal_id):
        """
        Orchestrate the complete 7-step AI bank reconciliation pipeline.

        This is the PRIMARY RPC entry point triggered by the 'Run AI Agent' button
        on the OWL dashboard. All seven steps run sequentially; a bus event is
        published at the start and end of each step so the OWL stepper can animate.

        Pipeline overview:
            Step 1 â€“ Planning        : Validate journal; detect AI vs rules-only mode.
            Step 2 â€“ Data Collection : Fetch unreconciled statement lines; group by statement.
            Step 3 â€“ Internal Review : Load unreconciled AMLs on reconcilable accounts.
            Step 4 â€“ Auto Matching   : Build amount index; exact-match each statement line.
            Step 5 â€“ Rule Application: Apply Odoo account.reconcile.model rules to 'check' lines.
            Step 6 â€“ Categorization  : Optional OpenAI call for AI-assisted final classification.
            Step 7 â€“ Final Analysis  : Persist analysis + lines; write AI log; serialize results.

        AI vs Rules-only mode:
            - openai_api_key set in vraja.ai.config â†’ Step 6 calls OpenAI (AI mode).
            - No key â†’ Steps 4+5 results used directly (rules-only mode).

        Args:
            journal_id (int): ID of the account.journal record (must be type='bank').

        Returns:
            dict: On success:
                {
                    'success'       : True,
                    'analysis_id'   : int,   # Persisted analysis record ID
                    'analysis_name' : str,   # e.g. "BRA/2026/00015"
                    'results'       : dict,  # Serialised matched/rule/check lists
                    'step_data'     : dict,  # Per-step accordion drill-down data
                }
                On failure:
                {'success': False, 'error': str}
        """
        # User-specific bus channel so events reach only the triggering user.
        channel = f'bank_recon_dashboard_{self.env.user.id}'

        # step_payloads accumulates drill-down table data (step2â€¦step5).
        # step1, step6, step7 don't have tabular accordion drill-downs.
        step_payloads = {}

        # -- STEP 1: Planning -------------------------------------------------
        # Validate the selected journal and determine AI vs rules-only mode.
        step = self.STEPS[0]
        self._publish_step(channel, *step, status='active')

        journal = self.env['account.journal'].browse(journal_id)
        if not journal.exists() or journal.type != 'bank':
            # Return immediately â€” no point continuing with an invalid journal.
            return {'success': False, 'error': 'Invalid bank journal selected.'}

        # sudo() because regular users may not have read access to the config model.
        config = self.env['vraja.ai.config'].sudo().search([], limit=1)
        # Determine AI mode based on the active provider and its respective key.
        _ai_provider_step1 = config.ai_provider if config else 'openai'
        if _ai_provider_step1 == 'claude':
            use_ai = bool(config and config.claude_api_key)
        elif _ai_provider_step1 == 'gemini':
            use_ai = bool(config and config.gemini_api_key)
        else:
            use_ai = bool(config and config.openai_api_key)

        self._publish_step(channel, *step, status='done')

        # -- STEP 2: Data Collection -------------------------------------------
        # Fetch every unreconciled statement line for the chosen journal.
        # Lines are grouped by bank statement for the accordion UI and flattened
        # into stm_data for AI/rule processing.
        step = self.STEPS[1]
        self._publish_step(channel, *step, status='active')

        statement_lines = self.env['account.bank.statement.line'].search([
            ('journal_id', '=', journal_id),
            ('is_reconciled', '=', False),
        ])

        # stm_data      : flat list of dicts, one per line (used in Steps 4-6).
        # statements_dict: grouped by statement ID for the accordion table.
        stm_data = []
        statements_dict = {}
        for stm in statement_lines:
            stmt_id = stm.statement_id.id if stm.statement_id else False
            stmt_name = stm.statement_id.name if stm.statement_id else 'Direct Line'
            # Use statement date if available; fall back to line's own date.
            stmt_date = str(stm.statement_id.date) if (stm.statement_id and stm.statement_id.date) else str(stm.date)

            # Build statements_dict keyed by statement ID (first-seen wins).
            if stmt_id and stmt_id not in statements_dict:
                statements_dict[stmt_id] = {
                    'id': stmt_id,
                    'reference': stmt_name,
                    'date': stmt_date,
                    'balance_start': stm.statement_id.balance_start or 0.0,
                    'balance_end_real': stm.statement_id.balance_end_real or 0.0,
                    'line_count': 0,
                }
            # Increment per-statement line count for the UI summary row.
            if stmt_id:
                statements_dict[stmt_id]['line_count'] += 1

            # Flat payload used by the matching logic and AI prompt construction.
            stm_data.append({
                'id': stm.id,
                'statement': stmt_name,
                'date': str(stm.date),
                # Prefer payment_ref for display; fall back to move name.
                'name': stm.payment_ref or stm.name or '',
                'amount': stm.amount,
                'partner_id': stm.partner_id.id if stm.partner_id else '',
                'partner_name': stm.partner_id.name if stm.partner_id else '',
                'payment_ref': stm.payment_ref or '',
            })

        # Store grouped + flat data for the Step 2 accordion panel.
        step_payloads['step2'] = {
            'statements': list(statements_dict.values()),
            'transactions': stm_data
        }
        self._publish_step(channel, *step, status='done')

        # -- STEP 3: Internal Review -------------------------------------------
        # Load all unreconciled journal items (account.move.line) on reconcilable
        # accounts. These are the potential counterparts for bank statement lines.
        #
        # Filters:
        #   account_id.reconcile = True  â†’ A/R and A/P accounts only.
        #   reconciled = False           â†’ Not yet fully reconciled.
        #   parent_state = 'posted'      â†’ Only confirmed/validated journal entries.
        step = self.STEPS[2]
        self._publish_step(channel, *step, status='active')

        aml_records = self.env['account.move.line'].search([
            ('account_id.reconcile', '=', True),
            ('reconciled', '=', False),
            ('parent_state', '=', 'posted'),
        ])

        aml_data = []
        for aml in aml_records:
            aml_data.append({
                'id': aml.id,
                'date': str(aml.date),
                # name preferred; ref is typically the invoice/bill number.
                'name': aml.name or aml.ref or '',
                # amount_residual is outstanding balance after partial reconciliations.
                'amount': aml.amount_residual,
                'account_id': aml.account_id.code if aml.account_id else '',
                'partner_id': aml.partner_id.id if aml.partner_id else '',
                'partner_name': aml.partner_id.name if aml.partner_id else '',
                'move_id': aml.move_id.name if aml.move_id else '',
            })

        step_payloads['step3'] = {'unreconciled_moves': aml_data}
        self._publish_step(channel, *step, status='done')

        # -- STEP 4: Auto Matching ---------------------------------------------
        # Exact amount-based matching using a pre-built index for O(1) lookup.
        #
        # Algorithm:
        #   a) Build aml_by_amount dict: {rounded_residual: [aml, ...]}
        #   b) For each statement line, look up its NEGATED amount in the index.
        #      (Bank debit=positive â†’ invoice credit=negative residual in Odoo's convention)
        #   c) Match found â†’ 'matched'; no match â†’ 'check' (re-evaluated in Step 5).
        #
        # Note: When multiple AMLs have the same amount, the first one is chosen.
        # Production should add tiebreakers (date proximity, partner, etc.).
        step = self.STEPS[3]
        self._publish_step(channel, *step, status='active')

        # Build O(1) lookup dict: {rounded_amount: [aml_record, ...]}
        aml_by_amount = {}
        for aml in aml_records:
            key = round(aml.amount_residual, 2)
            aml_by_amount.setdefault(key, []).append(aml)

        # provisional_results holds the working classification for all lines.
        # Each dict: {statement_id, status, matched_aml_ids, ai_explanation}
        provisional_results = []
        step4_matched = []   # Rows for the Step 4 "Matched" accordion table.
        step4_remaining = [] # Lines without exact match, forwarded to Step 5.

        for stm in stm_data:
            # Negate: bank debit (positive) corresponds to A/R credit (negative residual).
            neg_amount = round(-stm['amount'], 2)
            matched_amls = aml_by_amount.get(neg_amount, [])

            if matched_amls:
                # âœ… Exact amount match found â†’ classify as 'matched'.
                aml_match = matched_amls[0]
                provisional_results.append({
                    'statement_id': stm['id'],
                    'status': 'matched',
                    'matched_aml_ids': [aml_match.id],
                    'ai_explanation': f"Exact amount match: {stm['amount']} â†’ AML {aml_match.id}",
                })
                # Build accordion row data for Step 4 UI table.
                step4_matched.append({
                    'statement_id': stm['id'],
                    'statement_date': stm['date'],
                    'statement_ref': stm['name'],
                    'statement_amount': stm['amount'],
                    'transaction_id': aml_match.id,
                    'transaction_partner_id': aml_match.partner_id.id if aml_match.partner_id else '',
                    'transaction_partner': aml_match.partner_id.name if aml_match.partner_id else '',
                    'transaction_date': str(aml_match.date),
                    'transaction_ref': aml_match.name or aml_match.ref or '',
                })
            else:
                # â�³ No exact match â†’ tentatively 'check'; Step 5 may promote to 'rule'.
                provisional_results.append({
                    'statement_id': stm['id'],
                    'status': 'check',        # will be refined in step 5
                    'matched_aml_ids': [],
                    'ai_explanation': 'No exact match found in this pass.',
                })
                step4_remaining.append(stm)

        step_payloads['step4'] = {
            'matched': step4_matched,
            'remaining': step4_remaining
        }
        self._publish_step(channel, *step, status='done')

        # -- STEP 5: Rule Application -----------------------------------------
        # Apply Odoo's native reconcile models (account.reconcile.model) to 'check'
        # lines that were not resolved in Step 4.
        #
        # Only rules with can_be_proposed=True are loaded â€” these are rules
        # configured by the accountant in Accounting â†’ Configuration â†’ Reconciliation Models.
        #
        # Matching criteria (all optional; ALL defined criteria must pass):
        #   - Label match  : contains | not_contains | is | match_regex
        #   - Partner match: statement partner must be in rule.match_partner_ids
        #   - Amount range : abs(amount) must fall within [match_amount_min, match_amount_max]
        #
        # 'check' â†’ 'rule' on first matching rule (break after first match).
        step = self.STEPS[4]
        self._publish_step(channel, *step, status='active')

        # Load reconcile models for the current company with auto-proposal enabled.
        rules = self.env['account.reconcile.model'].search([
            ('company_id', '=', self.env.company.id),
            ('can_be_proposed', '=', True),
        ])

        # Build human-readable criteria summaries for the Step 5 accordion table.
        rules_data = []
        for r in rules:
            criteria_parts = []
            if r.match_label and r.match_label_param:
                criteria_parts.append(f"Label {r.match_label} '{r.match_label_param}'")
            if r.match_amount:
                criteria_parts.append(
                    f"Amount between {r.match_amount_min} and {r.match_amount_max}"
                )
            if r.match_partner_ids:
                criteria_parts.append(f"Partner in {', '.join(r.match_partner_ids.mapped('name'))}")
            rules_data.append({
                'id': r.id,
                'name': r.name,
                'criteria': ' | '.join(criteria_parts) if criteria_parts else 'Auto Rule',
            })

        step_payloads['step5'] = {'rules': rules_data}

        # O(1) lookup dict for statement lines used inside the rule-matching loop.
        stm_by_id = {s['id']: s for s in stm_data}

        for item in provisional_results:
            # Only re-evaluate lines NOT resolved in Step 4.
            if item['status'] != 'check':
                continue

            stm = stm_by_id.get(item['statement_id'], {})
            stm_ref = (stm.get('payment_ref') or stm.get('name') or '').strip()
            stm_partner_id = stm.get('partner_id')
            stm_amount = abs(stm.get('amount', 0.0))

            for rule in rules:
                matched = True

                # -- Label matching -----------------------------------------
                # Applied only when both label type AND parameter are configured.
                if rule.match_label and rule.match_label_param:
                    param = rule.match_label_param
                    ref_lower = stm_ref.lower()
                    param_lower = param.lower()

                    if rule.match_label == 'contains':
                        # Statement reference must contain the rule parameter substring.
                        matched = matched and (param_lower in ref_lower)
                    elif rule.match_label == 'not_contains':
                        # Statement reference must NOT contain the parameter.
                        matched = matched and (param_lower not in ref_lower)
                    elif rule.match_label == 'is':
                        # Exact case-insensitive equality.
                        matched = matched and (ref_lower == param_lower)
                    elif rule.match_label == 'match_regex':
                        # Regex match â€” bad patterns are caught and treated as non-match.
                        import re
                        try:
                            matched = matched and bool(re.search(param, stm_ref, re.IGNORECASE))
                        except re.error:
                            matched = False
                    else:
                        # Unknown match type â€” treat rule as non-applicable.
                        matched = False
                # If rule has no label criteria, label check is skipped entirely.

                # -- Partner matching ------------------------------â        # -- STEP 6: Categorization (optional AI call) -------------------------
        # Supports two AI providers based on vraja.ai.config.ai_provider:
        #
        #   Provider 'openai' (default / existing logic â€” untouched):
        #     Endpoint : POST https://api.openai.com/v1/chat/completions
        #     Auth     : Authorization: Bearer <key>
        #     Schema   : {'model':â€¦, 'messages':[{role,content}]}
        #     Response : choices[0].message.content  (JSON string)
        #
        #   Provider 'claude' (new addition â€” Anthropic Messages API):
        #     Endpoint : POST https://api.anthropic.com/v1/messages
        #     Auth     : x-api-key: <key>  (NOT Bearer)
        #     Headers  : anthropic-version: 2023-06-01  (mandatory)
        #     Schema   : {'model':â€¦, 'max_tokens':â€¦, 'system':â€¦, 'messages':[{role,content}]}
        #     Response : content[0].text  (JSON string)
        #     Ref      : https://docs.anthropic.com/en/api/overview
        #
        # Fallback: rules-only results from Steps 4+5 used if AI is disabled or fails.
        step = self.STEPS[5]
        self._publish_step(channel, *step, status='active')

        parsed_data = provisional_results   # default to rule/exact-match results
        token_usage = 0

        # -- Shared prompt (identical for both providers) -----------------------
        # Separating prompts from the provider-specific payload construction below
        # keeps the logic clean; both providers receive exactly the same instructions.
        system_prompt = """
You are an elite AI bank reconciliation Agent for Odoo.
Your goal is to parse Bank Statement Lines and match them to Unreconciled Journal Items.

Output must be valid JSON array ONLY, no markdown wrapper.

Categories of outcome for each Bank Statement Line:
1. 'matched': Found exact or highly probable matched A/R or A/P. Include AML IDs in 'matched_aml_ids'.
2. 'rule': Regular predictable pattern (bank fee, SMS charge, service charge). No exact AML matched, but fits a known pattern.
3. 'check': Cannot find match, flag for user manual review.

JSON format:
[
    {
        "statement_id": <int>,
        "status": "<matched|rule|check>",
        "ai_explanation": "<string>",
        "matched_aml_ids": [<int list>]
    },...
]
"""
        user_prompt = (
            "Bank Statements:\n" + json.dumps(stm_data) +
            "\n\nUnreconciled Journal Items:\n" + json.dumps(aml_data)
        )

        # Determine active provider and key.
        ai_provider = config.ai_provider if config else 'openai'
        use_openai = (ai_provider == 'openai') and bool(config and config.openai_api_key)
        use_claude = (ai_provider == 'claude') and bool(config and config.claude_api_key)
        use_gemini = (ai_provider == 'gemini') and bool(config and config.gemini_api_key)
        use_ai = use_openai or use_claude or use_gemini

        if use_ai and stm_data and aml_data:
            try:
                import requests

                if use_gemini:
                    # ── Google Gemini REST API ────────────────────────────────
                    # Endpoint : POST https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent
                    # Auth     : URL query param ?key=...
                    gemini_model = config.gemini_llm_model or 'gemini-flash-latest'
                    url = f'https://generativelanguage.googleapis.com/v1beta/models/{gemini_model}:generateContent?key={config.gemini_api_key}'

                    payload = {
                        "system_instruction": {
                            "parts": {"text": system_prompt}
                        },
                        "contents": [
                            {
                                "parts": [{"text": user_prompt}]
                            }
                        ]
                    }

                    response = requests.post(
                        url,
                        json=payload,
                        headers={
                            'Content-Type': 'application/json',
                        },
                        timeout=120,
                    )
                    response.raise_for_status()
                    response_json = response.json()

                    # Gemini response schema:
                    # {'candidates': [{'content': {'parts': [{'text': '...'}]}}], 'usageMetadata': {'totalTokenCount': 123}}
                    candidates = response_json.get('candidates', [])
                    if not candidates:
                        raise ValueError(f"Gemini returned no candidates. Full response: {response_json}")

                    parts = candidates[0].get('content', {}).get('parts', [])
                    if not parts or 'text' not in parts[0]:
                        raise ValueError(f"Gemini returned unexpected content structure: {candidates[0]}")

                    ai_text = parts[0]['text']
                    token_usage = response_json.get('usageMetadata', {}).get('totalTokenCount', 0)

                elif use_claude:
                    # -- Claude (Anthropic) Messages API -----------------------
                    # Endpoint : https://api.anthropic.com/v1/messages
                    # Auth     : x-api-key header (Anthropic uses its own auth scheme,
                    #            NOT the standard 'Authorization: Bearer' pattern).
                    # Version  : anthropic-version header MUST be '2023-06-01'.
                    # System   : top-level 'system' key (not inside messages array).
                    # Messages : [{'role': 'user', 'content': <str>}]
                    #            Claude does not accept a 'system' role inside messages.
                    # max_tokens: required field for Claude (unlike OpenAI which is optional).
                    #
                    # Full ref: https://docs.anthropic.com/en/api/overview
                    claude_model = config.claude_llm_model or 'claude-sonnet-4-6'
                    payload = {
                        'model': claude_model,
                        'max_tokens': config.claude_max_tokens or 8192,  # Configurable by user
                        'system': system_prompt,  # System prompt is a TOP-LEVEL key, not inside messages.
                        'messages': [
                            {'role': 'user', 'content': user_prompt},
                        ],
                    }
                    response = requests.post(
                        'https://api.anthropic.com/v1/messages',
                        json=payload,
                        headers={
                            'x-api-key': config.claude_api_key,           # Anthropic auth header
                            'anthropic-version': '2023-06-01',            # Mandatory version header
                            'content-type': 'application/json',
                        },
                        timeout=120,
                    )
                    response.raise_for_status()
                    response_json = response.json()

                    # Claude response schema:
                    #   {'content': [{'type': 'text', 'text': '<string>'}], 'usage': {...}}
                    # NOTE: When extended thinking is active, content[0] may be a
                    #       {'type': 'thinking', 'thinking': '...'} block with NO 'text' key.
                    #       Always filter by type='text' to avoid KeyError / empty string.
                    content_blocks = response_json.get('content', [])
                    text_blocks = [b for b in content_blocks if b.get('type') == 'text']
                    if not text_blocks:
                        raise ValueError(
                            f"Claude response contained no 'text' content block. "
                            f"stop_reason={response_json.get('stop_reason')}, "
                            f"content_types={[b.get('type') for b in content_blocks]}"
                        )
                    ai_text = text_blocks[0]['text']
                    usage = response_json.get('usage', {})
                    token_usage = usage.get('input_tokens', 0) + usage.get('output_tokens', 0)

                else:
                    # -- OpenAI Chat Completions API (existing logic â€” 100% untouched) --
                    payload = {
                        'model': config.llm_model or 'gpt-4.1',
                        'messages': [
                            {'role': 'system', 'content': system_prompt},
                            {'role': 'user', 'content': user_prompt},
                        ],
                    }
                    # POST to OpenAI with a 120s timeout for large datasets.
                    response = requests.post(
                        'https://api.openai.com/v1/chat/completions',
                        json=payload,
                        headers={
                            'Authorization': f'Bearer {config.openai_api_key}',
                            'Content-Type': 'application/json',
                        },
                        timeout=120,
                    )
                    # Raise HTTPError for 4xx/5xx responses.
                    response.raise_for_status()
                    response_json = response.json()
                    ai_text = response_json['choices'][0]['message']['content']
                    # Track token consumption for cost reporting in the AI log.
                    token_usage = response_json.get('usage', {}).get('total_tokens', 0)

                # -- Shared response parsing (identical for both providers) ----
                # Strip whitespace first so startswith check is reliable.
                ai_text = ai_text.strip()
                # Strip optional markdown code fence if model wraps JSON in ```json...```.
                if ai_text.startswith('```'):
                    ai_text = ai_text.split('\n', 1)[-1].rsplit('```', 1)[0].strip()

                # Guard: empty string → model returned nothing usable.
                # Raising here gives a clear message instead of the cryptic
                # "Expecting value: line 1 column 1 (char 0)" JSONDecodeError.
                if not ai_text:
                    raise ValueError(
                        "AI returned an empty response body after stripping code fences. "
                        "The model may have refused the request or returned only a fence marker."
                    )

                # Accept both a plain list and a dict wrapping the array in 'statements'.
                parsed_ai = json.loads(ai_text)
                if isinstance(parsed_ai, list):
                    parsed_data = parsed_ai
                elif isinstance(parsed_ai, dict) and 'statements' in parsed_ai:
                    parsed_data = parsed_ai['statements']

            except Exception as e:
                _logger.error("BankRecon AI call failed: %s", e)
                # Write a 'failed' log entry for audit before returning the error.
                try:
                    failed_log = self.env['vraja.ai.log'].sudo().create({
                        'vraja_common_log_store': 'bank_recon',
                        'status': 'failed',
                    })
                    self.env['vraja.ai.log.line'].sudo().create([
                        {'log_id': failed_log.id, 'step': 'Error', 'message': f"AI Call Failed: {str(e)}"},
                        {'log_id': failed_log.id, 'step': 'Journal', 'message': journal.name if journal else 'Unknown'},
                    ])
                except Exception as log_e:
                    _logger.warning("BankRecon: Could not write failed AI log - %s", log_e)
                return {'success': False, 'error': f"AI Call Failed: {str(e)}"}

        self._publish_step(channel, *step, status='done')

        # AI may have changed statuses (e.g. promoting 'check' to 'matched').
        # Sync the 'Step 4' payload so the UI doesn't look contradictory.
        if use_ai and 'step4' in step_payloads:
            # Get IDs of statement lines already shown in step 4
            existing_step4_matched_ids = {m['statement_id'] for m in step_payloads['step4']['matched']}
            
            # Find any NEW matches discovered specifically by the AI in step 6
            amls_by_id = {aml['id']: aml for aml in aml_data}
            for match in parsed_data:
                if match.get('status') == 'matched' and match.get('statement_id') not in existing_step4_matched_ids:
                    # Look up the statement transaction logic
                    stm = next((s for s in stm_data if s['id'] == match.get('statement_id')), None)
                    if stm and match.get('matched_aml_ids'):
                        # Take the first AML ID the AI associated with this
                        aml = amls_by_id.get(match.get('matched_aml_ids')[0])
                        if aml:
                            step_payloads['step4']['matched'].append({
                                'statement_id': stm['id'],
                                'statement_date': stm['date'],
                                'statement_ref': stm['name'],
                                'statement_amount': stm['amount'],
                                'transaction_id': aml['id'],
                                'transaction_partner_id': aml['partner_id'],
                                'transaction_partner': aml['partner_name'],
                                'transaction_date': aml['date'],
                                'transaction_ref': aml['name'],
                            })

        # -- STEP 7: Final Analysis â€“ persist records --------------------------
        # parsed_data now holds the final classification for every statement line.
        # This step:
        #   a) Creates the vraja.bank.recon.analysis header record.
        #   b) Bulk-creates all vraja.bank.recon.analysis.line child records.
        #   c) Writes the vraja.ai.log entry for audit + KPI dashboard counters.
        #   d) Serialises the persisted analysis and returns it to the OWL frontend.
        step = self.STEPS[6]
        self._publish_step(channel, *step, status='active')

        # Find the AI card for this module to link the analysis in the AI tools list.
        card = self.env['vraja.ai.card'].search(
            [('vraja_common_store', '=', 'bank_recon')], limit=1
        )

        # Create the analysis header. state='done' marks it as a completed run.
        # step_data stores accordion drill-down data for future dashboard restores.
        analysis = self.env['vraja.bank.recon.analysis'].create({
            'card_id': card.id if card else False,
            'journal_id': journal_id,
            'state': 'done',
            'step_data': step_payloads,
        })

        # Bulk-build One2many line vals using the ORM (0, 0, vals) tuple syntax.
        # (6, 0, ids) on matched_aml_ids replaces the Many2many set with the provided IDs.
        line_vals = []
        for match in parsed_data:
            line_vals.append((0, 0, {
                'statement_line_id': match.get('statement_id'),
                'status': match.get('status'),
                'ai_explanation': match.get('ai_explanation'),
                'matched_aml_ids': [(6, 0, match.get('matched_aml_ids', []))],
            }))
        analysis.write({'line_ids': line_vals})

        # -- Tally final counts and write the AI audit log ---------------------
        matched_count = sum(1 for m in parsed_data if m.get('status') == 'matched')
        rule_count = sum(1 for m in parsed_data if m.get('status') == 'rule')
        check_count = sum(1 for m in parsed_data if m.get('status') == 'check')
        total = len(parsed_data)

        self._write_ai_log(
            analysis_id=analysis.id,
            analysis_ref=analysis.name,
            journal_name=journal.name,
            matched_count=matched_count,
            rule_count=rule_count,
            check_count=check_count,
            total=total,
            used_ai=use_ai,
            token_usage=token_usage,
            ai_provider=ai_provider if use_ai else False,
            llm_model=(
                (config.gemini_llm_model if use_gemini else
                 (config.claude_llm_model if use_claude else config.llm_model))
                if use_ai else False
            ),
        )

        self._publish_step(channel, *step, status='done')

        # Serialise the persisted analysis record to a JSON-safe dict for the OWL layer.
        result_data = self._serialize_analysis(analysis)

        return {
            'success': True,
            'analysis_id': analysis.id,
            'analysis_name': analysis.name,
            'results': result_data,
            'step_data': step_payloads,
        }

    # -------------------------------------------------------------------------
    # SECTION 3 â€“ Confirm & Review (auto-reconcile + return redirect)
    # -------------------------------------------------------------------------

    @api.model
    def confirm_and_review(self, analysis_id):
        """
        Finalise an AI analysis: auto-reconcile matched lines and redirect to
        the native Odoo bank reconciliation widget.

        Called when the user clicks 'Confirm & Review' on the dashboard results.

        Execution:
            1. Browse the analysis record; return error dict if not found.
            2. Delegate to analysis.action_confirm_and_review() which:
                   - Processes 'matched' and 'rule' lines via set_line_bank_statement_line().
                   - Sets analysis state to 'reconciled'.
            3. Build and return an ir.actions.act_window pointing to the enterprise
               bank reconciliation kanban, scoped to the processed journal.

        Fallback:
            If the enterprise kanban action is not found, returns a basic
            act_window for account.bank.statement.line.

        Args:
            analysis_id (int): ID of the vraja.bank.recon.analysis record to finalise.

        Returns:
            dict: {'success': True, 'action': <odoo_action_dict>}
                  {'success': False, 'error': str}
        """
        analysis = self.env['vraja.bank.recon.analysis'].browse(analysis_id)
        if not analysis.exists():
            return {'success': False, 'error': 'Analysis not found.'}

        # Delegate reconciliation to the analysis model's domain method.
        analysis.action_confirm_and_review()

        journal_id = analysis.journal_id.id

        # -- Resolve the enterprise bank reconciliation kanban action ----------
        # External ID available in Odoo 17+ Enterprise (account_accountant module).
        try:
            base_action = self.env.ref(
                'account_accountant.action_bank_statement_line_transactions_kanban'
            ).sudo().read()[0]
        except Exception:
            # Fallback if enterprise module is not installed.
            base_action = {
                'type': 'ir.actions.act_window',
                'name': 'Bank Reconciliation',
                'res_model': 'account.bank.statement.line',
                'view_mode': 'kanban,list',
            }

        # Override domain/context to scope the view to the processed journal.
        # default_journal_id + search_default_journal_id pre-selects the journal filter.
        base_action.update({
            'domain': [],
            'context': {
                'default_journal_id': journal_id,
                'search_default_journal_id': journal_id,
            },
            'name': 'Bank Reconciliation',
            'target': 'current',
        })
        # Remove 'id' to prevent the action manager from resetting domain/context
        # by reloading the template action record from the database.
        base_action.pop('id', None)

        return {
            'success': True,
            'action': base_action,
        }

    # -------------------------------------------------------------------------
    # SECTION 4 â€“ Helpers
    # -------------------------------------------------------------------------

    def _serialize_analysis(self, analysis):
        """
        Convert a vraja.bank.recon.analysis record into a plain Python dict
        suitable for JSON serialisation and transmission to the OWL frontend.

        Called in two contexts:
            1. After a new AI run (to return results to the dashboard).
            2. During get_dashboard_data (to restore the last run on page load).

        Output structure:
            {
                'analysis_id'   : int,         # Database ID
                'analysis_name' : str,         # Human reference e.g. "BRA/2026/00015"
                'journal_name'  : str,         # Bank journal display name
                'run_date'      : str,         # ISO datetime string
                'state'         : str,         # 'draft' | 'done' | 'reconciled'
                'matched'       : list[dict],  # Lines classified as 'matched'
                'rule'          : list[dict],  # Lines classified as 'rule'
                'check'         : list[dict],  # Lines needing manual review
                'step_data'     : dict|None,   # Per-step drill-down data
            }

        Each line dict: {id, date, amount, payment_ref, status, ai_explanation, matched_aml_count}

        matched_aml_count is used instead of the full IDs list to keep the payload small.

        Args:
            analysis (vraja.bank.recon.analysis): Record to serialise.

        Returns:
            dict: JSON-safe dictionary.
        """
        matched = []
        rule = []
        check = []

        for line in analysis.line_ids:
            entry = {
                'id': line.id,
                'date': str(line.date) if line.date else '',
                'amount': line.amount,
                'payment_ref': line.payment_ref or '',
                'status': line.status,
                'ai_explanation': line.ai_explanation or '',
                # Send count rather than full ID list to keep the JSON payload compact.
                'matched_aml_count': len(line.matched_aml_ids),
            }
            # Distribute into the correct result bucket.
            if line.status == 'matched':
                matched.append(entry)
            elif line.status == 'rule':
                rule.append(entry)
            else:
                # Any unexpected status falls into 'check' for safety.
                check.append(entry)

        return {
            'analysis_id': analysis.id,
            'analysis_name': analysis.name,
            'journal_name': analysis.journal_id.name if analysis.journal_id else '',
            'run_date': str(analysis.run_date) if analysis.run_date else '',
            'state': analysis.state,
            'matched': matched,
            'rule': rule,
            'check': check,
            # step_data stores per-step accordion drill-down payloads from Steps 2-5.
            'step_data': analysis.step_data or None,
        }

    def _write_ai_log(self, analysis_id, analysis_ref, journal_name, matched_count,
                      rule_count, check_count, total, used_ai, token_usage=0,
                      ai_provider=False, llm_model=False):
        """
        Write a structured audit log entry to vraja.ai.log for this analysis run.

        Each run produces one vraja.ai.log header with multiple vraja.ai.log.line
        child records (one per metric). These log records:
            - Appear in the 'AI Logs' view from the dashboard history button.
            - Are counted by the KPI card for ai_matched / rule_matched.
            - Feed the openAIMatchedLines() OWL navigation (filtered to 'reconciled').

        Log lines recorded:
            Analysis Reference â€“ Sequence number of the analysis run.
            Journal            â€“ Name of the processed bank journal.
            Mode               â€“ 'AI + Rules' (OpenAI used) or 'Rules Only'.
            Matched            â€“ Count of lines classified as 'matched'.
            Rule               â€“ Count of lines classified as 'rule'.
            To Check           â€“ Count of lines flagged for manual review.
            Total Processed    â€“ Total statement lines in this run.

        Design: sudo() ensures the log is written regardless of user's access rights.
                Failures are logged as warnings and do NOT abort the analysis.

        Args:
            analysis_id   (int)  : ID of the linked vraja.bank.recon.analysis record.
            analysis_ref  (str)  : Human-readable reference number.
            journal_name  (str)  : Display name of the bank journal.
            matched_count (int)  : Count of 'matched' lines.
            rule_count    (int)  : Count of 'rule' lines.
            check_count   (int)  : Count of 'check' lines.
            total         (int)  : Total statement lines processed.
            used_ai       (bool) : True if OpenAI was called.
            token_usage   (int)  : Total tokens consumed (0 if AI not used).
            ai_provider   (str)  : AI provider used (False if rules-only).
            llm_model     (str)  : Name of the AI model used (False if rules-only).
        """
        try:
            log_vals = {
                'vraja_common_log_store': 'bank_recon',
                'status': 'success',
                'bank_recon_analysis_id': analysis_id,
                'bank_recon_token_usage': token_usage,
            }
            if used_ai:
                log_vals['ai_provider'] = ai_provider
                log_vals['ai_llm_model'] = llm_model
            log = self.env['vraja.ai.log'].sudo().create(log_vals)
            if not used_ai:
                log.write({'ai_provider': False, 'ai_llm_model': False})
            # Batch-create all detail lines in a single SQL INSERT for performance.
            line_vals = [
                {'log_id': log.id, 'step': 'Analysis Reference', 'message': analysis_ref},
                {'log_id': log.id, 'step': 'Journal', 'message': journal_name},
                {'log_id': log.id, 'step': 'Mode', 'message': 'AI + Rules' if used_ai else 'Rules Only'},
                {'log_id': log.id, 'step': 'Matched', 'message': str(matched_count)},
                {'log_id': log.id, 'step': 'Rule', 'message': str(rule_count)},
                {'log_id': log.id, 'step': 'To Check', 'message': str(check_count)},
                {'log_id': log.id, 'step': 'Total Processed', 'message': str(total)},
            ]
            self.env['vraja.ai.log.line'].sudo().create(line_vals)
        except Exception as e:
            # A logging failure must never abort the main reconciliation flow.
            _logger.warning("BankRecon: Could not write AI log â€“ %s", e)

    @api.model
    def get_last_analysis(self, journal_id=None):
        """
        Return the serialised most-recent completed analysis for a given journal.

        Used when the OWL component needs to refresh the last result independently
        of a full get_dashboard_data call (e.g., on journal picker change).

        Args:
            journal_id (int|None): Scope to a specific journal ID, or None for global.

        Returns:
            dict|None: Serialised analysis dict or None if no completed analysis exists.
        """
        # Only consider fully completed (not draft) analyses.
        domain = [('state', '=', 'done')]
        if journal_id:
            domain.append(('journal_id', '=', journal_id))

        analysis = self.env['vraja.bank.recon.analysis'].search(
            domain, order='run_date desc', limit=1
        )
        if analysis:
            return self._serialize_analysis(analysis)
        return None

    @api.model
    def run_ai_auto_match(self):
        """
        [LEGACY] Simple bulk auto-match across all unreconciled bank statement lines.

        âš ï¸�  Kept for backward compatibility with older scheduled actions or buttons.
            New code should use run_full_ai_analysis(journal_id) which provides
            a 7-step pipeline, accordion drill-downs, and AI integration.

        Algorithm:
            For each unreconciled bank statement line (all bank journals):
                1. Find an AML with an equal and opposite balance on a reconcilable account.
                2. If found, call line.reconcile() via ORM.
                3. Increment success_count on each successful reconciliation.

        Limitations vs. run_full_ai_analysis:
            - No journal filtering (processes all bank journals at once).
            - No AI categorization (exact amount match only).
            - No vraja.ai.log entry (no audit trail).
            - skip_account_move_synchronization avoids re-posting the move during
              reconciliation, which would be unnecessary overhead.

        Returns:
            dict: {'success': True, 'message': str, 'matched_count': int}
        """
        BankStatementLine = self.env['account.bank.statement.line']
        lines = BankStatementLine.search([
            ('is_reconciled', '=', False),
            ('journal_id.type', 'in', ['bank'])
        ])
        success_count = 0
        for line in lines:
            # Find a counterpart AML with the opposite balance on a reconcilable account.
            # balance holds the raw debit/credit in company currency on account.move.line.
            domain = [
                ('amount_residual', '!=', 0),
                ('account_id.reconcile', '=', True),
                ('balance', '=', -line.amount)
            ]
            matching_aml = self.env['account.move.line'].search(domain, limit=1)
            if matching_aml:
                try:
                    # skip_account_move_synchronization avoids re-posting the move
                    # during reconciliation (unnecessary for simple bank matching).
                    line.with_context(skip_account_move_synchronization=True).reconcile(
                        lines_vals_list=[{'id': matching_aml.id}]
                    )
                    success_count += 1
                except Exception:
                    # Silently skip lines that fail (e.g., already reconciled mid-loop).
                    pass
        return {
            'success': True,
            'message': f'AI successfully matched {success_count} transactions across all Journals!',
            'matched_count': success_count,
        }
