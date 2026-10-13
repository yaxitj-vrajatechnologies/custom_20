# -*- coding: utf-8 -*-
from odoo import fields, models

class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    mcp_ai_operations_api_key = fields.Char(
        string="Odoo MCP API Key",
        config_parameter="mcp_ai_operations.mcp_api_key",
        help="An active Odoo API key with the MCP-only scope. Create it from "
        "the profile of the user whose Odoo access the AI should use.",
    )
