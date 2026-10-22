# -*- coding: utf-8 -*-
"""
account_bank_statement_line.py
================================
Extends the native Odoo account.bank.statement.line model to expose an
RPC-callable method for triggering AI reconciliation directly from the
native bank reconciliation widget (OWL BankRecKanbanRenderer).

This extension follows the Odoo "extend, don't replace" philosophy:
no existing methods are overridden; only a new @api.model method is added.
"""

from odoo import models, api
import logging

_logger = logging.getLogger(__name__)


class AccountBankStatementLine(models.Model):
    """
    Extension of account.bank.statement.line for the Vraja Bank Reconciliation AI module.

    This class adds a single RPC endpoint (action_run_ai_reconciliation) that can be
    called from the OWL bank reconciliation kanban widget to trigger an AI-assisted
    exact-amount matching pass for the selected statement lines.

    Design note:
        This is intentionally a lightweight hook. The full 7-step AI pipeline
        lives in vraja.bank.recon.dashboard.data.run_full_ai_analysis(). This method
        provides a quick in-widget match for individual lines without leaving the
        native reconciliation view.
    """

    _inherit = 'account.bank.statement.line'

    @api.model
    def action_run_ai_reconciliation(self, active_ids):
        """
        RPC endpoint for triggering AI reconciliation from the OWL kanban widget.

        Called directly from the OWL BankRecKanbanRenderer component when the user
        clicks the "AI Match" action button within the native Odoo bank reconciliation
        widget. Processes only the statement lines whose IDs are passed in active_ids.

        Algorithm (prototype / lightweight version):
            For each unreconciled statement line in active_ids:
                1. Search for an account.move.line with:
                       - amount_residual != 0  (has an outstanding balance)
                       - account_id.reconcile = True  (on a reconcilable account)
                       - balance == -line.amount  (equal and opposite to the bank line)
                2. If a match is found, call line.reconcile() with the matched AML.
                3. Increment success_count on each successful reconciliation.

        Note on sign convention:
            A bank debit (money in, positive amount) corresponds to an A/R credit
            entry (negative balance on account.move.line in Odoo's convention).
            Hence the search uses ``balance == -line.amount``.

        Production improvement path:
            Replace the simple balance= lookup with a call to
            vraja.ai.card._ask_llm() for AI-assisted matching that considers
            partner, date proximity, payment reference, and partial amounts.

        Context flag:
            skip_account_move_synchronization=True prevents the ORM from
            re-posting the parent account.move during reconciliation, which
            would be unnecessary overhead for this operation.

        Args:
            active_ids (list[int]): IDs of the account.bank.statement.line records
                                    selected in the kanban widget for AI matching.

        Returns:
            dict: {
                'success'      : bool,  # Always True (failures are caught per-line)
                'message'      : str,   # Human-readable summary of results
                'matched_count': int,   # Number of lines successfully reconciled
            }
        """
        lines = self.browse(active_ids)
        _logger.info("AI Auto-Match triggered for lines: %s", active_ids)

        success_count = 0

        for line in lines.filtered(lambda l: not l.is_reconciled):
            # Build a domain to find a counterpart AML with the opposite balance.
            # balance field on account.move.line holds the raw debit/credit sign.
            domain = [
                ('amount_residual', '!=', 0),          # Must have an outstanding balance
                ('account_id.reconcile', '=', True),   # Must be on a reconcilable account
                ('balance', '=', -line.amount)          # Equal and opposite to the bank line
            ]
            matching_aml = self.env['account.move.line'].search(domain, limit=1)

            if matching_aml:
                try:
                    # Execute Odoo's native reconciliation via ORM.
                    # skip_account_move_synchronization avoids re-posting the move,
                    # which would be unnecessary overhead here.
                    line.with_context(skip_account_move_synchronization=True).reconcile(
                        lines_vals_list=[{'id': matching_aml.id}]
                    )
                    success_count += 1
                except Exception as e:
                    # Log the failure but continue processing remaining lines.
                    _logger.error("AI Match failed for line %s: %s", line.id, e)

        return {
            'success': True,
            'message': f'AI successfully matched {success_count} transactions!',
            'matched_count': success_count,
        }
