# -*- coding: utf-8 -*-
{
    # App information
    'name': 'Xero Odoo Integration | Odoo Xero Connector | Bi-directional Xero Odoo Integration',
    'category': 'Website',
    'version': '20.0.1.0',
    'summary': '''Seamless Bi-Directional Accounting Synchronization Between Odoo & Xero
Managing financial data across multiple platforms can be time-consuming and error-prone. Our Xero Odoo Integration Module provides a powerful, secure, and fully automated bi-directional synchronization between Odoo ERP and Xero Accounting.
This integration ensures real-time financial accuracy while significantly reducing manual accounting work.
Our Xero Odoo Integration module provides a powerful and secure bi-directional synchronization between Odoo ERP and Xero Accounting, enabling businesses to automate their entire financial workflow. This advanced Odoo Xero Connector allows seamless import and export of customers, vendors, products, invoices, bills, payments, credit notes, accounts, taxes, analytic accounts, purchase orders, prepayments, and overpayments between both systems. With real-time financial data synchronization, companies can eliminate manual data entry, reduce accounting errors, and ensure accurate reporting across departments. Whether you want to sync invoices from Odoo to Xero, import payments from Xero to Odoo, or automate tax and account mapping, this integration ensures smooth and reliable accounting automation. Designed with secure API connectivity and multi-company support, our Odoo to Xero sync solution is ideal for businesses that use Odoo for operations and Xero for accounting, providing complete financial transparency and operational efficiency.
Xero Odoo Integration
Odoo Accounting Automation
Xero Invoice Sync Odoo
Odoo Export Bills to Xero
Odoo Import Credit Notes from Xero
Odoo ERP integration with Xero accounting software
vraja_accounting_solution''',
    'license': 'OPL-1',

    # Dependencies
    'depends': ['account','purchase','stock'],

    # Views
    'data': [
        'security/ir.access.csv',
        'wizard/xero_operations_view.xml',
        'wizard/xero_instance_view.xml',
        'data/cron.xml',
        'views/xero_partner_map_view.xml',
        'views/xero_account_map_view.xml',
        'views/xero_product_map_view.xml',
        'views/xero_tax_map_view.xml',
        'views/xero_analytic_account_map_view.xml',
        'views/xero_contact_group_view.xml',
        "views/move_data_queue.xml",
        'views/credit_note_data_queue.xml',
        'views/xero_view.xml',
        'views/xero_log_view.xml',
        'views/account_move_view.xml',
        'views/account_payment_view.xml',
        'views/purchase_order_view.xml',
    ],
    # Odoo Store Specific
    'images': ['static/description/cover.gif'],

    # Author
    'author': 'Vraja Technologies',
    'website': 'http://www.vrajatechnologies.com',
    'maintainer': 'Vraja Technologies',

    # Technical
    'demo': [],
    'installable': True,
    'application': True,
    'auto_install': False,
    'live_test_url': 'https://www.vrajatechnologies.com/contactus',
    'price': '98',
    'currency': 'EUR',

}
# version changelog
