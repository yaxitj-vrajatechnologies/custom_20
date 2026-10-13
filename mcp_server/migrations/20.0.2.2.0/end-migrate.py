"""Give scope-less API keys the ``rpc`` scope.

Since 20.0 core matches an API key's scope exactly (``scope = %s``); a key stored
with a NULL scope (created before scopes were required) authenticates on no door
at all. Such keys were general-purpose keys, so they are backfilled with ``rpc``,
the scope the standard wizard now hands out, and keep working on ``/mcp`` and the
legacy REST/XML-RPC routes.
"""

import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return
    cr.execute("UPDATE res_users_apikeys SET scope = 'rpc' WHERE scope IS NULL")
    _logger.info("Set the 'rpc' scope on %s API key(s) that had no scope.", cr.rowcount)
