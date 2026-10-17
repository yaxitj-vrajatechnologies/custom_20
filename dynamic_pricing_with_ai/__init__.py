from . import models


def _post_init_generate_dynamic_price_card(env):

    card_obj = env['vraja.ai.card'].sudo()

    existing_card = card_obj.search([('vraja_common_card_name', '=', 'Dynamic Pricing with AI')], limit=1)

    if not existing_card:
        card_obj.create({
            'vraja_common_card_name': 'Dynamic Pricing with AI',
            'vraja_common_card_description': 'AI-powered pricing engine — analyses sales, stock & competitor data to auto-suggest prices per segment and apply them to Odoo pricelists.',
            'vraja_common_card_active': True,
            'vraja_common_store': 'dynamic_pricing',
        })

def _uninstall_dynamic_pricing_with_ai(env):

    # Delete Dynamic Pricing AI Logs
    logs = env['vraja.ai.log'].sudo().search([('vraja_common_log_store', '=', 'dynamic_pricing')])
    logs.unlink()

    # Delete AI Generated Pricelist Items
    ai_pricelist_items = env['product.pricelist.item'].sudo().search([('is_ai_price', '=', True)])
    ai_pricelist_items.unlink()

    # Delete Dashboard Card
    cards = env['vraja.ai.card'].search([('vraja_common_card_name', '=', 'Dynamic Pricing with AI')])
    cards.unlink()


