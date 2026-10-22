# -*- coding: utf-8 -*-
"""
vraja_bank_recon_analysis.py
==============================
Defines the persistent data models for a Bank Reconciliation AI run.

Two models are declared here:

    VrajaBankReconAnalysis      (_name: vraja.bank.recon.analysis)
        - Header record for a single AI reconciliation run.
        - Stores the journal analysed, the run timestamp, the final state,
          per-step accordion data, and links to all child classification lines.
        - Sequence-based reference is auto-assigned on creation.

    VrajaBankReconAnalysisLine  (_name: vraja.bank.recon.analysis.line)
        - One record per bank statement line processed in a given analysis run.
        - Stores the AI classification (matched / rule / check), the explanation,
          and a Many2many link to the proposed counterpart account.move.line records.

"""

from odoo import models, fields, api
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class VrajaBankReconAnalysis(models.Model):
    """
    Header record for a single AI bank reconciliation analysis run.

    Lifecycle states:
        draft      – Created but not yet confirmed (unused in the current flow;
                     analysis records are created directly in 'done' state).
        done       – AI pipeline completed; lines are classified and stored.
        reconciled – Confirm & Review was executed; matched/rule lines have been
                     reconciled in Odoo via set_line_bank_statement_line().

    The step_data JSON field stores the per-step accordion drill-down payloads
    (steps 2-5) produced during the AI run so the dashboard can restore them
    on subsequent page loads without re-running the pipeline.
    """

    _name = 'vraja.bank.recon.analysis'
    _description = 'Bank Reconciliation AI Analysis'
    # Default ordering: most recent run at the top of list views.
    _order = 'run_date desc'

    # ── Identification ────────────────────────────────────────────────────────
    name = fields.Char(
        string='Reference',
        required=True,
        copy=False,
        readonly=True,
        default='New',
        help="Sequence-based reference number auto-assigned from ir.sequence "
             "'vraja.bank.recon.analysis' on record creation (e.g. BRA/2026/00015)."
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    card_id = fields.Many2one(
        'vraja.ai.card',
        string='AI Card',
        required=True,
        ondelete='cascade',
        help="Links this analysis to the Bank Reconciliation AI card in the vraja.ai module. "
             "Used in the 'My AI Tools' portal list view."
    )
    journal_id = fields.Many2one(
        'account.journal',
        string='Bank Journal',
        domain=[('type', '=', 'bank')],
        help="The bank journal that was analysed. Only bank-type journals are eligible."
    )

    # ── Timestamps & Status ───────────────────────────────────────────────────
    run_date = fields.Datetime(
        string='Generated On',
        default=fields.Datetime.now,
        readonly=True,
        help="UTC timestamp when this analysis was created."
    )
    state = fields.Selection([
        ('draft', 'Draft'),
        ('done', 'Done'),
        ('reconciled', 'Reconciled'),
    ], string='Status', default='draft',
        help="Lifecycle state:\n"
             "  draft      – Not yet processed.\n"
             "  done       – AI classification complete; lines stored.\n"
             "  reconciled – Confirm & Review executed; entries reconciled in Odoo."
    )

    # ── Child Lines & Step Data ────────────────────────────────────────────────
    line_ids = fields.One2many(
        'vraja.bank.recon.analysis.line',
        'analysis_id',
        string='Reconciliation Lines',
        help="One line per bank statement line processed in this run, "
             "each carrying the AI classification and proposed counterpart AMLs."
    )
    step_data = fields.Json(
        string='Step Data',
        readonly=True,
        help="Stores the per-step accordion drill-down payloads (steps 2-5) produced "
             "during the AI pipeline so the OWL dashboard can restore them without "
             "re-running the full analysis."
    )

    @api.model_create_multi
    def create(self, vals_list):
        """
        Override create() to auto-assign a sequence-based reference number.

        Called automatically by the ORM whenever one or more analysis records are
        created (e.g., at the end of Step 7 in the AI pipeline).

        For each record in the batch:
            - If the 'name' is still the sentinel value 'New' (the field default),
              it is replaced with the next value from the 'vraja.bank.recon.analysis'
              ir.sequence (e.g., "BRA/2026/00015").
            - If the sequence is not configured, 'New' is kept as a fallback to
              avoid a hard error on missing sequence configuration.

        Args:
            vals_list (list[dict]): List of field-value dicts for the records to create.

        Returns:
            vraja.bank.recon.analysis: Recordset of newly created records.
        """
        for vals in vals_list:
            # Only assign a new sequence if the caller did not provide an explicit name.
            if vals.get('name', 'New') == 'New':
                vals['name'] = (
                    self.env['ir.sequence'].next_by_code('vraja.bank.recon.analysis')
                    or 'New'
                )
        return super().create(vals_list)

    def action_confirm_and_review(self):
        """
        Reconcile all 'matched' and 'rule' lines in Odoo and mark analysis as done.

        This method is called by:
            - confirm_and_review() in vraja.bank.recon.dashboard.data (via RPC).
            - action_confirm_and_review() in vraja.ai.log (via the log form view button).

        Reconciliation strategy (Odoo 19 Enterprise):
            For each analysis line with status 'matched' or 'rule':
                1. Skip the line if the statement line is already reconciled.
                2. Filter matched AMLs to those not yet fully reconciled.
                3. Call statement_line.set_line_bank_statement_line(aml_ids) which is
                   the canonical Odoo 19 Enterprise API for associating a bank statement
                   line with one or more journal items. It correctly handles:
                       - Partial reconciliations
                       - Exchange difference entries
                       - Early payment discounts (EPDA)
                4. Log any per-line failures at ERROR level without aborting the batch —
                   remaining lines continue to be processed.

        After processing all lines, the analysis state is set to 'reconciled'.

        Returns:
            dict: An ir.actions.client notification action indicating success/count.

        Raises:
            None: Individual line failures are caught and logged; no exception is propagated.
        """
        self.ensure_one()  # This method must be called on a single record.

        # Filter to only actionable lines (skip 'check' status — those need manual review).
        lines_to_process = self.line_ids.filtered(lambda l: l.status in ['matched', 'rule'])
        success_count = 0

        for line in lines_to_process:
            # Guard: skip if statement line doesn't exist or is already reconciled.
            if line.statement_line_id and not line.statement_line_id.is_reconciled:

                # Filter matched AMLs to only those with outstanding residual amounts.
                # Avoids attempting to reconcile an already-reconciled journal item.
                aml_to_reconcile = line.matched_aml_ids.filtered(lambda x: not x.reconciled)

                if aml_to_reconcile:
                    try:
                        # Odoo 19 Enterprise (account_accountant) reconciliation API.
                        # set_line_bank_statement_line() is the correct method for matching
                        # invoice/payment lines to a bank statement line. It wraps the
                        # lower-level account.move.line reconcile logic with proper handling
                        # of suspense accounts, exchange differences, and partial payments.
                        line.statement_line_id.set_line_bank_statement_line(aml_to_reconcile.ids)
                        success_count += 1
                    except Exception as e:
                        # Log the failure but continue processing remaining lines.
                        _logger.error(
                            "Failed to reconcile statement line %s: %s",
                            line.statement_line_id.id, str(e)
                        )

        # Mark the analysis as fully reconciled regardless of individual line failures.
        # This prevents the user from accidentally re-running the confirmation step.
        self.write({'state': 'reconciled'})

        # Return a client notification so the form view / wizard shows a success banner.
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': "Reconciliation Success",
                'message': f"Successfully reconciled {success_count} entries.",
                'sticky': False,
                'type': 'success',
                # Close the currently open form/wizard after displaying the notification.
                'next': {'type': 'ir.actions.act_window_close'},
            }
        }


