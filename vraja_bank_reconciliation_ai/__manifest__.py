# -*- coding: utf-8 -*-
{
    # App information
    'name': 'AI Bank Reconciliation Agent | Bank Reconciliation | Automatic Bank Reconciliation | ChatGPT (OpenAI) | Claude (Anthropic) | Gemini',
    'category': 'Accounting',
    'version': '20.0.1.0',
    'summary': """Unlock the full potential of Artificial Intelligence in your Odoo accounting workflow with the Vraja AI Bank Reconciliation module, a comprehensive framework designed to completely automate your bank statement matching processes. 
                Stop wasting countless hours manually attempting to match hundreds of individual bank lines; instead, let our sophisticated 7-step autonomous AI agent effortlessly process your transactions. The system utilizes highly advanced heuristics, exact-amount matching, fuzzy logic algorithms, and deep, seamless integration with your native Odoo reconciliation models to ensure unparalleled accuracy.
                This robust framework automatically classifies complex financial statements perfectly into 'Matched', 'Rule-Based', and 'Needs Check' categories to eliminate guesswork and significantly boost your daily accounting efficiency. It directly reads your native Account Reconcile Models (writeoff rules) to automatically and intelligently handle regular fees, service charges, and recurring payments.
                By harnessing cutting-edge generative AI processing—including OpenAI models—the agent can instantly understand ambiguous transaction labels, expertly map them directly to your outstanding invoices and vendor bills, and adapt to your unique financial patterns over time. 
                Everything is tied together with a beautifully sleek, modern, real-time reactive OWL frontend dashboard featuring an interactive animated stepper that keeps your accounting teams fully informed at every stage of the reconciliation pipeline. Maximize your ERP's productivity and transform your financial back-office operations into a fully automated, AI-driven powerhouse. 

                AI bank reconciliation, artificial intelligence, automatic bank reconciliation, machine learning banking, fin-tech odoo, 
                automated accounting workflow, smart matching, exact amount matching, auto reconcile, bank statement matching, auto-validate, 
                generative ai, openai finance, vraja ai, rule-based automation, automated financial categorization, fast accounting, 
                enterprise finance tools, modern erp AI integrations, 
                openai odoo, claude odoo, gemini odoo, anthropic odoo, chatgpt odoo, multi-provider ai,
                AI Agent, AI Agents, vraja_ai_agents
              """,
    'license': 'OPL-1',
    'description': """""",

    # Dependencies
    'depends': ['vraja_ai', 'accountant'],

    # Views / Data
    'data': [
        'security/ir.access.csv',
        'data/vraja_bank_recon_data.xml',
        'views/vraja_bank_recon_analysis_view.xml',
        'views/vraja_bank_recon_log_view.xml',
        'views/bank_recon_dashboard_actions.xml',
        'wizard/vraja_bank_recon_wizard_view.xml',
    ],

    'uninstall_hook': 'uninstall_hook',

    'assets': {
        'web.assets_backend': [
            'vraja_bank_reconciliation_ai/static/src/dashboard/**/*',
        ],
    },

    'external_dependencies': {
        'python': ['requests', 'openai'],
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
