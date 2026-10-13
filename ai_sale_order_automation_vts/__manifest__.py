# -*- coding: utf-8 -*-
{
    # App information
    "name": "Auto Create Sale Order Through MCP | AI Sale Order Automation",
    "category": "Sales",
    "version": "20.0.1.1.0",
    'sequence': 1,
    "summary": """
            Upload a customer order in any format (photo, scanned or digital PDF, Excel/CSV, Outlook message or ODT) and let Claude AI turn it into a draft Odoo sale order.
            
            * Extracts customer, order reference, delivery date and ordered products from the document.
            * Creates the draft sale order in Odoo through the MCP server, matching customers and products against live Odoo data.
            * Never creates new products and never confirms the order.
            * Supports customer-specific instructions, so each customer's order format and unit rules can be handled without changing the common prompts.
            * Learns from manual corrections through reusable product mappings.
            * Shows extracted lines, ignored lines and token usage for review.
            
            AI Sale Order Automation for Odoo
            AI Sales Order Creator from Documents
            Odoo AI Order Entry Automation
            Odoo MCP Sale Order Automation
            Auto Create Sale Order Through MCP
            Odoo MCP PDF to Sale Order
            Odoo MCP Excel Order Import with AI
            14. Odoo MCP Handwritten Order Scanner

    """,

    'license': 'OPL-1',
    'description': """""",

    # Dependencies
    "depends": ["base", "sale", "mail", "vraja_ai"],

    # Views
    "data": [
        "security/ir.access.csv",
        "data/ir_sequence_data.xml",
        "data/ai_prompt_data.xml",
        "views/order_automation_view.xml",
        "views/ai_product_mapping_view.xml",
        "views/ai_prompt_view.xml",
        "views/res_partner_views.xml",
        "views/res_config_settings_views.xml",
    ],

    "external_dependencies": {
        "python": ["openpyxl", "pymupdf"],
    },

    "assets": {
        "web.assets_backend": [
            "ai_sale_order_automation_vts/static/src/js/many2many_binary_dragdrop.js",
            "ai_sale_order_automation_vts/static/src/scss/many2many_binary_dragdrop.scss",
        ],
    },

    # Odoo Store Specific
    'images': ["ai_sale_order_automation_vts/static/description/cover.gif"],

    # Author
    'author': 'Vraja Technologies',
    'maintainer': 'Vraja Technologies',
    'website': 'www.vrajatechnologies.com',
    'live_test_url': 'http://www.vrajatechnologies.com/contactus',

    # Technical
    'demo': [],
    'installable': True,
    'application': True,
    'auto_install': False,
    'price': '',
    'currency': 'USD',
}
