"""Tests for the 20.0.2.2.0 end-migration (scope-less API keys get ``rpc``)."""

import importlib.util
import os
from datetime import datetime, timedelta

from odoo.tests import common, tagged

_MIGRATION_PATH = os.path.join(
    os.path.dirname(__file__),
    "..",
    "migrations",
    "20.0.2.2.0",
    "end-migrate.py",
)


def _load_migration():
    """Load the end-migrate module by path (migrations/ is not a package)."""
    spec = importlib.util.spec_from_file_location(
        "mcp_server_end_migrate_20_0_2_2_0", _MIGRATION_PATH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@tagged("much_unit", "post_install", "-at_install")
class TestMigrationApiKeyScope(common.TransactionCase):
    """migrate() backfills NULL-scope API keys with ``rpc`` on upgrades only."""

    def _keys(self):
        apikeys = self.env["res.users.apikeys"]
        expiration = datetime.now() + timedelta(hours=12)
        null_key = apikeys._generate(None, "Null Key", expiration)
        mcp_key = apikeys._generate("mcp", "MCP Key", expiration)
        self.env.flush_all()
        return null_key, mcp_key

    def _scope_of(self, name):
        self.env["res.users.apikeys"].invalidate_model()
        return self.env["res.users.apikeys"].sudo().search([("name", "=", name)]).scope

    def test_null_scope_becomes_rpc_and_others_are_kept(self):
        self._keys()
        _load_migration().migrate(self.env.cr, "20.0.2.1.0")
        self.assertEqual(self._scope_of("Null Key"), "rpc")
        self.assertEqual(self._scope_of("MCP Key"), "mcp")

    def test_fresh_install_is_a_no_op(self):
        self._keys()
        _load_migration().migrate(self.env.cr, None)
        self.assertFalse(self._scope_of("Null Key"))
