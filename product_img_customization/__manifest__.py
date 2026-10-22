{
    # App information
    'name': 'One Click Multi Variant Image Sync',
    'category': 'Product',
    'version': '20.0.1.0',
    'summary': '''One Click Multi Variant Image Sync | In Odoo's current system, product images must be uploaded individually for each variant. This can be time-consuming, especially for products with multiple variations in color and size.Odoo Product Variant Image Sync,Bulk Variant Image Upload Odoo,Multi-Variant Image Update Odoo,Odoo Product Template Image Sync,One-Click Product Image Sync Odoo,Odoo Variant Image Automation,Odoo Image Synchronization for Variants,Odoo Multi-Variant Image Management,Odoo eCommerce Multi-Variant Image Support,Mass Image Update for Variants Odoo,Odoo Product Attribute Image Mapping, vraja_top_sale_integrations
vraja_featured_apps''',
    'license': 'OPL-1',

    # Dependencies
    "depends": ["product", "website_sale"],

    # Views
    "data": [
        "views/product_view.xml",
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
    'price': '40',
    'currency': 'EUR',

}