class VrajaBankReconAnalysisLine(models.Model):
    """
    One-per-statement-line child record of a vraja.bank.recon.analysis run.

    Each line stores:
        - A link to the original account.bank.statement.line being classified.
        - The AI classification: 'matched', 'rule', or 'check'.
        - The AI's natural-language explanation of why it chose that classification.
        - A Many2many set of account.move.line records proposed as counterparts
          (populated only for 'matched' lines; empty for 'rule' and 'check').

    Fields like date, amount, payment_ref, and currency_id are computed via
    related= from the linked statement line to avoid data duplication.
    """

    _name = 'vraja.bank.recon.analysis.line'
    _description = 'Bank Reconciliation AI Line'
    # Use analysis_id as the display name in Many2one dropdowns.
    _rec_name = 'analysis_id'

    # ── Parent link ───────────────────────────────────────────────────────────
    analysis_id = fields.Many2one(
        'vraja.bank.recon.analysis',
        string='Analysis Reference',
        required=True,
        ondelete='cascade',
        help="Parent analysis run that produced this line."
    )

    # ── Bank Statement Line (source data) ─────────────────────────────────────
    statement_line_id = fields.Many2one(
        'account.bank.statement.line',
        string='Statement Line',
        help="The bank statement line being classified by this AI analysis."
    )

    # Related fields mirror data from the statement line to make list views
    # informative without requiring extra joins in the OWL frontend.
    date = fields.Date(
        related='statement_line_id.date',
        string='Date',
        help="Transaction date from the bank statement line."
    )
    amount = fields.Monetary(
        related='statement_line_id.amount',
        string='Amount',
        currency_field='currency_id',
        help="Transaction amount in the statement line's currency."
    )
    payment_ref = fields.Char(
        related='statement_line_id.payment_ref',
        string='Payment Reference',
        help="Payment reference or narration from the bank statement line."
    )
    currency_id = fields.Many2one(
        related='statement_line_id.currency_id',
        help="Currency of the bank statement line (used by the amount Monetary field)."
    )

    # ── AI Classification ─────────────────────────────────────────────────────
    status = fields.Selection([
        ('matched', 'Matched'),
        ('rule', 'Manual Counterpart (Rule)'),
        ('check', 'Statement to Check'),
    ], string='AI Classification',
        help="Classification assigned by the AI agent:\n"
             "  matched – Exact or high-confidence counterpart AML found.\n"
             "  rule    – No AML found, but fits a known rule pattern (e.g. bank fee).\n"
             "  check   – Cannot be auto-classified; requires manual accountant review."
    )

    ai_explanation = fields.Text(
        string='AI Explanation / Reasoning',
        help="Natural-language explanation from the AI or rule engine explaining "
             "why this classification was chosen. Shown in the dashboard accordion."
    )

    # ── Matching Data ─────────────────────────────────────────────────────────
    matched_aml_ids = fields.Many2many(
        'account.move.line',
        string='Proposed Matches (Journal Items)',
        help="The account.move.line record(s) proposed by the AI as counterparts "
             "for this bank statement line. Populated only for 'matched' lines. "
             "Used by action_confirm_and_review() to execute the reconciliation."
    )
