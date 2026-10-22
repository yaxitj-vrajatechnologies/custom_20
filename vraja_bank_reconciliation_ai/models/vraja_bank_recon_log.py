# -*- coding: utf-8 -*-
"""
vraja_bank_recon_log.py
=========================
Extends the vraja.ai.log and vraja.ai.log.line models from the base vraja_ai
module to support Bank Reconciliation AI-specific log data.

Design philosophy:
    All additions are made via _inherit so the base vraja_ai module is never
    modified. This keeps the Bank Reconciliation AI module fully self-contained
    and removable without impacting the core AI framework.

Extensions:
    VrajaAILogBankRecon:
        - Registers 'bank_recon' as a new selection option in vraja_common_log_store.
        - Adds relational fields linking the log entry to the associated
          vraja.bank.recon.analysis record (state, lines, journal, card, token usage).
        - Exposes action_confirm_and_review() as a convenience pass-through
          so the log form view's "Confirm & Review" button works without needing
          to open the analysis record separately.

    VrajaAILogLineBankRecon:
        - Adds 'step' and 'message' Char/Text fields to vraja.ai.log.line so each
          detail line can store a labelled key-value pair (e.g., "Matched: 12").

Author : Vraja Technologies
Version: 19.0
"""

from odoo import models, fields


class VrajaAILogBankRecon(models.Model):
    """
    Extends vraja.ai.log with Bank Reconciliation AI-specific fields.

    The base vraja.ai.log model is a generic audit log for all Vraja AI modules.
    This class injects the 'bank_recon' selection value into the store discriminator
    field and adds relational fields to surface analysis data directly on the log form.

    New selection value:
        vraja_common_log_store = 'bank_recon'
        → This tag is used as the primary filter in search views and domain
          expressions everywhere logs are listed for this module.

    ondelete='set null' ensures that if this module is uninstalled, the selection
    value is cleared from existing records rather than causing a constraint error.
    """

    _inherit = 'vraja.ai.log'

    # ── Store discriminator (selection extension) ─────────────────────────────
    vraja_common_log_store = fields.Selection(
        selection_add=[('bank_recon', 'Bank Reconciliation AI')],
        ondelete={'bank_recon': 'set null'},
        help="Adds 'bank_recon' as a valid store tag for filtering AI logs "
             "to the Bank Reconciliation module."
    )

    # ── Analysis record links (all read from the related analysis record) ──────
    bank_recon_analysis_id = fields.Many2one(
        'vraja.bank.recon.analysis',
        string='Analysis Record',
        ondelete='cascade',
        help="Links this log entry to the specific vraja.bank.recon.analysis run "
             "that generated it. Used for the 'Confirm & Review' button on the log form."
    )
    bank_recon_state = fields.Selection(
        related='bank_recon_analysis_id.state',
        help="Mirrors the analysis run's lifecycle state (draft/done/reconciled) "
             "for display in the log list view without opening the analysis form."
    )
    bank_recon_line_ids = fields.One2many(
        related='bank_recon_analysis_id.line_ids',
        readonly=False,
        help="Related analysis classification lines, shown on the log form view "
             "so accountants can review AI decisions without leaving the log record."
    )
    bank_recon_journal_id = fields.Many2one(
        related='bank_recon_analysis_id.journal_id',
        help="Bank journal that was analysed in the linked analysis run."
    )
    bank_recon_card_id = fields.Many2one(
        related='bank_recon_analysis_id.card_id',
        help="AI card linked to the analysis run (used in the AI tools list view)."
    )
    bank_recon_token_usage = fields.Integer(
        string='Token Usage',
        help="Total OpenAI API tokens consumed during the AI categorization step (Step 6). "
             "0 if the run executed in rules-only mode (no OpenAI key configured)."
    )

    def action_confirm_and_review(self):
        """
        Pass-through action allowing the 'Confirm & Review' button on the log
        form view to trigger reconciliation without opening the analysis record.

        Iterates over all records in the current recordset (supports multi-action
        from list views) and delegates to the analysis record's own
        action_confirm_and_review() method, which handles the actual Odoo
        reconciliation API calls.

        Returns:
            dict|None: The return value of the last analysis.action_confirm_and_review()
                       call (an ir.actions.client notification), or None if no
                       analysis is linked.
        """
        for rec in self:
            if rec.bank_recon_analysis_id:
                # Delegate to the domain method on the analysis record.
                # Only the last return value is surfaced (suitable for single-record use).
                return rec.bank_recon_analysis_id.action_confirm_and_review()


class VrajaAILogLineBankRecon(models.Model):
    """
    Extends vraja.ai.log.line to carry labelled key-value detail rows.

    The base vraja.ai.log.line model is a generic log detail record. This class
    adds 'step' (label) and 'message' (value) fields so that each Bank
    Reconciliation AI run can record structured per-metric rows such as:

        Step    : "Matched"    | Message: "12"
        Step    : "Rule"       | Message: "5"
        Step    : "To Check"   | Message: "3"
        Step    : "Journal"    | Message: "Bank - USD"

    These rows are displayed in a One2many tree on both the vraja.ai.log form
    and the vraja.bank.recon.analysis form.

    Added FROM THIS MODULE — the base vraja_ai module is not modified.
    """

    _inherit = 'vraja.ai.log.line'

    step = fields.Char(
        string='Step / Label',
        help="Short label identifying what this log detail row represents, "
             "e.g. 'Matched', 'Journal', 'Mode', 'Total Processed'."
    )
    message = fields.Text(
        string='Value / Detail',
        help="The value or explanation associated with the step label, "
             "e.g. '12', 'Bank - USD', 'AI + Rules'."
    )
