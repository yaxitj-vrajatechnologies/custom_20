# -*- coding: utf-8 -*-
{
    # App Information
    'name': 'Odoo Google Merchant Center Integration | Odoo Google Shopping | Google Merchant Center Next',
    'category': 'eCommerce',
    'version': '20.0.1.0',
    'summary': '''Google Merchant Center Next Integration for Odoo. Import Google Product Taxonomy, map product categories, configure dynamic feed columns, 
                auto-generate XML/TSV product feeds, and submit them to Google via SFTP. Supports multi-feed, multi-language, cron automation, feed logs, and feed preview. 
                Compatible with Google Shopping, Facebook Catalog, Pinterest Ads, and TikTok catalog feed formats.
                
                Google Shopping Feed, Google Merchant Center, GMC Next, Product Feed SFTP,
                Google Product Taxonomy, Shopping Ads, Feed Automation, Odoo eCommerce Integration.
                Vraja Google, Vraja GMC''',
    'description': "",
    'license': 'OPL-1',

    # Dependencies
    'depends': ['website_sale', 'stock', 'sale_management'],

    # External Python Libraries
    'external_dependencies': {
        'python': ['paramiko', 'requests'],
    },

    # Views / Data
    'data': [
        'security/ir.access.csv',
        'data/gmc_feed_column_data.xml',
        'data/ir_cron.xml',
        'wizard/import_google_category_wizard_view.xml',
        'views/google_product_taxonomy_view.xml',
        'views/gmc_feed_view.xml',
        'views/gmc_feed_column_view.xml',
        'views/gmc_feed_log_view.xml',
        'views/product_template_view.xml',
        'views/res_config_settings_view.xml',
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
    'price': '79',
    'currency': 'EUR',
}