"""Tests for the dedicated ``mcp`` API-key scope.

Two auth surfaces are pinned here:

* ``auth.get_user_from_api_key`` now probes ``_check_credentials(scope="mcp")``
  before falling back to ``scope="rpc"``, so a key stored with scope ``mcp`` or
  ``rpc`` authenticates on ``POST /mcp``.
* The blast-radius promise: an ``mcp``-scoped key is NOT a general RPC key -- core
  ``_check_credentials(scope="rpc", ...)`` rejects it.

Plus the wizard plumbing that lets users mint such keys: the ``mcp`` value added to
the ``scope`` field of the standard "New API Key" wizard reaches ``_generate``
through core's ``@check_identity``-gated ``make_key`` (HttpCase).

Mirrors the HttpCase + ``_generate`` key-minting harness of ``test_mcp_protocol``
and ``test_authentication``.
"""

import json
import time
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from odoo.http import request_var
from odoo.tests import common, tagged

from ..controllers import auth, rate_limiting, utils
from .test_helpers import create_test_user, grant_mcp_access

# Must match mcp_server/controllers/mcp.py.
PREFERRED_PROTOCOL_VERSION = "2025-11-25"


@tagged("much_unit", "post_install", "-at_install")
class TestApiKeyScope(common.HttpCase):
    """``mcp``-scoped and NULL-scope keys at the ``/mcp`` bearer door."""

    def setUp(self):
        super().setUp()
        utils.clear_mcp_caches()
        rate_limiting._api_limiter.clear()

        unique_id = str(int(time.time() * 1000))[-6:]
        self.mcp_user = create_test_user(
            self.env,
            "MCP Scope User",
            f"mcp_scope_user_{unique_id}",
            email=f"mcp_scope_{unique_id}@example.com",
        )
        grant_mcp_access(self.mcp_user)

        env_as_user = self.env(user=self.mcp_user)
        expiration = datetime.now() + timedelta(hours=12)
        # A key minted with the dedicated ``mcp`` scope...
        self.mcp_key = env_as_user["res.users.apikeys"]._generate(
            "mcp", "MCP Scoped Key", expiration
        )
        # ...and a legacy NULL-scope key (no longer valid on any door).
        self.null_key = env_as_user["res.users.apikeys"]._generate(
            None, "Legacy Null Scope Key", expiration
        )
        # ...and an explicit ``rpc``-scope key (general RPC access).
        self.rpc_key = env_as_user["res.users.apikeys"]._generate(
            "rpc", "RPC Scoped Key", expiration
        )

        # Enable MCP globally and drop any stale cached toggle value.
        self.env["ir.config_parameter"].sudo().set_str("mcp_server.enabled", "True")
        utils.clear_mcp_caches()

    def _post_rpc(self, body, api_key):
        """POST a JSON-RPC ``body`` dict to ``/mcp`` with a bearer key."""
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }
        return self.url_open("/mcp", data=json.dumps(body), headers=headers)

    def _get_rest(self, path, api_key):
        """GET a legacy REST ``path`` with an ``X-API-Key`` header."""
        return self.url_open(
            path, headers={"X-API-Key": api_key, "Accept": "application/json"}
        )

    def test_mcp_user_reads_only_own_api_keys(self):
        """MCP membership grants no read access to other users' key metadata."""
        self.env(user=self.env.ref("base.user_admin"))["res.users.apikeys"]._generate(
            "rpc", "Admin Key", datetime.now() + timedelta(hours=12)
        )
        keys = self.env(user=self.mcp_user)["res.users.apikeys"].search([])
        self.assertTrue(keys)
        self.assertEqual(keys.user_id, self.mcp_user)

    def test_mcp_scoped_key_authenticates_on_rpc(self):
        """A key from ``_generate("mcp", ...)`` authenticates on ``/mcp``."""
        response = self._post_rpc(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {"protocolVersion": PREFERRED_PROTOCOL_VERSION},
            },
            api_key=self.mcp_key,
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertNotIn("error", body)
        self.assertEqual(body["result"]["protocolVersion"], PREFERRED_PROTOCOL_VERSION)

    def test_rpc_scoped_key_authenticates_on_mcp(self):
        """An ``rpc``-scope key (the wizard default) also authenticates on ``/mcp``."""
        response = self._post_rpc(
            {"jsonrpc": "2.0", "id": 3, "method": "ping"},
            api_key=self.rpc_key,
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("error", response.json())

    def test_null_scope_key_is_rejected_on_mcp(self):
        """Core matches ``scope = %s`` exactly, so a NULL-scope key is refused."""
        response = self._post_rpc(
            {"jsonrpc": "2.0", "id": 2, "method": "ping"},
            api_key=self.null_key,
        )
        self.assertEqual(response.status_code, 401)

    def test_mcp_key_is_not_a_general_rpc_key(self):
        """Blast-radius pin: the ``mcp`` key is rejected by ``scope='rpc'`` lookups.

        Core ``_check_credentials`` matches ``scope = %s`` exactly; a key
        stored with scope ``mcp`` therefore resolves under an ``mcp`` probe but NOT
        under the ``rpc`` probe used by core bearer/XML-RPC auth.
        """
        apikeys = self.env["res.users.apikeys"].sudo()
        # Sanity: the mcp probe DOES resolve the key (the pin below is meaningful).
        self.assertTrue(
            apikeys._check_credentials(scope="mcp", key=self.mcp_key),
            "the mcp-scoped key must resolve under an mcp-scope lookup",
        )
        # The actual pin: it is NOT a general RPC key.
        self.assertFalse(
            apikeys._check_credentials(scope="rpc", key=self.mcp_key),
            "an mcp-scoped key must NOT authenticate under scope='rpc'",
        )

    def test_mcp_key_rejected_on_legacy_rest_route(self):
        """Blast-radius pin: an ``mcp`` key does NOT authenticate on the legacy
        ``X-API-Key`` REST routes.

        ``/mcp/models`` is gated by ``require_api_key`` -> ``validate_api_key`` ->
        ``get_user_from_api_key`` with the default ``allowed_scopes=("rpc",)``,
        which rejects an ``mcp``-scope key; with no session either, the route
        returns 401. This closes a metadata-disclosure hole: an ``mcp`` key must
        not leak the enabled-model list here.
        """
        response = self._get_rest("/mcp/models", self.mcp_key)
        self.assertEqual(response.status_code, 401)
        self.assertFalse(response.json()["success"])

    def test_rpc_key_authenticates_on_legacy_rest_route(self):
        """Regression pin: an ``rpc`` key keeps authenticating on the same legacy
        REST route the ``mcp`` key is rejected on."""
        response = self._get_rest("/mcp/models", self.rpc_key)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["success"])

    def test_null_key_rejected_on_legacy_rest_route(self):
        """A NULL-scope key matches no scope probe, so the REST route refuses it."""
        response = self._get_rest("/mcp/models", self.null_key)
        self.assertEqual(response.status_code, 401)

    def test_helper_default_scope_rejects_mcp_key(self):
        """Unit pin on the shared helper: the default ``allowed_scopes=("rpc",)``
        does not resolve an ``mcp`` key, but widening to ``("mcp", "rpc")`` does.

        This is exactly the difference between the legacy callers (default) and
        the ``/mcp`` bearer door (widened).
        """
        mock_request = MagicMock()
        mock_request.env = self.env
        with patch("odoo.addons.mcp_server.controllers.auth.request", mock_request):
            self.assertFalse(
                auth.get_user_from_api_key(
                    self.mcp_key, allowed_scopes=("rpc",), log_failure=False
                ),
                "an mcp key must not resolve under the default rpc-only scope",
            )
            user = auth.get_user_from_api_key(
                self.mcp_key, allowed_scopes=("mcp", "rpc")
            )
            self.assertEqual(user.id, self.mcp_user.id)


