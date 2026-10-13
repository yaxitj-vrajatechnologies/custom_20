import logging
import xmlrpc.client as xmlrpclib  # nosec
from unittest.mock import patch

from odoo.exceptions import (
    AccessDenied,
    AccessError,
    MissingError,
    UserError,
    ValidationError,
)
from odoo.tests.common import HttpCase, tagged
from odoo.tools import mute_logger

from ..controllers.api import (
    XMLRPC_FAULT_CODES,
    MCPObjectController,
    _generate_xmlrpc_fault,
)

_logger = logging.getLogger(__name__)


@tagged("much_unit", "post_install", "-at_install")
class TestXMLRPCControllers(HttpCase):
    def test_generate_xmlrpc_fault(self):
        """Test the helper function that generates XML-RPC fault responses."""
        code = 400
        message = "Test error message"
        result = _generate_xmlrpc_fault(code, message)

        self.assertIsInstance(result, str)
        self.assertIn("methodResponse", result)
        self.assertIn("fault", result)
        self.assertIn(str(code), result)
        self.assertIn(message, result)

    def test_xmlrpc_fault_codes_defined(self):
        """Test that all expected fault codes are defined."""
        expected_codes = {
            "bad_request": 400,
            "unauthorized": 401,
            "forbidden": 403,
            "not_found": 404,
            "rate_limit": 429,
            "internal_error": 500,
        }
        self.assertEqual(XMLRPC_FAULT_CODES, expected_codes)


