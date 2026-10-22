# -*- coding: utf-8 -*-
from . import models
from . import wizard

def uninstall_hook(env):
    """Remove the Cashflow Dashboard card on uninstallation."""
    cards = env['vraja.ai.card'].search([('vraja_common_store', '=', 'bank_recon')])
    cards.unlink()
    # Remove the logs
    logs = env['vraja.ai.log'].search([('vraja_common_log_store', '=', 'bank_recon')])
    logs.unlink()