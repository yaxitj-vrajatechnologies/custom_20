from . import models


def _post_init_generate_product_card(env):

    card_obj = env['vraja.ai.card'].sudo()
    existing_card = card_obj.search([('vraja_common_card_name', '=', 'Product Alternate & Accessory')], limit=1)

    if not existing_card:
        card_obj.create({
            'vraja_common_card_name': 'Product Alternate & Accessory',
            'vraja_common_card_description': 'Analyse your product catalog and let AI recommend the best alternatives and accessories for each product..',
            'vraja_common_card_active': True,
            'vraja_common_store': 'product_alt_acc',
        })


def _uninstall_product_alt_acc_ai(env):
    env['vraja.ai.card'].sudo().search([('vraja_common_card_name', '=', 'Product Alternate & Accessory')]).unlink()

    env['vraja.ai.log'].sudo().search([('vraja_common_log_store', '=', 'product_alt_acc')]).unlink()