@tagged("much_unit", "post_install", "-at_install")
class TestMCPCommonController(HttpCase):
    def setUp(self):
        super().setUp()
        from ..controllers import utils

        # Enable MCP globally by default
        self.env["ir.config_parameter"].sudo().set_str("mcp_server.enabled", "True")
        utils.clear_mcp_caches()

    def test_common_controller_mcp_disabled(self):
        """Test XML-RPC common request when MCP is globally disabled."""
        from ..controllers import utils

        # Disable MCP globally
        self.env["ir.config_parameter"].sudo().set_str("mcp_server.enabled", "False")
        utils.clear_mcp_caches()

        request_data = xmlrpclib.dumps((), "version", allow_none=1)
        response = self.url_open(
            "/mcp/xmlrpc/common",
            data=request_data,
            headers={"Content-Type": "text/xml"},
        )

        # xmlrpclib.loads raises a Fault exception for fault responses
        with self.assertRaises(xmlrpclib.Fault) as cm:
            xmlrpclib.loads(response.content)

        self.assertEqual(cm.exception.faultCode, 403)
        self.assertIn("MCP Server is disabled globally", cm.exception.faultString)

    @patch("odoo.service.common.dispatch")
    def test_common_controller_success(self, mock_dispatch):
        """Test successful XML-RPC common request."""
        mock_dispatch.return_value = {"server_version": "16.0"}
        request_data = xmlrpclib.dumps((), "version", allow_none=1)

        response = self.url_open(
            "/mcp/xmlrpc/common",
            data=request_data,
            headers={"Content-Type": "text/xml"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("Content-Type"), "text/xml")

        result = xmlrpclib.loads(response.text)
        self.assertEqual(result[0][0], {"server_version": "16.0"})
        mock_dispatch.assert_called_once_with("version", ())

    @mute_logger("odoo.addons.mcp_server.controllers.api")
    @patch("odoo.service.common.dispatch")
    def test_common_controller_exception(self, mock_dispatch):
        """Test exception handling in common controller."""
        mock_dispatch.side_effect = Exception("Unexpected error")
        request_data = xmlrpclib.dumps((), "test_method", allow_none=1)

        response = self.url_open(
            "/mcp/xmlrpc/common",
            data=request_data,
            headers={"Content-Type": "text/xml"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("Content-Type"), "text/xml")
        self.assertIn("fault", response.text)
        self.assertIn("500", response.text)


@tagged("much_unit", "post_install", "-at_install")
class TestMCPDatabaseController(HttpCase):
    def setUp(self):
        super().setUp()
        from ..controllers import utils

        # Enable MCP globally by default
        self.env["ir.config_parameter"].sudo().set_str("mcp_server.enabled", "True")
        utils.clear_mcp_caches()

    def test_db_controller_mcp_disabled(self):
        """Test XML-RPC database request when MCP is globally disabled."""
        from ..controllers import utils

        # Disable MCP globally
        self.env["ir.config_parameter"].sudo().set_str("mcp_server.enabled", "False")
        utils.clear_mcp_caches()

        request_data = xmlrpclib.dumps((), "list", allow_none=1)
        response = self.url_open(
            "/mcp/xmlrpc/db",
            data=request_data,
            headers={"Content-Type": "text/xml"},
        )

        # xmlrpclib.loads raises a Fault exception for fault responses
        with self.assertRaises(xmlrpclib.Fault) as cm:
            xmlrpclib.loads(response.content)

        self.assertEqual(cm.exception.faultCode, 403)
        self.assertIn("MCP Server is disabled globally", cm.exception.faultString)

    @patch("odoo.addons.mcp_server.controllers.api._dispatch_db_service")
    def test_db_controller_success(self, mock_dispatch):
        """Test successful XML-RPC database request."""
        mock_dispatch.return_value = ["test_db1", "test_db2"]
        request_data = xmlrpclib.dumps((), "list", allow_none=1)

        response = self.url_open(
            "/mcp/xmlrpc/db", data=request_data, headers={"Content-Type": "text/xml"}
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("Content-Type"), "text/xml")

        result = xmlrpclib.loads(response.text)
        self.assertEqual(result[0][0], ["test_db1", "test_db2"])
        mock_dispatch.assert_called_once_with("list", ())

    @mute_logger("odoo.addons.mcp_server.controllers.api")
    @patch("odoo.addons.mcp_server.controllers.api._dispatch_db_service")
    def test_db_controller_exception(self, mock_dispatch):
        """Test exception handling in database controller."""
        mock_dispatch.side_effect = Exception("Database error")
        request_data = xmlrpclib.dumps((), "test_method", allow_none=1)

        response = self.url_open(
            "/mcp/xmlrpc/db", data=request_data, headers={"Content-Type": "text/xml"}
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("Content-Type"), "text/xml")
        self.assertIn("fault", response.text)
        self.assertIn("500", response.text)

    def _db_fault(self, method="list"):
        request_data = xmlrpclib.dumps((), method, allow_none=1)
        response = self.url_open(
            "/mcp/xmlrpc/db", data=request_data, headers={"Content-Type": "text/xml"}
        )
        with self.assertRaises(xmlrpclib.Fault) as cm:
            xmlrpclib.loads(response.content)
        return cm.exception

    @mute_logger("odoo.addons.mcp_server.controllers.api")
    @patch("odoo.addons.mcp_server.controllers.api._dispatch_db_service")
    def test_db_controller_user_errors_keep_their_message(self, mock_dispatch):
        """An Odoo user error keeps its message and core's fault code, not a 500.

        The codes match core's ``/xmlrpc/2`` (2 user error, 3 refused login,
        4 access error), so XML-RPC clients classify them as business errors.
        """
        cases = [
            (UserError("Nope"), 2),
            (ValidationError("Bad value"), 2),
            (AccessError("Not yours"), 4),
            (MissingError("Gone"), 2),
            (AccessDenied(), 3),
        ]
        for exc, code in cases:
            with self.subTest(exc=type(exc).__name__):
                mock_dispatch.side_effect = exc
                fault = self._db_fault()
                self.assertEqual(fault.faultCode, code)
                self.assertNotIn("Internal", fault.faultString)
                self.assertIn(exc.args[0], fault.faultString)

    @mute_logger(
        "odoo.addons.mcp_server.controllers.api",
        "odoo.addons.mcp_server.controllers.error_sanitizer",
    )
    @patch("odoo.addons.mcp_server.controllers.api._dispatch_db_service")
    def test_db_controller_internal_error_is_generic(self, mock_dispatch):
        """An unexpected error returns the generic message, not its raw text."""
        mock_dispatch.side_effect = RuntimeError("secret detail in /opt/odoo")
        fault = self._db_fault()
        self.assertEqual(fault.faultCode, 500)
        self.assertEqual(fault.faultString, "Internal server error")

    @mute_logger("odoo.addons.mcp_server.controllers.api")
    def test_db_controller_unknown_method_not_found(self):
        """A method the reduced db service does not offer is a 404 fault."""
        fault = self._db_fault("drop")
        self.assertEqual(fault.faultCode, 404)
        self.assertIn("Method not found: drop", fault.faultString)


@tagged("much_unit", "post_install", "-at_install")
class TestMCPObjectController(HttpCase):
    def setUp(self):
        super().setUp()
        self.controller = MCPObjectController()
        from ..controllers import utils

        # Enable MCP globally by default
        self.env["ir.config_parameter"].sudo().set_str("mcp_server.enabled", "True")
        utils.clear_mcp_caches()

    def test_object_controller_mcp_disabled(self):
        """Test XML-RPC object request when MCP is globally disabled."""
        from ..controllers import utils

        # Disable MCP globally
        self.env["ir.config_parameter"].sudo().set_str("mcp_server.enabled", "False")
        utils.clear_mcp_caches()

        params = ("test_db", 1, "password", "res.users", "search", [])
        request_data = xmlrpclib.dumps(params, "execute_kw", allow_none=1)
        response = self.url_open(
            "/mcp/xmlrpc/object",
            data=request_data,
            headers={"Content-Type": "text/xml"},
        )

        # xmlrpclib.loads raises a Fault exception for fault responses
        with self.assertRaises(xmlrpclib.Fault) as cm:
            xmlrpclib.loads(response.content)

        self.assertEqual(cm.exception.faultCode, 403)
        self.assertIn("MCP Server is disabled globally", cm.exception.faultString)

    def test_object_controller_rate_limit_fault_advertises_retry_after(self):
        """The rate-limit fault (429) carries the same Retry-After as /mcp."""
        from ..controllers import rate_limiting

        params = self.env["ir.config_parameter"].sudo()
        params.set_str("mcp_server.enable_rate_limiting", "True")
        params.set_str("mcp_server.request_limit", "10")
        rate_limiting._api_limiter.clear()
        self.addCleanup(rate_limiting._api_limiter.clear)
        uid = self.env.uid
        for _ in range(10):
            rate_limiting.record_api_request(uid, self.env.cr.dbname)

        request_data = xmlrpclib.dumps(
            (self.env.cr.dbname, uid, "pw", "res.partner", "search_count", [[]]),
            "execute_kw",
            allow_none=1,
        )
        response = self.url_open(
            "/mcp/xmlrpc/object",
            data=request_data,
            headers={"Content-Type": "text/xml"},
        )
        with self.assertRaises(xmlrpclib.Fault) as cm:
            xmlrpclib.loads(response.content)
        self.assertEqual(cm.exception.faultCode, 429)
        self.assertEqual(
            response.headers.get("Retry-After"),
            str(rate_limiting.RATE_LIMIT_WINDOW_MINUTES * 60),
        )

    def test_object_controller_non_execute_kw_method(self):
        """Test rejection of non-execute_kw methods."""
        from ..controllers import utils

        # Ensure MCP is enabled
        self.env["ir.config_parameter"].sudo().set_str("mcp_server.enabled", "True")
        utils.clear_mcp_caches()

        params = ("test_db", 1, "password", "res.users", "search")
        request_data = xmlrpclib.dumps(params, "invalid_method", allow_none=1)

        response = self.url_open(
            "/mcp/xmlrpc/object",
            data=request_data,
            headers={"Content-Type": "text/xml"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("Content-Type"), "text/xml")
        self.assertIn("fault", response.text)
        self.assertIn("400", response.text)
        self.assertIn("Unsupported method", response.text)

    def test_object_controller_insufficient_params(self):
        """Test handling of insufficient parameters."""
        from ..controllers import utils

        # Ensure MCP is enabled
        self.env["ir.config_parameter"].sudo().set_str("mcp_server.enabled", "True")
        utils.clear_mcp_caches()

        params = ("test_db", 1)  # Not enough params for execute_kw
        request_data = xmlrpclib.dumps(params, "execute_kw", allow_none=1)

        response = self.url_open(
            "/mcp/xmlrpc/object",
            data=request_data,
            headers={"Content-Type": "text/xml"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("Content-Type"), "text/xml")
        self.assertIn("fault", response.text)
        self.assertIn("400", response.text)
        self.assertIn("Insufficient parameters", response.text)

    def test_mcp_object_dispatch_non_execute_kw(self):
        """Test _mcp_object_dispatch rejects non-execute_kw methods."""
        with self.assertRaises(xmlrpclib.Fault) as cm:
            self.controller._mcp_object_dispatch("invalid_method", [])

        self.assertEqual(cm.exception.faultCode, 400)
        self.assertIn("Unsupported method", cm.exception.faultString)

    def test_mcp_object_dispatch_insufficient_params(self):
        """Test _mcp_object_dispatch validates parameter count."""
        with self.assertRaises(xmlrpclib.Fault) as cm:
            self.controller._mcp_object_dispatch("execute_kw", ("db", 1))

        self.assertEqual(cm.exception.faultCode, 400)
        self.assertIn("Insufficient parameters", cm.exception.faultString)

    @patch("odoo.addons.mcp_server.controllers.utils.sanitize_model_name")
    def test_mcp_object_dispatch_invalid_model_name(self, mock_sanitize):
        """Test _mcp_object_dispatch validates model names."""
        mock_sanitize.side_effect = ValueError("Invalid model name")
        params = ("test_db", 1, "password", "invalid.model", "search")

        with self.assertRaises(xmlrpclib.Fault) as cm:
            self.controller._mcp_object_dispatch("execute_kw", params)

        self.assertEqual(cm.exception.faultCode, 400)
        self.assertIn("Invalid model name", cm.exception.faultString)
