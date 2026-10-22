from . import models

def _post_init_generate_vendor_intelligence(env):
    """Create the Vendor Intelligence card after install."""
    card_obj = env['vraja.ai.card'].sudo()
    existing_card = card_obj.search([('vraja_common_store', '=', 'ai_vendor_intel')], limit=1)

    if not existing_card:
        existing_card = card_obj.create({
            'vraja_common_card_name': 'AI Vendor Intelligence',
            'vraja_common_card_description': 'Scores vendor performance (Delivery, Quality, Price) and provides AI-driven purchasing recommendations.',
            'vraja_common_card_active': True,
            'vraja_common_store': 'ai_vendor_intel',
        })
        existing_card.generate_ai_vendor_file()

def _uninstall_vendor_intelligence(env):
    card_obj = env['vraja.ai.card'].sudo()
    cards = card_obj.search([('vraja_common_store', '=', 'ai_vendor_intel')])
    if cards:
        cards.unlink()
        
    log_obj = env['vraja.ai.log'].sudo()
    logs = log_obj.search([('vraja_common_log_store', '=', 'ai_vendor_intel')])
    if logs:
        logs.unlink()
