# -*- coding: utf-8 -*-
{
    # App information
    "name": "MCP Assistant | MCP AI Automation ",
    "category": "Productivity",
    "version": "20.0.1.0",
    'sequence': 1,
    "summary":    """
            Chat-style AI assistant that turns plain-English instructions into real, governed actions on your Odoo data through the Model Context Protocol (MCP) Server, so users can ask, search and update records without knowing a single technical term.
            Every conversation is scoped to one Odoo model and one operation, Read, Create, Update or Delete, chosen up front, so the AI agent can only do what it was explicitly asked to do and never wanders into unrelated data.
            Read access stays wide so the AI can search across any model to resolve a customer, product or reference by name before acting, while write access stays locked to the single model and operation configured for that chat.
            Built-in guardrails stop the AI from guessing: it must resolve every name to a real record ID with a live search, ask you to choose when a match is ambiguous, and re-confirm a record's current state right before every update or delete.
            A clean, modern chat interface lives inside Odoo itself, with a sidebar to pick the Odoo model, operation and AI agent, live Allowed / Not allowed badges for Read, Create, Update and Delete rights,.
            conversation history is kept per chat record so you can continue a thread later, with every user prompt and AI response stored and threaded exactly as it happened.
            Per-model access control lets administrators decide exactly which models are exposed to the AI and which CRUD operations are permitted on each one, from a dedicated Enabled Models configuration list.
            Uses the OpenAI API key and model configured in the Vraja AI module (AI Dashboard > Configuration), and connects securely to your own Odoo instance via a scoped MCP API key you generate per user.
            Odoo MCP Server Integration
            Natural Language Odoo Automation
            Odoo MCP AI Agent
            Chat with Odoo Data using ChatGPT
            Odoo AI Assistant (MCP)
            ChatGPT for Odoo
            AI Powered Read Create Update Delete Automation
            AI Chat Assistant for Odoo Data
            AI Agent Access Rights Per Model
            OpenAI Responses API Odoo Connector
            Governed AI Read Write Delete Control
            Model Context Protocol Automation
    """,

    'license': 'OPL-1',
    'description': """""",

    # Dependencies
    "depends": ["base", "mail", "mcp_server", "vraja_ai"],

    # Views
    "data": [
        "security/ir.access.csv",
        "views/res_config_settings_view.xml",
        "views/mcp_operation_view.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "vraja_mcp/static/src/css/mcp_chat.css",
            "vraja_mcp/static/src/js/mcp_chat.js",
            "vraja_mcp/static/src/js/mcp_composer_dragdrop.js",
        ],
    },

    # Odoo Store Specific
    'images': [],

    # Author
    'author': 'Vraja Technologies',
    'maintainer': 'Vraja Technologies',
    'website': 'www.vrajatechnologies.com',
    'live_test_url': 'http://www.vrajatechnologies.com/contactus',

    #Technical
    'demo': [],
    'installable': True,
    'application': True,
    'auto_install': False,
    'price': '',
    'currency': 'USD',
}