@tagged("much_unit", "post_install", "-at_install")
class TestApiKeyScopeWizard(common.HttpCase):
    """The wizard ``make_key`` stores the scope chosen on the wizard.

    ``make_key`` is ``@check_identity``-gated and hard-requires an HTTP request, so
    there is no TransactionCase path. We push a minimal fake request onto the stack
    (mirroring core ``base/tests/test_res_users.py::test_revoke_all_devices``) and
    prime ``identity-check-last`` so the 10-minute gate passes and ``make_key`` runs
    directly -- no password round-trip through the identity wizard.
    """

    def setUp(self):
        super().setUp()
        unique_id = str(int(time.time() * 1000))[-6:]
        # Internal user: core ``check_access_make_key`` requires ``_is_internal()``.
        self.wizard_user = create_test_user(
            self.env,
            "MCP Key Wizard User",
            f"mcp_key_wizard_{unique_id}",
            email=f"mcp_key_wizard_{unique_id}@example.com",
            group_ids=[(6, 0, [self.env.ref("base.group_user").id])],
        )

    def _run_make_key(self, scope):
        """Drive the wizard ``make_key`` as ``wizard_user``; return the stored scope."""
        # Prime the identity gate and provide the ``request`` attributes core
        # ``make_key`` -> ``_generate`` reads (session gate, REMOTE_ADDR log line
        # and the ``url_root`` shown on the "Save your API Key" dialog).
        fake_req = SimpleNamespace(
            session={"identity-check-last": time.time()},
            env=self.env,
            httprequest=SimpleNamespace(
                environ={"REMOTE_ADDR": "127.0.0.1"},
                url_root="http://localhost/",
            ),
        )
        token = request_var.set(fake_req)
        self.addCleanup(request_var.reset, token)
        wizard = (
            self.env["res.users.apikeys.description"]
            .with_user(self.wizard_user)
            .create({"name": "Wizard Key", "scope": scope})
        )
        wizard.make_key()
        return (
            self.env["res.users.apikeys"]
            .sudo()
            .search([("user_id", "=", self.wizard_user.id)], order="id desc", limit=1)
            .scope
        )

    def test_wizard_mcp_scope_stores_mcp_scope(self):
        """``scope="mcp"`` -> the created key row has scope ``mcp``."""
        self.assertEqual(self._run_make_key("mcp"), "mcp")

    def test_wizard_rpc_scope_stores_rpc_scope(self):
        """``scope="rpc"`` -> the created key row has the ``rpc`` scope."""
        self.assertEqual(self._run_make_key("rpc"), "rpc")
