# -*- coding: utf-8 -*-
{
    # App information
    'name': 'Odoo Quickbooks Online Connector | USA | Odoo QuickBooks Connector | Odoo QuickBooks USA Integration | Odoo Intuit QuickBooks Connector',
    'category': 'Website',
    'version': '20.0.1.0.0',
    'summary': '''Streamline your financial operations by seamlessly connecting your Odoo ERP with QuickBooks Online. This integration ensures data accuracy by synchronizing key records—including invoices, bills, payments, customers, vendors, and products—between both systems.
            Eliminate manual data entry and minimize errors by automating the flow of information. The connector facilitates the mapping of essential details like taxes, accounts, payment terms, and departments. You can export invoices and bills from Odoo to QuickBooks, as well as sync customer and vendor payments, partner details, and products. A key feature enables you to send payment links directly to customers from within Odoo.
            To suit your workflow, you have the flexibility to perform synchronizations either manually or on an automated schedule.
            Keywords: 
            vraja_quickbooks_integrations, vraja_ecommerce_integrations, QuickBooks Online Integration, Odoo QuickBooks Connector, QuickBooks Customer Sync, QuickBooks Payment Import, Vraja Technologies QuickBooks Odoo Connector, QuickBooks Product Sync, QuickBooks Online Odoo Connector, QuickBooks Partner Sync, QuickBooks Odoo Connector, Sync QuickBooks with Odoo, QuickBooks Integration, accounting app, QuickBooks Online Payment Links, QuickBooks Invoice Export, Connect QuickBooks to Odoo, Vraja QuickBooks Odoo Connector, QuickBooks Payment Export, Intuit Odoo Connector, Odoo Connector, quickbooks online connector, Automatic QuickBooks Sync, Manual QuickBooks Sync, quickbooks connector, odoo quickbooks, QuickBooks Online,vraja_accounting_solution''',
    'license': 'OPL-1',

    # Dependencies
    'depends': ["quickbooks_common_connector_vts","stock"],

    # Views
    'data': [
        'security/ir.access.csv',
        'data/quickbook_server_action.xml',
        'wizard/instance_wizard_view.xml',
        # 'views/partner_view.xml',
        'views/qbo_product_map.xml',
        'views/quickbooks_view.xml',
        'views/product_template_view.xml',
        'views/account_move_view.xml',
        'views/account_payment_view.xml',
        'views/qkb_vendor_map_view.xml',
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
    'price': '49',
    'currency': 'EUR',

}
# version changelog
