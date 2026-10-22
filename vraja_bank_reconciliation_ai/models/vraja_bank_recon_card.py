# -*- coding: utf-8 -*-
"""
vraja_bank_recon_card.py
==========================
Extends the vraja.ai.card model from the base vraja_ai module to register
the 'bank_recon' store value and override card action methods to route the
Bank Reconciliation AI card to its custom OWL dashboard and log view.

Design philosophy:
    The vraja.ai.card model acts as a registry of all Vraja AI tools.
    Each module registers its own selection option in the vraja_common_store
    field and overrides the card action methods to provide module-specific
    navigation. The super() call is used as the final fallback so the base
    module's behaviour is preserved for non-bank_recon cards.
"""

from odoo import models, fields


class VrajaAICard(models.Model):
    """
    Extends vraja.ai.card to register the Bank Reconciliation AI tool.

    The base vraja.ai.card model displays a list of all enabled Vraja AI modules
    as clickable "cards" on the AI hub page. Each card has two primary actions:
        - action_review_dashboard() → Open the module's main dashboard.
        - action_log_view()         → Open the module's filtered AI log list.

    This class:
        1. Adds 'bank_recon' to the vraja_common_store selection field so the card can
           be configured for the Bank Reconciliation AI module.
        2. Overrides action_review_dashboard() to open the custom OWL client action
           ('vraja_bank_recon.dashboard') when the card is a bank_recon card.
        3. Overrides action_log_view() to pre-apply a domain filter that shows only
           bank_recon log entries when accessing logs from a bank_recon card.
    """

    _inherit = 'vraja.ai.card'

    # ── Store discriminator (selection extension) ─────────────────────────────
    vraja_common_store = fields.Selection(
        selection_add=[('bank_recon', 'Bank Reconciliation AI')],
        ondelete={'bank_recon': 'set null'},
        help="Registers 'bank_recon' as a valid store tag for the Bank Reconciliation AI card. "
             "ondelete='set null' ensures removal of this module does not break existing records."
    )

    def action_review_dashboard(self):
        """
        Open the Bank Reconciliation AI OWL dashboard when triggered from a bank_recon card.

        This method overrides the base vraja.ai.card implementation.

        For bank_recon cards:
            Returns an ir.actions.client action with tag='vraja_bank_recon.dashboard'.
            The tag must match the key used in registry.category('actions').add()
            in bank_recon_dashboard.js. Odoo's action manager will look up this tag
            and render the registered OWL component.

        For all other card types:
            Falls through to super().action_review_dashboard() to preserve the base
            module's default routing behaviour.

        Returns:
            dict: ir.actions.client action pointing to the Bank Recon dashboard,
                  or the result of super() for other card types.
        """
        self.ensure_one()
        if self.vraja_common_store == 'bank_recon':
            return {
                'type': 'ir.actions.client',
                'tag': 'vraja_bank_recon.dashboard',
                'name': 'Bank Reconciliation AI',
            }
        # Delegate to the base module for all other store types.
        return super().action_review_dashboard()

    def action_log_view(self):
        """
        Open the AI log list view pre-filtered to bank_recon entries.

        This method overrides the base vraja.ai.card implementation.

        For bank_recon cards:
            Calls super() to get the base act_window action structure, then modifies:
                - domain=[]  : Clears any existing domain so the search filter
                               (search_default_store_bank_recon) handles filtering.
                - context    : Sets 'search_default_store_bank_recon' to activate the
                               pre-configured search filter in the log list view, and
                               'default_vraja_common_log_store' so new logs created
                               from this view are automatically tagged as 'bank_recon'.

        For all other card types:
            Returns the base module's unmodified log action.

        Returns:
            dict: ir.actions.act_window action for the AI log list,
                  contextually scoped to bank_recon records.
        """
        self.ensure_one()
        # Get the base action structure (model, views, etc.) from the parent module.
        res = super().action_log_view()
        if self.vraja_common_store == 'bank_recon':
            # Clear the domain — let the search filter handle scoping.
            res['domain'] = []
            # search_default_store_bank_recon activates the predefined search filter
            # in the vraja.ai.log list view that filters to bank_recon store entries.
            res['context'] = {
                'search_default_store_bank_recon': 1,
                'default_vraja_common_log_store': 'bank_recon',
            }
        return res
