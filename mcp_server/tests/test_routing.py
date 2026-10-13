"""Tests for the route precedence of the MCP URLs (``ir.http`` override)."""

import functools
import types
from unittest.mock import patch

from odoo.tests import common, tagged


class _OwnController:
    pass


class _OtherController:
    pass


_OwnController.__module__ = "odoo.addons.mcp_server.controllers.fake"
_OtherController.__module__ = "odoo.addons.other_module.controllers.fake"


def _endpoint(controller_class, methods):
    """A routing-map endpoint shaped like core's (a partial of a bound method)."""
    bound = types.MethodType(lambda self: None, controller_class())
    endpoint = functools.partial(bound)
    endpoint.routing = {"methods": methods}
    return endpoint


@tagged("much_unit", "post_install", "-at_install")
class TestMcpRoutePrecedence(common.TransactionCase):
    def test_only_overlapping_methods_are_dropped(self):
        """Another module keeps a method this module does not serve on its URL."""
        own = _endpoint(_OwnController, ["POST"])
        other_post = _endpoint(_OtherController, ["POST"])
        other_get = _endpoint(_OtherController, ["GET"])
        other_any = _endpoint(_OtherController, None)
        elsewhere = _endpoint(_OtherController, ["POST"])
        rules = [
            ("/mcp", own),
            ("/mcp", other_post),
            ("/mcp", other_get),
            ("/mcp", other_any),
            ("/elsewhere", elsewhere),
        ]
        with patch(
            "odoo.http.routing_map._generate_routing_rules", return_value=iter(rules)
        ):
            kept = list(self.env["ir.http"]._generate_routing_rules([], None))
        self.assertEqual(
            [endpoint for _url, endpoint in kept], [own, other_get, elsewhere]
        )
