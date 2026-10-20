# -*- coding: utf-8 -*-pack

{  # App information
    'name': 'All In One Cancel | Cancel Sale Orders | Cancel Purchase Orders | Cancel Picking | Cancel Paid Invoices | Cancel Inventory',
    'category': 'Inventory',
    'version': '20.0.1.0',
    'summary': '''All In One Cancel - Basic This module helps to cancel sale orders, purchase orders, invoices, payments, stock pickings. You can also cancel multiple records from the tree view.Cancel Inventory,Stock Move Cancel,Cancel Order,Cancel Multiple Delivery Order,All in One Delete Cancel Order
    All In One Cancel Sales,Purchases and Delivery,Invoice, All in one Cancel Sale,Purchase,Picking,Sale Cancel,Picking Cancel, Stock Move Cancel,Purchase Cancel, All In One Cancel - Advance | All In One Cancel and Delete, Cancel Reason on Sale, Purchase, Invoice, Picking, All Cancel Extended, Advance All Cancel Extended, All In One Cancel | Cancel Sale Orders | Cancel Purchase Orders | Cancel Picking | Cancel Paid Invoices | Cancel Inventory, All in One Cancel Orders, All in one Mass Cancel, All in one Delete Orders/All in one Cancel Orders-Advance, Cancel Manufacturing Order& linked Sale Order, Cancel Sale Order& linked Manufacturing Order, Stock All In One Cancel | Delete, Cancel Point Of Sale Orders, POS Order Delete/ Delete POS Paid Order, Cancel MRP | Cancel Manufacturing Orders |Cancel Manufacturing | Cancel MRP Orders, Stock Landed Cost Cancel and Reverse, Cancel Invoice Cancel Account Payment, Cancel Stock Moves, Cancel Employee Payslips & Payslip Batches,
    
    vraja_top_sale_integrations
    vraja_featured_apps

    Annulation Vente Achat Facture Odoo | Annulation Massive des Commandes Odoo | Annulation Préparation Inventaire Odoo | Annulation de Facture Payée Odoo | Annulation Tout-en-Un Odoo (French)
    Cancelar Venta Compra Factura Odoo | Cancelación Masiva de Pedidos Odoo | Cancelación de Picking e Inventario Odoo | Cancelación de Factura Pagada Odoo | Cancelación Todo en Uno Odoo (Spanish)
    Odoo Verkoop Inkoop Factuur Annuleren | Odoo Bulk Annulering van Orders | Odoo Picking en Voorraad Annuleren | Odoo Betaalde Factuur Annuleren | Odoo Alles-in-één Annuleren (Dutch)
    Cancelar Venta Compra Factura Odoo | Cancelación Masiva de Pedidos Odoo | Cancelación de Picking e Inventario Odoo | Cancelación de Factura Pagada Odoo | Cancelación Todo en Uno Odoo (Mexican)''',
    'description': "",
    'license': 'OPL-1',

    # Dependencies
    'depends': ['delivery', 'stock', 'stock_delivery', 'sale_stock', 'purchase_stock', 'account'],

    # Views
    "data": [
        'views/stock_picking.xml',
        'views/res_company.xml',
        'views/account_move.xml',
        'views/sale_order.xml',
        'views/purchase_order.xml',
    ],

    # Odoo Store Specific
    'images': ['static/description/cover.gif'],

    # Author
    'author': 'Vraja Technologies',
    'maintainer': 'Vraja Technologies',
    'website': 'www.vrajatechnologies.com',

    # Technical
    'demo': [],
    'installable': True,
    'application': True,
    'auto_install': False,
    'live_test_url': 'http://www.vrajatechnologies.com/contactus',
    'price': '35',
    'currency': 'EUR',

}
# version changelog
