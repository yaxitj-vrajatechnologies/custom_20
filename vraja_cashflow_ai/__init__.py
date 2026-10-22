# -*- coding: utf-8 -*-
from . import models
from . import wizard

def post_init_hook(env):
    """Create the Cashflow Dashboard card on installation."""
    card = env['vraja.ai.card'].search([('vraja_common_store', '=', 'cashflow')], limit=1)
    if not card:
        env['vraja.ai.card'].create({
            'vraja_common_card_name': 'Smart Cashflow AI Dashboard',
            'vraja_common_card_description': (
                'AI-powered cashflow intelligence. Connects to your Odoo data and uses ChatGPT to deliver instant CFO-level insights'
            ),
            'vraja_common_store': 'cashflow',
            'vraja_common_card_active': True,
        })

def uninstall_hook(env):
    """Remove the Cashflow Dashboard card on uninstallation."""
    cards = env['vraja.ai.card'].search([('vraja_common_store', '=', 'cashflow')])
    cards.unlink()
    # Remove the logs
    logs = env['vraja.ai.log'].search([('vraja_common_log_store', '=', 'cashflow')])
    logs.unlink()
