# -*- coding: utf-8 -*-
{
    # App information
    'name': 'Enhanced Subscription Management | Odoo Sales Subscription Enhancer | Upsell Subscription | Subscription Downgrade',
    'category': 'Sales',
    'version': '20.0.1.0',
    'summary': '''Enhance the Odoo Subscription Sales workflow by adding advanced Upsell and Downgrade management with automated prorated calculations for remaining subscription periods.
                Upsell Order Prorated Calculation: Automatically calculate the prorated amount when a customer upgrades their subscription during the active billing period, ensuring accurate pricing based on the remaining days.
                Subscription Downgrade Management: Allow customers to downgrade their active subscription plans easily while maintaining accurate billing adjustments.
                Automatic Credit Note Creation: When a subscription is downgraded, the system automatically calculates the unused amount for the remaining subscription period and generates a credit note accordingly.
                Accurate Remaining Period Calculation: Ensures precise financial calculations by determining the remaining days in the current subscription cycle.
                Improved Subscription Billing Flexibility: Helps businesses manage mid-cycle upgrades and downgrades without manual calculations.

                Advanced Sales Subscription Module
                Sales Subscription Management Plus
                Subscription Sales Extension
                Smart Sales Subscription Add-on
                Sales Subscription Pro
                Enhanced Subscription Management
                Sales Recurring Subscription Extension
                vraja_featured_apps''',
    'license': 'OPL-1',
    'description': "",

    # Dependencies
    'depends': ['sale_subscription'],

    # Views
    'data': [
        'data/product_data.xml',
        'views/sale_order_view.xml',
    ],

    # Odoo Store Specific
    'images': ['static/description/cover.gif'],

    # Author
    'author': 'Vraja Technologies',
    'website': 'http://www.vrajatechnologies.com',
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
