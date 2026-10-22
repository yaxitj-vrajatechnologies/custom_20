# -*- coding: utf-8 -*-
{
    # App Information
    'name': 'Fruugo Marketplace Integration | Odoo Fruugo Connector | Fruugo Product Feed',
    'category': 'eCommerce',
    'version': '20.0.1.0',
    'summary': '''The Odoo Fruugo Connector is a powerful, fully automated integration solution designed to seamlessly synchronize your Odoo store products with the global Fruugo marketplace. 
                Whether you are a small retailer or a large enterprise, this module simplifies the complexities of multi-channel e-commerce by providing an robust engine that automatically generates highly detailed, 
                Fruugo-compliant XML product feeds directly from your existing Odoo inventory.
                Supports product variants, stock status, VAT pricing, scheduled daily feed generation, feed logs with attached XML files, and multi-feed configuration.
                
                Fruugo Feed, Fruugo Connector, Fruugo Integration, Fruugo XML Feed, Odoo Fruugo,
                Fruugo Product Feed, Marketplace Feed, Fruugo eCommerce.''',
    'description': "",
    'license': 'OPL-1',

    # Dependencies
    'depends': ['stock', 'sale_management', 'website_sale'],

    # Views / Data
    'data': [
        'security/ir.access.csv',
        'data/ir_cron.xml',
        'views/fruugo_feed_view.xml',
        'views/fruugo_feed_log_view.xml',
        'views/fruugo_category_view.xml',
        'views/product_category_view.xml',
        'views/product_template_view.xml',
        'wizard/import_fruugo_category_wizard_view.xml',
        'views/menu.xml',
    ],

    # Odoo Store Specific
    'images': ['static/description/cover.gif'],

    # Author
    'author': 'Vraja Technologies',
    'website': 'https://www.vrajatechnologies.com',
    'maintainer': 'Vraja Technologies',
    'live_test_url': 'https://www.vrajatechnologies.com/contactus',

    # Technical
    'demo': [],
    'installable': True,
    'application': True,
    'auto_install': False,
    'price': '99',
    'currency': 'EUR',
}
# version changelog
# 19.0.1.0 - Initial release.
