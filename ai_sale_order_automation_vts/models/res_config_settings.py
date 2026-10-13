# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    ai_sale_order_mcp_api_key = fields.Char(
        string="Odoo MCP API Key",
        config_parameter="ai_sale_order_automation_vts.mcp_api_key",
        help="API key generated from My Profile > Account Security > New API Key "
        "(scope 'MCP only'), from the mcp_server module. This lets the OpenAI "
        "model call back into this Odoo through /mcp.",
    )
