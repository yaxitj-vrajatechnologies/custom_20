"""Tests for the 20.0.2.2.0 pre-migration (XML IDs of replaced access rules)."""

import importlib.util
import os

from odoo.tests import common, tagged

_MIGRATION_PATH = os.path.join(
    os.path.dirname(__file__),
    "..",
    "migrations",
    "20.0.2.2.0",
    "pre-migrate.py",
)


def _load_migration():
    """Load the pre-migrate module by path (migrations/ is not a package)."""
    spec = importlib.util.spec_from_file_location(
        "mcp_server_pre_migrate_20_0_2_2_0", _MIGRATION_PATH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@tagged("much_unit", "post_install", "-at_install")
class TestMigrationAccessXmlids(common.TransactionCase):
    """migrate() drops XML IDs still pointing to the replaced access models."""

    def setUp(self):
        super().setUp()
        self.env.cr.execute(
            """
            INSERT INTO ir_model_data (module, name, model, res_id, noupdate)
            VALUES ('mcp_server', 'test_old_acl', 'ir.model.access', 999999, false),
                   ('mcp_server', 'test_old_rule', 'ir.rule', 999998, false)
            """
        )

    def _names(self):
        self.env.cr.execute(
            "SELECT name FROM ir_model_data WHERE module = 'mcp_server'"
        )
        return {row[0] for row in self.env.cr.fetchall()}

    def test_old_xmlids_released_current_ones_kept(self):
        _load_migration().migrate(self.env.cr, "19.0.2.2.0")
        names = self._names()
        self.assertNotIn("test_old_acl", names)
        self.assertNotIn("test_old_rule", names)
        self.assertIn("access_mcp_log_admin", names)

    def test_apikey_grants_removed_other_grants_kept(self):
        """A converted MCP group grant on res.users.apikeys is deleted."""
        Access = self.env["ir.access"].sudo()
        apikey_model = self.env["ir.model"]._get("res.users.apikeys")
        orphan = Access.create(
            {
                "name": "res.users.apikeys mcp user",
                "model_id": apikey_model.id,
                "group_id": self.env.ref("mcp_server.group_mcp_user").id,
                "operation": "r",
            }
        )
        with_xmlid = Access.create(
            {
                "name": "res.users.apikeys mcp admin",
                "model_id": apikey_model.id,
                "group_id": self.env.ref("mcp_server.group_mcp_admin").id,
                "operation": "r",
            }
        )
        self.env["ir.model.data"].create(
            {
                "module": "mcp_server",
                "name": "access_res_users_apikeys_mcp_admin",
                "model": "ir.access",
                "res_id": with_xmlid.id,
            }
        )
        kept = self.env.ref("mcp_server.access_mcp_log_admin")
        self.env.flush_all()

        _load_migration().migrate(self.env.cr, "19.0.2.2.0")
        self.env.invalidate_all()

        self.assertFalse(orphan.exists())
        self.assertFalse(with_xmlid.exists())
        self.assertNotIn("access_res_users_apikeys_mcp_admin", self._names())
        self.assertTrue(kept.exists())

    def test_fresh_install_is_a_no_op(self):
        _load_migration().migrate(self.env.cr, None)
        self.assertIn("test_old_acl", self._names())
