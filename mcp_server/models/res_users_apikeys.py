"""Let users mint ``mcp``-scoped API keys straight from the standard wizard.

Core's "New API Key" wizard has a required ``scope`` field (badges) that it hands
to ``_generate``. We add an ``mcp`` value to it: a key of that scope authenticates
only on ``/mcp`` (see ``auth.get_user_from_api_key``), so a leaked key cannot be
used for general RPC. No core method is overridden.
"""

from odoo import fields, models


class ResUsersApikeysDescription(models.TransientModel):
    _inherit = "res.users.apikeys.description"

    # Required selection: a new value needs a cleanup policy for module
    # uninstall; wizard rows fall back to the default (``rpc``) scope.
    scope = fields.Selection(
        selection_add=[("mcp", "MCP")], ondelete={"mcp": "set default"}
    )
