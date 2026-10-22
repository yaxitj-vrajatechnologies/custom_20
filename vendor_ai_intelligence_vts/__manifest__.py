# -*- coding: utf-8 -*-
{  
    # App information
    'name': 'AI Vendor Intelligence | AI-Based Supplier Recommendation | ChatGPT (OpenAI) | Claude (Anthropic) | Gemini',
    'version': '20.0.1.0',
    'category': 'Purchases',
    'summary': """Vendor AI Intelligence Agent helps procurement teams automatically track, score, and rank their suppliers to ensure maximum supply chain efficiency.
                The module analyzes all historical purchase orders and stock receipts to calculate performance scores for Delivery Punctuality, Quantity Fulfillment, Price Consistency, and Lead Time Accuracy. It then sends this data to the Vraja AI/OpenAI Code Interpreter to receive deep, actionable insights. Users can view the fastest delivering vendors, category kings, red flag warnings, and a detailed action plan.
                
                Key Features:
                - Dynamic Vendor Intelligence Dashboard with Interactive Pie Charts
                - Automatic scoring for Delivery (35%), Fulfillment (25%), Price (20%), and Lead Time (20%)
                - Forecast period configuration (All Time vs Selected Data)
                - Automatic AI tracking of Worst Delays, Fastest Deliveries, and Best Rates
                - Category King identification for product-specific vendor optimization
                - Red Flag alerts for recurring supply chain issues
                - Manual or scheduled workbook generation via Cron
                - Manual or scheduled AI analysis via Cron
                - Beautiful, rich HTML historical AI execution logs
                
                Which vendor usually delays,
                Which vendor gives fastest delivery,
                Which vendor provides best rates,
                Which vendor is most reliable for specific product categories,
                odoo ai vendor, vendor intelligence ai, supplier performance ai, ai procurement, purchase planning ai, vendor scoring,
                supplier evaluation, vendor optimization, late delivery alert, vendor prediction, supplier recommendation, vendor ranking,
                category kings, procurement ai, supply chain ai, purchase forecasting, vendor replenishment, purchase order ai, openai vendor,
                openai odoo, claude odoo, gemini odoo, anthropic odoo, chatgpt odoo, multi-provider ai,
                AI Agent, AI Agents, vraja_ai_agents
                """,
    'license': 'OPL-1',
    'description': """AI-powered vendor performance scoring, supplier recommendation, and supply chain insights for Odoo Purchase.""",

    # Dependencies
    'depends': ['purchase', 'stock', 'vraja_ai'],

    # Views
    'data': [
        'security/ir.access.csv',
        'data/ir_cron.xml',
        'views/vendor_ai_log_view.xml',
    ],

    # JS/XML Assets for the Custom Print Button
    'assets': {
        'web.assets_backend': [
            'vendor_ai_intelligence_vts/static/src/js/vraja_vendor_ai_dashboard.js',
            'vendor_ai_intelligence_vts/static/src/css/vendor_ai_dashboard.css',
            'vendor_ai_intelligence_vts/static/src/xml/dashboard_template.xml',
        ],
    },

    # Odoo Store Specific
    'images': ['static/description/cover.gif'],

    # Author
    'author': 'Vraja Technologies',
    'website': 'www.vrajatechnologies.com',
    'maintainer': 'Vraja Technologies',
    'live_test_url': 'http://www.vrajatechnologies.com/contactus',

    # Technical
    'demo': [],
    'installable': True,
    'application': True,
    'auto_install': False,
    'post_init_hook': '_post_init_generate_vendor_intelligence',
    'uninstall_hook': '_uninstall_vendor_intelligence',
    'price': '99',
    'currency': 'EUR',
}
