# -*- coding: utf-8 -*-
{  
    # App information
    'name': 'AI Product Recommendation Agent | Alternate, Accessory & Catalog Intelligence',
    'category': 'Inventory',
    'version': '20.0.1.0',
    'sequence': 1,
    'summary': '''Complete AI-powered solution for automatically analysing your product caalog and recommending the most relevant alternative and accessory products for each item.
                Integrates with OpenAI and supports multiple LLM models including GPT-4.1,GPT-4.1 Mini, GPT-5, GPT-5 Mini, GPT-5.4, and GPT-5.4 Mini.
                Clean 6-step guided workflow to select products, configure AI settings, run the analysis, and review and apply the results from a single interface.
                Uses product category, tags, price, attributes, and real sales co-purchase history as data sources for generating intelligent product relationship suggestions.
                Supports bulk product selection through manual search, Select All, or Excel file import using Internal Reference.
                Configurable AI settings including Suggestion Type, Minimum Confidence Level,Price Tolerance, and Maximum Suggestions per Product.
                Scheduled Auto Run via cron jobs to automatically run the AI analysis daily without any manual intervention.
                Dedicated AI Logs section with complete run history including status, configuration used, tokens consumed, and per-product breakdown of all suggestions applied.
                AI-generated suggestions are applied directly to the Accessory Products and Alternative Products fields on each product record for immediate upselling andcross-selling.

                AI Product Recommendation for Odoo, AI-Powered Product Alternate & Accessory Linking, Smart Product Relationship Management with OpenAI, 
                Automated Alternative & Accessory Product Suggestions, OpenAI Product Catalog Analysis in Odoo, AI Cross-Sell and Upsell Product Recommendations, 
                Product Alternate Suggestion using GPT in Odoo, Odoo AI Product Accessory Linking, Smart Product Catalog Management with AI, 
                AI-Based Product Relationship Builder for Odoo, Automated Product Upsell & Cross-Sell Management, OpenAI Integration for Product Recommendations in Odoo, 
                GPT-Powered Product Alternate & Accessory Module, AI Product Linking and Recommendation System for Odoo, Intelligent Product Catalog Optimization with OpenAI

                odoo ai, product recommendation ai, ai product recommendation, alternate products, accessory products, product suggestions, catalog enrichment, 
                ai catalog management, product linking, upsell products, cross sell products, openai odoo, ai sales recommendation, smart product matching, 
                product intelligence, ai merchandising, ecommerce ai, product relationship management, ai accessories, ai alternatives, product catalog ai, 
                automated product recommendations, inventory intelligence, ai product analysis, product recommendation engine
AI-powered alternative product recommendation for Odoo
AI accessory product recommendation app for Odoo
Odoo AI module for upselling and cross-selling products
Odoo product recommendation based on category, tags, attributes, and sales history
Bulk AI product relationship analysis using Excel import in Odoo
Odoo AI app to apply alternative and accessory products automatically''',
    'license': 'OPL-1',
    'description': """""",

    # Dependencies
    'depends': ['vraja_ai', 'website_sale'],

    'external_dependencies': {
        'python': ['xlsxwriter', 'openpyxl', 'requests'],
        # xlsxwriter :- Used when creating Excel (.xlsx) files from scratch.
        # openpyxl :- Used when reading or modifying existing Excel files.
        # requests :- Used for calling external APIs or websites.
    },

    # Views
    'data': [
        'data/cron.xml',
        'views/product_ai_log_view.xml',
    ],

    # JS/XML Assets for the Custom Print Button
    'assets': {
        'web.assets_backend': [
            'product_ai_agent_vts/static/src/js/product_ai_dashboard.js',
            'product_ai_agent_vts/static/src/xml/dashboard_template.xml',
        ],
    },

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
    'post_init_hook': '_post_init_generate_product_card',
    'uninstall_hook': '_uninstall_product_alt_acc_ai',
    'price': '99',
    'currency': 'EUR',
}
