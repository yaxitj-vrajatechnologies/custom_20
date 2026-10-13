# -*- coding: utf-8 -*-
{
    # App information
    'name': 'WhatsApp Notification | WhatsApp Alerts | WhatsApp Marketing | WhatsApp marketing automation Odoo | send offers on WhatsApp Odoo | invoice reminder WhatsApp Odoo | Overdue Invoice Notification | automated WhatsApp follow-ups | WhatsApp marketing for ecommerce  | Recover Carts, Send Offers & Reminders via WhatsApp in Odoo | Boost Sales with Automated WhatsApp Alerts & Campaigns',
    'category': 'Website',
    'version': '20.0.1.0',
    'summary': '''Send automated WhatsApp Notifications to customers for abandoned carts, festival offers, new product launches, discount coupons, personalized pricing, and overdue invoices
            Auto Reminder After X Hours (Abandoned Cart): Automatically notify customers who added products to their cart but did not complete the purchase within a specified time.
            Festival Offers: Notify special customers about festival offers and discounts on configured dates.
            New Product Launch: Send notifications to customers about newly launched products on specified dates.
            Discount Coupons: Notify users about available coupons and discounts according and send them notification through whatsapp.
            Personalized Pricing: Inform special customers about personalized pricing for specific products.
            Overdue Invoice Notification: Notify customers about overdue invoices and request payment.
            WhatsApp Notification Odoo
            Automated Customer Notifications
            Abandoned Cart Reminder
            Personalized Pricing Alerts
            Odoo WhatsApp Integration
            WhatsApp marketing automation
            Odoo WhatsApp Connector
            Automated Messaging Workflow
            Abandoned Cart WhatsApp Reminder
            Odoo E-commerce Notifications
            WhatsApp alerts for order and payment updates
            send invoice payment reminders via WhatsApp Odoo
	    automate WhatsApp marketing campaigns in Odoo
            WhatsApp alerts for product launches and offers in Odoo
            vraja_featured_apps''',
    'license': 'OPL-1',
    'description': "",

    # Dependencies
    'depends': ['whatsapp', 'account', 'website_sale_loyalty'],

    # Views
    'data': [
        'security/ir.access.csv',
        'report/product_report.xml',
        'report/report_action.xml',
        'data/cron_jobs.xml',
        'data/whatsapp_template_data.xml',
        'views/festival_offers_view.xml',
        'views/sale_loyalty_card_view.xml',
        'views/res_config_settings_view.xml',
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
