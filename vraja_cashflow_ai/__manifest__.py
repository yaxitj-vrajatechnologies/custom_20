# -*- coding: utf-8 -*-
{
    # App information
    'name': 'AI Cashflow Intelligence Agent | CFO Cashflow AI | Smart Cashflow Analyzer | ChatGPT (OpenAI) | Claude (Anthropic) | Gemini',
    'category': 'Accounting',
    'version': '20.0.1.0',
    'summary': """Cashflow AI is an advanced Odoo module developed by Vraja Technologies that brings CFO-level financial intelligence directly into your Odoo backend. 
                It connects to the AI provider of your choice — OpenAI (ChatGPT), Claude (Anthropic), or Google Gemini — to analyse your real-time Accounts Receivable (AR),
                Accounts Payable (AP), bank balances, expense pipelines, and sales/purchase order pipelines — then delivers actionable insights, liquidity scoring,
                cash runway forecasts, and a full executive summary.
                The module is built on top of the Vraja AI common platform (vraja_ai) and the Odoo account module.
                It uses a token-optimised CSV approach to minimise AI API costs while maximising the quality of AI-generated intelligence.
                Stop guessing about your cash position. Cashflow AI connects to your Odoo accounting data and uses your preferred AI provider to deliver instant CFO-level insights.

                odoo cashflow ai, ai cashflow analysis, cashflow intelligence, cfo ai, cashflow forecasting, liquidity forecasting, ai financial analysis,
                financial intelligence, cash runway forecasting, odoo accounting ai, finance ai, executive financial reporting, accounts receivable analysis,
                accounts payable analysis, ai kpi dashboard, cashflow dashboard, financial risk analysis, automated cfo reports, smart cashflow analyzer,
                openai odoo, claude odoo, gemini odoo, anthropic odoo, chatgpt odoo, multi-provider ai,
                AI Agent, AI Agents, vraja_ai_agents
                """,
    'license': 'OPL-1',
    'description': """""",

    # Dependencies
    'depends': ['vraja_ai', 'account'],

    # Views
    'data': [
        'security/ir.access.csv',
        'data/vraja_cashflow_cron.xml',
        'wizard/vraja_cashflow_wizard_views.xml',
        'views/vraja_cashflow_analysis.xml',
        'views/vraja_cashflow_log_view.xml',
        'views/report_cashflow_analysis.xml',
    ],

    'post_init_hook': 'post_init_hook',
    'uninstall_hook': 'uninstall_hook',

    'assets': {
        'web.assets_backend': [
            'vraja_cashflow_ai/static/src/css/cashflow_dashboard.css',
            'vraja_cashflow_ai/static/src/js/cashflow_dashboard.js',
            'vraja_cashflow_ai/static/src/xml/cashflow_dashboard_template.xml',
        ],
    },

    'external_dependencies': {
        'python': ['openai', 'requests'],
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
    'price': '99',
    'currency': 'EUR',
}
