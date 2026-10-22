# -*- coding: utf-8 -*-pack
{

    # App information
    'name': 'Rental Management',
    'category': 'Sales',
    'version': '20.0.1.0',
    'summary': '''Rental Management Rental Management, Rental Odoo, Rent, Rental, Car Rent, Vehicle Rent, Clothes Rental, Luxury Rental, Odoo Rental, Repair, Odoo Rental Management, Odoo Rental App, Simply Access Management, Advanced Property Sale and Renal, Equipment Rental. Property Manager, Property Rental Management, Advanced Equipment Rental Management, Online Fleet Rental, Website Fleet Rental, Sale Rental Management, Fleet Rental Management, Lease / Rental Management, Odoo Rental Sale, Rental Items, Rental Check Availability, Dynamic Field Mapping, CRM to Sales Dynamic FIeld Mapping, Generic Rental management, Odoo Marketplace, Odoo Marketplace Rent, Holiday Property Rental, Rental hOliday Module, POS Rental management,Odoo Rental Dashboard, Odoo Rental Bundle,Rental Order Management Odoo,Inventory for Rental Products Odoo,Odoo Rental Scheduling,Equipment Rental Odoo,Vehicle Rental System Odoo,Rental Asset Maintenance Odoo,Property Rentals,Tool and Equipment Rentals,Fashion and Accessories Rentals,Sports Rentals
    vraja_featured_apps''',
    'license': 'OPL-1',

    # Dependencies
    'depends': ['sale_renting', 'repair'],

    # Views
    'data': [
        'security/ir.access.csv',
        'data/ir_cron.xml',
        'views/rental_order.xml',
        'wizard/create_advance_payment_wizard_view.xml',
        'wizard/repair_order_wizard.xml',
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
