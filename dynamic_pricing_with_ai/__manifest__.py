# -*- coding: utf-8 -*-
{  
    # App information
    'name': 'AI Dynamic Pricing Agent | AI Dynamic Pricing | ChatGPT (OpenAI) | Claude (Anthropic) | Gemini',
    'category': 'Inventory',
    'version': '20.0.1.0',
    'sequence': 1,
    'summary': """Complete AI-powered dynamic pricing solution that automatically analyses sales velocity, stock levels, and competitor market prices to suggest the optimal price for every product across each customer segment and applies them directly to Odoo pricelists.
                Integrates with OpenAI, Claude (Anthropic), and Google Gemini.
                Clean 6-step guided workflow to configure business context, select products, define segment pricing rules, run AI batches, and review and apply the results from a single interface.
                Supports segment-based pricing for B2B, Retailer, Wholesaler, Distributor, B2C, Walk-in, and VIP customers with independent margin limits and mapped pricelists per segment.
                Competitor price tracking via configurable URLs where the AI fetches the market price, converts it to company currency, and applies the correct segment-based undercut percentage automatically.
                Scheduled Auto-Run via cron jobs to automatically analyse all products and apply updated prices to pricelists daily without any manual intervention.
                Dedicated AI Logs section with complete run history including status, AI provider, LLM model, tokens consumed, and per-product breakdown of all pricing decisions applied.
                odoo dynamic pricing, ai pricing engine, competitor price tracking, segment based pricing, b2b pricing ai, pricelist automation, ai price optimization, openai odoo pricing, dynamic pricelist odoo, stock based pricing, demand based pricing, margin protection ai, ai price suggestion, wholesale pricing ai, retail pricing ai, competitor undercut pricing, odoo ai pricelist, automated pricing odoo, price intelligence odoo, ai pricing dashboard
                Smart Pricing Engine with AI
                Auto Pricelist Update for B2B
                Dynamic Pricelist Automation with AI
                Segment Based Dynamic Pricing
                Automated Pricelist Update with AI
                Dynamic Pricing per Customer Segment
                Odoo Dynamic Pricing Automation
                Stock and Demand Based Pricing Engine
                AI Competitor Price Analysis for Odoo
                Intelligent Price Optimization with AI
                Auto Pricelist Update with AI
                AI Price Intelligence for Odoo
                openai odoo, claude odoo, gemini odoo, anthropic odoo, chatgpt odoo, multi-provider ai,
                AI Agent, AI Agents, vraja_ai_agents
                """,
    'license': 'OPL-1',
    'description': """""",

    # Dependencies
    'depends': ['vraja_ai', 'website_sale','stock'],

    # Views
    'data': [
        'security/ir.access.csv',
        'data/ir_cron_data.xml',
        'views/dynamic_price_log_view.xml',
        'views/dynamic_pricing_batch_view.xml',
    ],

    # JS/XML Assets for the Custom Print Button
    'assets': {
        'web.assets_backend': [
            'dynamic_pricing_with_ai/static/src/css/dynamic_pricing_dashboard.css',
            'dynamic_pricing_with_ai/static/src/css/dp_analysis_dashboard.css',
            'dynamic_pricing_with_ai/static/src/js/dynamic_pricing_card_dashboard.js',
            'dynamic_pricing_with_ai/static/src/js/dp_analysis_dashboard.js',
            'dynamic_pricing_with_ai/static/src/xml/dp_dashboard_template.xml',
            'dynamic_pricing_with_ai/static/src/xml/dp_analysis_dashboard_template.xml',
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
    'post_init_hook': '_post_init_generate_dynamic_price_card',
    'uninstall_hook': '_uninstall_dynamic_pricing_with_ai',
    'price': '99',
    'currency': 'EUR',
}
