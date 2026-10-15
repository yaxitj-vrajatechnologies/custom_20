# -*- coding: utf-8 -*-
{
    # App information
    'name': 'AI Email Template Generator | Smart Mailing Template Generator',
    'category': 'Marketing',
    'version': '20.0.1.0.0',
    'summary': '''AI-powered email template generation solution that automatically creates professional HTML email templates based on campaign descriptions using OpenAI, Anthropic Claude, and Google Gemini.
                Supports Text Only and Full Design generation modes to either add a new content section or completely redesign the entire mailing template.
                Clean wizard-based workflow to describe your campaign, select generation type, preview the result, and apply it directly to your Odoo mailing with a single click.
                Integrates with OpenAI (GPT-4.1, GPT-4.1 Mini), Anthropic Claude (claude-sonnet-4-6), and Google Gemini (gemini-2.5-flash) with configurable API keys and models.
                Segment-aware prompt system that automatically includes company branding, logo, website, and contact details in every generated template.
                Dedicated AI Logs section with complete generation history including status, provider, model, tokens consumed, and full generated HTML per run.
                
                ai email generator odoo, ai email template odoo, openai email marketing odoo, claude email generator, gemini email template, 
                odoo ai mailing, automated email template odoo, ai html email odoo, dynamic email template odoo, ai campaign generator odoo,
                AI-Powered Email Campaign Generator, Automated HTML Email Template Generator, AI Email Marketing Template Builder,
                AI Mailing Template Designer for Odoo, Intelligent Email Template Creator for Odoo, Email Template Automation with AI for Odoo,
                Smart Mailing Template Builder with AI, AI-Driven Email Template Designer for Odoo, AI Email Marketing Automation,
                Smart Email Content Generator, Odoo AI Email Marketing, Multi-AI Email Template Generator, AI Email Design Assistant,
                vraja_ai''',
    'description': """""",
    'license': 'OPL-1',

    # Dependencies
    'depends': ['mass_mailing'],

    # Views
    'data': [
        'security/ir.access.csv',
        'data/ir_sequence.xml',
        'data/ir_cron.xml',
        'views/mailing_mailing_views.xml',
        'views/ai_provider_config_views.xml',
        'wizard/ai_email_generate_wizard_views.xml',
        'views/email_template_log_view.xml',
    ],

    # JS/XML Assets for the Custom Print Button
    'assets': {
        'web.assets_backend': [
            'ai_email_template_generator/static/src/css/ai_generate.css',
            'ai_email_template_generator/static/src/js/ai_email_template.js',
            'ai_email_template_generator/static/src/xml/ai_email_template.xml',
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
    'price': '49',
    'currency': 'EUR',
}
