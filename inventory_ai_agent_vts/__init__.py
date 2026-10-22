from . import models


def _post_init_generate_inventory_report(env):
    """Create the Low stock card and generate the initial stock export after install."""
    card_obj = env['vraja.ai.card'].sudo()

    existing_card = card_obj.search([('vraja_common_card_name', '=', 'Low Stock Alert')], limit=1)

    if not existing_card:
        existing_card = card_obj.create({
            'vraja_common_card_name': 'Low Stock Alert',
            'vraja_common_card_description': 'It will calculate stock data and sales performance & show the products to be restocked with better vendor details.',
            'vraja_common_card_active': True,
            'vraja_common_store': 'ai_low_stock',
        })
        existing_card.generate_ai_inventory_file()


def _uninstall_low_stock_ai_analysis(env):
    card_obj = env['vraja.ai.card'].sudo()

    cards = card_obj.search([('vraja_common_card_name', '=', 'Low Stock Alert')], limit=1)

    if cards:
        cards.unlink()

    # Delete all low stock AI logs
    log_obj = env['vraja.ai.log'].sudo()
    logs = log_obj.search([('vraja_common_log_store', '=', 'ai_low_stock')])
    if logs:
        logs.unlink()
