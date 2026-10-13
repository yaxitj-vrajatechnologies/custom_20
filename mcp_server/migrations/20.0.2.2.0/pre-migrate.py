"""Release the XML IDs of the access rules and record rules replaced by ir.access.

Since 20.0 the module ships its access rules in ``security/ir.access.csv`` and
reuses the XML IDs of its former ``ir.model.access`` records. Loading a record
whose XML ID still points to a record of another model fails ("found record of
different model"), so an XML ID the upgrade left on ``ir.model.access`` or
``ir.rule`` is removed here; the data load then creates the ``ir.access`` row
under it. XML IDs already moved to ``ir.access`` are kept and updated in place.

Up to 19.0 the module granted the MCP groups read access to
``res.users.apikeys``; 20.0 drops that grant. The upgrade converts the old
access rows to ``ir.access`` rows, and a converted row whose XML ID is released
above would stay without one, so the module update would not remove it. Those
grants are deleted here by model and group, which does not depend on how the
upgrade mapped the XML IDs.
"""

import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return
    cr.execute(
        """
        DELETE FROM ir_access a
         USING ir_model m, ir_model_data g
         WHERE a.model_id = m.id
           AND m.model = 'res.users.apikeys'
           AND a.group_id = g.res_id
           AND g.module = 'mcp_server'
           AND g.model = 'res.groups'
           AND g.name IN ('group_mcp_user', 'group_mcp_admin')
     RETURNING a.id
        """
    )
    access_ids = [row[0] for row in cr.fetchall()]
    if access_ids:
        cr.execute(
            "DELETE FROM ir_model_data WHERE model = 'ir.access' AND res_id = ANY(%s)",
            [access_ids],
        )
    _logger.info("Removed %s MCP group grant(s) on res.users.apikeys.", len(access_ids))

    cr.execute(
        """
        DELETE FROM ir_model_data
         WHERE module = 'mcp_server'
           AND model IN ('ir.model.access', 'ir.rule')
        """
    )
    _logger.info(
        "Released %s XML ID(s) of former access rules and record rules.", cr.rowcount
    )
