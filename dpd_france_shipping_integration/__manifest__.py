# -*- coding: utf-8 -*-pack
{
    # App information
    'name': 'DPD France Shipping Integration',
    'category': 'Website',
    'version': '20.0.1.1',
    'summary': '''At 𝗩𝗿𝗮𝗷𝗮 𝗧𝗲𝗰𝗵𝗻𝗼𝗹𝗼𝗴𝗶𝗲𝘀, we continue to innovate as a globally renowned 𝘀𝗵𝗶𝗽𝗽𝗶𝗻𝗴 𝗶𝗻𝘁𝗲𝗴𝗿𝗮𝘁𝗼𝗿 𝗮𝗻𝗱 𝗢𝗱𝗼𝗼 𝗰𝘂𝘀𝘁𝗼𝗺𝗶𝘇𝗮𝘁𝗶𝗼𝗻 𝗲𝘅𝗽𝗲𝗿𝘁. Our widely accepted shipping connections are made to easily interface with Odoo, simplifying everything from creating labels to tracking shipments—all from a single dashboard. We’re excited to introduce DPD France Odoo Connectors your one stop solution for seamless global shipping management, now available on the Odoo App Store! At Vraja Technologies, we continue to be at the forefront of Odoo shipping integrations, ensuring your logistics run smoothly across countries. Users also search using these keywords Vraja Odoo Shipping Integration, Vraja Odoo shipping Connector, Vraja Shipping Integration, Vraja shipping Connector, DPD France Odoo Shipping Integration, DPD France Odoo shipping Connector, DPD France Shipping Integration, DPD France shipping Connector, DPD France vraja technologies, dpd vraja technologies, Odoo DPD France, DPD shipping, DPD shipping integration.
Integrate DPD France with Odoo to create shipments, generate DPD shipping labels, update tracking numbers, and manage delivery orders directly from Odoo. Ideal for French eCommerce, retail, wholesale, and warehouse shipping operations.
Odoo shipping automation with DPD France connector
DPD France parcel shipment management in Odoo
DPD France parcel shipment management in Odoo
Odoo delivery order DPD France shipment integration
Best DPD France shipping connector for Odoo
Odoo DPD France integration for online stores
Odoo courier integration for French businesses
        vraja_shipping_solution France shipping integrations by Vraja''',
    'description': "",
    'depends': ['delivery','stock','stock_delivery'],
    'live_test_url': 'http://www.vrajatechnologies.com/contactus',
      'data': [
        'views/res_company.xml'
    ],
    'images': ['static/description/cover.gif'],
    'author': 'Vraja Technologies',
    'maintainer': 'Vraja Technologies',
    'website': 'www.vrajatechnologies.com',
    'demo': [],
    'installable': True,
    'application': True,
    'auto_install': False,
    'price': '121',
    'currency': 'EUR',
    'license': 'OPL-1',
}
#Version Log
#18.0 initial version
#18.1 - change to latest API CreateShipmentWithLabelsBc
#19.0.1.1 - implement api from CreateShipmentWithLabelsBc Multishipment
