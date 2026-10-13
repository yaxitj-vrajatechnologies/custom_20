# -*- coding: utf-8 -*-
{
    # App information
    "name": "Vendor Pricelist AI Update | AI Supplier Price List Automation",
    "category": "Purchases",
    "version": "20.0.1.0.0",
    "sequence": 1,
    "summary": """
            Generate a vendor's current price list, upload the price file the vendor sends back (any structure) and let AI match it and update your Vendor Pricelists.

            * Generates an XLSX file of the vendor's current Vendor Pricelist lines (product.supplierinfo).
            * Reads the vendor's returned price file and matches it against your existing products with AI (OpenAI, using the API key and model from the Vraja AI configuration).
            * Extracts the latest price, quantity, unit, discount, lead time, start date and end date, converting pack sizes and units to the price of the pack you buy.
            * Lets you review matched products and unmatched products, and download the AI result file.
            * Resolves unmatched products by mapping them to an existing product, or by creating a new product from an existing one, only when you choose to.
            * Applies the result to the Vendor Pricelist with automatic history handling: updates the open line with the same start date, creates a new line otherwise, and closes older open lines the day before the new start date.
            * Keeps the AI response, token usage and run date on every record, with a full chatter history.
            * Editable AI prompt per record, pre-filled from a default prompt and the current company name.

            AI Vendor Pricelist Update for Odoo
            AI Supplier Price List Update
            Odoo AI Vendor Price Import
            Odoo Supplier Price List Automation
            Odoo AI Purchase Price Update
            Odoo Vendor Price File Matching with AI
            Odoo Vendor Pricelist Excel and PDF Import with AI
    """,

    "license": "OPL-1",
    "description": """""",

    # Dependencies
    "depends": ["product", "purchase", "mail", "vraja_ai"],

    # Views
    "data": [
        "security/ir.access.csv",
        "data/ir_sequence.xml",
        "views/vendor_pricelist_update_views.xml",
        "views/ai_prompt_vts_view.xml",
        "data/ai_prompt_data.xml",
    ],

    "external_dependencies": {
        "python": ["openpyxl", "requests"],
    },

    "assets": {
        "web.assets_backend": [
            "ai_vendor_pricelist_update_vts/static/src/js/binary_field_dragdrop.js",
            "ai_vendor_pricelist_update_vts/static/src/scss/binary_field_dragdrop.scss",
        ],
    },

    # Odoo Store Specific
    "images": ["ai_vendor_pricelist_update_vts/static/description/cover.gif"],

    # Author
    "author": "Vraja Technologies",
    "maintainer": "Vraja Technologies",
    "website": "www.vrajatechnologies.com",
    "live_test_url": "http://www.vrajatechnologies.com/contactus",

    # Technical
    "demo": [],
    "installable": True,
    "application": True,
    "auto_install": False,
    "price": "",
    "currency": "USD",
}
