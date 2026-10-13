import logging
import xmlrpc.client as xmlrpclib  # nosec
from datetime import datetime
from typing import Any, Optional, Tuple

import defusedxml.xmlrpc

from odoo import SUPERUSER_ID, api, http, release
from odoo.exceptions import AccessDenied, AccessError, MissingError, UserError
from odoo.http import request
from odoo.modules import db as db_module
from odoo.service import common as common_service_root, model as model_service_root
from odoo.tools import config

from odoo.addons.rpc.controllers.xmlrpc import (
    RPC_FAULT_CODE_ACCESS_DENIED,
    RPC_FAULT_CODE_ACCESS_ERROR,
    RPC_FAULT_CODE_WARNING,
    dumps as odoo_dumps,
)

from . import auth, error_sanitizer, utils
from .rate_limiting import (
    check_rate_limit,
    is_rate_limiting_enabled,
    record_api_request,
    retry_after_seconds,
)

_logger = logging.getLogger(__name__)
defusedxml.xmlrpc.monkey_patch()

# XML-RPC fault codes aligned with HTTP status codes
XMLRPC_FAULT_CODES = {
    "bad_request": 400,
    "unauthorized": 401,
    "forbidden": 403,
    "not_found": 404,
    "rate_limit": 429,
    "internal_error": 500,
}


# Fault string for a verified credential whose user lacks the MCP access group;
# shared by the ``common`` login methods and the ``object`` proxy.
MCP_GROUP_DENIED_FAULT = (
    "MCP access denied: user is not a member of the MCP User group."
)


def _check_served_database(db_name: Any) -> None:
    """Refuse a call that names another database than the request is served from.

    Core verifies and runs a call in the database it names, while the MCP gates
    (group membership, enabled models, rate limit, audit) read the request's
    database; the two must be the same.
    """
    if db_name != request.db:
        raise xmlrpclib.Fault(
            XMLRPC_FAULT_CODES["bad_request"],
            "The call names a database this endpoint does not serve. Select the "
            "database through the host name or the X-Odoo-Database header.",
        )


# ``common`` service methods that return the uid of a verified credential.
_COMMON_LOGIN_METHODS = frozenset({"login", "authenticate"})


def _generate_xmlrpc_fault(code: int, message: str) -> str:
    """Build an XML-RPC fault string with standardized HTTP-aligned codes."""
    fault = xmlrpclib.Fault(code, message)
    return xmlrpclib.dumps(fault, methodresponse=1, allow_none=1)


def _fault_code_for(exc: Exception) -> int:
    """XML-RPC fault code for an error raised by a proxied call.

    Odoo user errors (``UserError`` and its subclasses) are expected outcomes of
    a call and keep the codes core's ``/xmlrpc/2`` sends, so XML-RPC clients can
    tell a business error from a transport failure: 3 for a refused login, 4 for
    an access error, 2 for any other user error. Anything else is an internal
    fault.
    """
    if isinstance(exc, AccessDenied):
        return RPC_FAULT_CODE_ACCESS_DENIED
    if isinstance(exc, AccessError):
        return RPC_FAULT_CODE_ACCESS_ERROR
    if isinstance(exc, UserError):
        return RPC_FAULT_CODE_WARNING
    return XMLRPC_FAULT_CODES["internal_error"]


def _audit_code_for(exc: Exception) -> int:
    """HTTP-style status recorded in the audit log for an error of a proxied call."""
    if isinstance(exc, AccessDenied):
        return XMLRPC_FAULT_CODES["unauthorized"]
    if isinstance(exc, AccessError):
        return XMLRPC_FAULT_CODES["forbidden"]
    if isinstance(exc, MissingError):
        return XMLRPC_FAULT_CODES["not_found"]
    if isinstance(exc, UserError):
        return XMLRPC_FAULT_CODES["bad_request"]
    return XMLRPC_FAULT_CODES["internal_error"]


def _fault_for_exception(controller_name: str, exc: Exception) -> Tuple[int, str]:
    """Fault code and client-safe message for an error raised by a proxied call.

    A user error returns its sanitized message and logs one line; an internal
    fault is logged with its traceback by the sanitizer and the client gets the
    generic message, never the raw exception text.
    """
    code = _fault_code_for(exc)
    if code != XMLRPC_FAULT_CODES["internal_error"]:
        _logger.info(
            "%s: %s: %s", controller_name, type(exc).__name__, utils._one_line(str(exc))
        )
    return code, error_sanitizer.sanitize_exception(
        exc, f"Unhandled error in {controller_name}"
    )


def _get_client_ip() -> Optional[str]:
    """Get client IP address from request."""
    if request and hasattr(request, "httprequest"):
        return request.httprequest.remote_addr
    return None


def _dispatch_db_service(method: str, params) -> Any:
    """Serve the public methods of the former ``db`` RPC service.

    Core no longer ships that service, so the proxy answers the read-only methods
    the standalone client uses (``list``, ``server_version``, ``db_exist``) from
    their replacements; the master-password methods are not offered.
    ``list`` honours ``list_db`` like core's own database list.
    """
    if method == "list":
        return db_module.list_dbs()
    if method == "server_version":
        return release.version
    if method == "db_exist":
        return db_module.exist(*params)
    raise xmlrpclib.Fault(
        XMLRPC_FAULT_CODES["not_found"], f"Method not found: {method}"
    )


def _dispatch_common_service(method: str, params) -> Any:
    """Serve the ``common`` RPC service, gating its login methods on MCP access.

    ``login`` / ``authenticate`` return the uid of a credential core has just
    verified, or ``False`` for a wrong one. The MCP access-group gate runs only
    on that verified uid, like the object proxy's password path: a wrong
    credential gets core's ``False`` whatever the user's membership, so there is
    no membership oracle. ``version`` stays open.
    """
    if method in _COMMON_LOGIN_METHODS and params:
        _check_served_database(params[0])
    result = common_service_root.dispatch(method, params)
    if method in _COMMON_LOGIN_METHODS and result:
        user = request.env["res.users"].sudo().browse(result)
        if not auth.user_has_mcp_access(user):
            auth.log_mcp_group_denied(user, api_key_used=False)
            raise xmlrpclib.Fault(
                XMLRPC_FAULT_CODES["forbidden"], MCP_GROUP_DENIED_FAULT
            )
    return result


def _dispatch_service_xmlrpc(controller_name: str, service_dispatch) -> Any:
    """Guard + parse + dispatch + marshal + fault scaffold for the stateless
    ``common`` / ``db`` XML-RPC proxies.

    The ``object`` proxy differs (custom access-controlled dispatch and Odoo's
    date-aware marshaller) and keeps its own handler below.
    """
    if not utils.is_mcp_enabled():
        fault_response = _generate_xmlrpc_fault(
            XMLRPC_FAULT_CODES["forbidden"],
            "MCP Server is disabled globally.",
        )
        return request.make_response(fault_response, [("Content-Type", "text/xml")])

    data = request.httprequest.data
    try:
        params, method = xmlrpclib.loads(data)
        result = service_dispatch(method, params)
        response_data = xmlrpclib.dumps((result,), methodresponse=1, allow_none=1)
        return request.make_response(response_data, [("Content-Type", "text/xml")])
    except xmlrpclib.Fault as e:
        _logger.warning(
            f"{controller_name} XML-RPC Fault: "
            f"Code {e.faultCode}, String: {e.faultString}"
        )
        return request.make_response(
            xmlrpclib.dumps(e, methodresponse=1, allow_none=1),
            [("Content-Type", "text/xml")],
        )
    except Exception as e:
        fault_response = _generate_xmlrpc_fault(
            *_fault_for_exception(controller_name, e)
        )
        return request.make_response(fault_response, [("Content-Type", "text/xml")])


class MCPCommonController(http.Controller):
    # auth="none"/csrf=False: stateless XML-RPC proxy. Credentials travel in the
    # call params (db, uid, api-key), not an Odoo session cookie, so there is no
    # CSRF surface (mirrors stock /xmlrpc/2/common); MCP is gated inside dispatch.
    @http.route(
        "/mcp/xmlrpc/common", type="http", auth="none", methods=["POST"], csrf=False
    )
    def index(self, **kwargs):
        return _dispatch_service_xmlrpc("MCPCommonController", _dispatch_common_service)


class MCPDatabaseController(http.Controller):
    # auth="none"/csrf=False: stateless XML-RPC proxy, same rationale as
    # /mcp/xmlrpc/common -- no session cookie, so no CSRF surface (mirrors stock
    # /xmlrpc/2/db); the global MCP kill-switch is checked inside dispatch.
    @http.route(
        "/mcp/xmlrpc/db", type="http", auth="none", methods=["POST"], csrf=False
    )
    def index(self, **kwargs):
        return _dispatch_service_xmlrpc("MCPDatabaseController", _dispatch_db_service)


class MCPObjectController(http.Controller):
    def _validate_request(self, xmlrpc_method: str, params: list) -> None:
        """Validate the XML-RPC method and params; raise Fault if invalid."""
        if xmlrpc_method != "execute_kw":
            _logger.warning(
                f"MCPObjectController received non-execute_kw method: {xmlrpc_method}"
            )
            if request and hasattr(request, "env"):
                request.env["mcp.log"].sudo().log_error(
                    error_message=f"MCPObjectController: "
                    f"Unsupported method {xmlrpc_method}. "
                    f"Only execute_kw is allowed.",
                    error_code="E400",
                    endpoint="/mcp/xmlrpc/object",
                    operation=xmlrpc_method,
                    ip_address=_get_client_ip(),
                )
            raise xmlrpclib.Fault(
                XMLRPC_FAULT_CODES["bad_request"],
                f"MCPObjectController: Unsupported method "
                f"{xmlrpc_method}. Only execute_kw is allowed.",
            )

        if len(params) < 5:
            raise xmlrpclib.Fault(
                XMLRPC_FAULT_CODES["bad_request"],
                "MCPObjectController: Insufficient parameters for execute_kw.",
            )

    def _identify_user(
        self, auth_token: Any, uid: Any
    ) -> Tuple[Optional[Any], Optional[int]]:
        """Identify the user from API key or uid, for rate limiting."""
        user_obj = None
        user_id = None

        # First try to get user from API key if it looks like one
        if isinstance(auth_token, str) and len(auth_token) > 20:
            user_obj = auth.get_user_from_api_key(auth_token)
            if user_obj:
                user_id = user_obj.id
                _logger.debug(
                    f"MCP XML-RPC: Identified user {user_id} "
                    f"from API key for rate limiting."
                )

        if not user_id and uid:
            user_id = uid

        return user_obj, user_id

    def _apply_rate_limiting(
        self,
        user_obj: Optional[Any],
        user_id: Optional[int],
        model_name: str,
        model_method: str,
    ) -> None:
        """Apply rate limiting if enabled; raise Fault if the limit is exceeded."""
        if not is_rate_limiting_enabled():
            return

        # Namespace the rate-limit bucket by database (cross-tenant collision).
        dbname = request.env.cr.dbname

        if user_id:
            if not check_rate_limit(user_id, dbname):
                _logger.warning(
                    f"MCP XML-RPC: Rate limit exceeded for user ID "
                    f"{user_id} on {model_name}.{model_method}."
                )
                env_for_log = request.env(user=user_obj.id) if user_obj else request.env
                env_for_log["mcp.log"].sudo().log_rate_limit_exceeded(
                    user_id=user_id,
                    endpoint="/mcp/xmlrpc/object",
                    ip_address=_get_client_ip(),
                )
                raise xmlrpclib.Fault(
                    XMLRPC_FAULT_CODES["rate_limit"],
                    "Too many requests. Rate limit exceeded.",
                )
            record_api_request(user_id, dbname)
        else:
            anonymous_id = -1
            if not check_rate_limit(anonymous_id, dbname):
                raise xmlrpclib.Fault(
                    XMLRPC_FAULT_CODES["rate_limit"],
                    "Too many requests. Rate limit exceeded.",
                )
            record_api_request(anonymous_id, dbname)

    def _get_env_for_user(self, user_obj: Optional[Any], uid: Any) -> Any:
        """Return the Odoo environment for the resolved user context."""
        if user_obj:
            return request.env(user=user_obj.id)

        if uid:
            try:
                return request.env(user=uid)
            except Exception as e:
                # Log the failure but continue with default environment
                _logger.debug(f"Failed to create environment for uid {uid}: {e}")

        return request.env

    def _extract_record_ids(self, params: list) -> Optional[list]:
        """Extract record IDs from params[5] if present, else None."""
        if len(params) > 5 and isinstance(params[5], list):
            # For methods like read, write that have record IDs in params[5]
            if params[5] and isinstance(params[5][0], int):
                return params[5]
        return None

    @staticmethod
    def _verify_uid_passwd(uid: int, auth_token: Any) -> None:
        """Verify a (uid, password) credential the way core does, or raise.

        Runs on an INDEPENDENT read/write cursor, not the request cursor: this
        ``auth="none"`` route defaults to ``readonly`` (``odoo/http.py``), which
        is a real replica cursor wherever ``db_replica_host`` is set, and
        ``_check_uid_passwd`` writes -- ``_check_credentials`` rehashes a
        deprecated hash through ``_set_encrypted_password``'s UPDATE. On the
        request cursor that UPDATE raises ``ReadOnlySqlTransaction``, and the
        controller's blanket ``except`` swallows the retry core's own
        ``http.py`` handler would perform, so the rehash could never commit and
        the member would be wedged at 500 forever. ``model_service_root.dispatch``
        has the same requirement and meets it the same way.

        Under ``test_enable`` the request cursor is used instead: opening a
        read/write cursor from HttpCase's readonly test cursor is refused
        outright. Mirrors ``controllers/audit.py``'s test/prod cursor
        discipline.

        Failures propagate untouched -- the caller must not turn a rejected
        credential into anything the caller can distinguish.
        """
        if config["test_enable"]:
            # sudo: no user is authenticated yet on this auth="none" route.
            request.env["res.users"].sudo()._check_uid_passwd(uid, auth_token)
            return
        with request.env.registry.cursor() as cr:
            api.Environment(cr, SUPERUSER_ID, {})["res.users"]._check_uid_passwd(
                uid, auth_token
            )

    def _gate_password_credential(self, uid: Any, auth_token: Any) -> None:
        """Apply the MCP access-group gate to a (uid, password) credential.

        The uid a client puts in ``execute_kw`` is unverified, so the gate
        cannot read it directly -- a 403-vs-fault split would turn this
        ``auth="none"`` route into a membership oracle over the uid space. So
        verify the credential FIRST, exactly as core will, and gate only the
        identity that survives: the 403 is then reachable only by a caller who
        already proved the password, which tells them nothing they did not
        already know.

        ``uid`` is normalised with ``int()`` because that is precisely what
        ``model_service_root.dispatch`` does before authenticating it -- gating
        only a Python ``int`` would let ``<string>42</string>`` walk past the
        gate and still authenticate downstream. A uid ``int()`` rejects is left
        to core, which raises on the same conversion.

        ``_check_uid_passwd`` is ``@ormcache('uid', 'passwd')``, so core's own
        call inside dispatch hits the cache -- the second verification costs no
        password hashing.

        A failed verification is re-raised as a bare ``AccessDenied``, so it
        faults identically for every uid: no membership signal, and no existence
        signal either -- core raises ``MissingError`` for a nonexistent uid
        (``_assert_can_auth``'s ``except AccessDenied`` only counts login
        failures; the ``env.user`` read inside it is not caught), which would
        otherwise fault with a different code and message.
        """
        try:
            uid = int(uid)
        except (TypeError, ValueError):
            return
        if not auth_token:
            # Core raises AccessDenied for an empty password before it opens a
            # cursor; nothing can authenticate, so there is nothing to gate.
            return

        try:
            self._verify_uid_passwd(uid, auth_token)
        except Exception:
            # The rejection must leave an mcp.log trace:
            # every other door records its denials, and without this row a
            # failed uid/password on this route commits with no audit entry at
            # all. No user_id -- the uid is client-supplied and unverified, so
            # attributing the row would let a caller seed the audit log with
            # arbitrary identities. Throttled per IP like every auth failure.
            auth._log_auth_failure(
                "Invalid uid/password credential", api_key_used=False
            )
            raise AccessDenied() from None

        user = request.env["res.users"].sudo().browse(uid)
        if not auth.user_has_mcp_access(user):
            auth.log_mcp_group_denied(user, api_key_used=False)
            raise xmlrpclib.Fault(
                XMLRPC_FAULT_CODES["forbidden"], MCP_GROUP_DENIED_FAULT
            )

    def _mcp_object_dispatch(self, xmlrpc_method: str, params: list):
        """Dispatch an XML-RPC object call through the MCP access-control gate."""
        self._validate_request(xmlrpc_method, params)

        # Standard params for execute_kw: (db_name, uid, password, model_name,
        # model_method, args_array, kwargs_dict)
        uid = params[1]
        auth_token = params[2]
        # Collapse CR/LF in the client-supplied method name before it reaches
        # any log sink or the mcp.log audit table: on this auth="none" route a
        # newline-bearing name would otherwise forge log/audit lines (CWE-117).
        # A legitimate method name has no CR/LF, so this is a no-op for real
        # calls; a forged one is denied at check_mcp_access before dispatch runs.
        model_method = utils._one_line(params[4])

        try:
            model_name = utils.sanitize_model_name(params[3])
        except ValueError as e:
            raise xmlrpclib.Fault(
                XMLRPC_FAULT_CODES["bad_request"], f"Invalid model name: {e}"
            ) from e

        _check_served_database(params[0])
        user_obj, user_id = self._identify_user(auth_token, uid)

        self._apply_rate_limiting(user_obj, user_id, model_name, model_method)

        # Per-user MCP access gate. Two credential kinds reach this proxy and
        # both are gated -- but only ever on a VERIFIED identity, never on the
        # raw client-supplied uid: acting on that unverified value would answer
        # "is uid N an MCP member?" for an unauthenticated caller sweeping the
        # uid space. See ``_gate_password_credential`` for how the password
        # path earns a verified identity before the gate runs.
        if user_obj is not None:
            # An rpc-scope API key, already resolved by _identify_user.
            if not auth.user_has_mcp_access(user_obj):
                auth.log_mcp_group_denied(user_obj, api_key_used=True)
                raise xmlrpclib.Fault(
                    XMLRPC_FAULT_CODES["forbidden"], MCP_GROUP_DENIED_FAULT
                )
        else:
            self._gate_password_credential(uid, auth_token)

        env_for_check = self._get_env_for_user(user_obj, uid)

        start_time = datetime.now()
        ip_address = _get_client_ip()

        if not utils.check_mcp_access(env_for_check, model_name, model_method):
            env_for_check["mcp.log"].sudo().log_permission_denied(
                model_name=model_name,
                operation=model_method,
                user_id=user_id,
                endpoint="/mcp/xmlrpc/object",
                ip_address=ip_address,
                error_message=f"Access denied by MCP for model "
                f"'{model_name}' method '{model_method}'.",
            )
            raise xmlrpclib.Fault(
                XMLRPC_FAULT_CODES["forbidden"],
                f"Access denied by MCP for model "
                f"'{model_name}' method '{model_method}'.",
            )

        _logger.info(
            f"MCP XML-RPC: Access GRANTED for {model_name}.{model_method} "
            f"(User ID: {user_id if user_id else 'N/A'})"
        )

        try:
            result = model_service_root.dispatch(xmlrpc_method, params)

            duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)
            env_for_check["mcp.log"].sudo().log_model_access(
                model_name=model_name,
                operation=model_method,
                user_id=user_id,
                record_ids=self._extract_record_ids(params),
                endpoint="/mcp/xmlrpc/object",
                http_method="POST",
                duration_ms=duration_ms,
                ip_address=ip_address,
            )

            return result
        except Exception as e:
            duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)
            env_for_check["mcp.log"].sudo().log_error(
                error_message=str(e),
                error_code=f"E{_audit_code_for(e)}",
                endpoint="/mcp/xmlrpc/object",
                model_name=model_name,
                operation=model_method,
                user_id=user_id,
                ip_address=ip_address,
            )
            raise

    # auth="none"/csrf=False: stateless XML-RPC proxy -- credentials ride in the
    # call params, not a session cookie, so no CSRF surface (mirrors stock
    # /xmlrpc/2/object). Every call is access-controlled by check_mcp_access
    # (per-model/operation MCP gate) inside _mcp_object_dispatch.
    @http.route(
        "/mcp/xmlrpc/object", type="http", auth="none", methods=["POST"], csrf=False
    )
    def index(self, **kwargs):
        if not utils.is_mcp_enabled():
            fault_response = _generate_xmlrpc_fault(
                XMLRPC_FAULT_CODES["forbidden"],
                "MCP Server is disabled globally.",
            )
            return request.make_response(fault_response, [("Content-Type", "text/xml")])

        data = request.httprequest.data
        try:
            params, method = xmlrpclib.loads(data)
            result = self._mcp_object_dispatch(method, params)
            # Use Odoo's custom XML-RPC marshaller that handles date objects
            response_data = odoo_dumps((result,))
            return request.make_response(response_data, [("Content-Type", "text/xml")])
        except xmlrpclib.Fault as e:
            _logger.warning(
                f"MCPObjectController XML-RPC Fault: "
                f"Code {e.faultCode}, String: {e.faultString}"
            )
            headers = [("Content-Type", "text/xml")]
            if e.faultCode == XMLRPC_FAULT_CODES["rate_limit"]:
                # XML-RPC faults travel on HTTP 200; the back-off hint rides
                # along as a header, same value as the /mcp and REST 429s.
                headers.append(("Retry-After", str(retry_after_seconds())))
            return request.make_response(
                xmlrpclib.dumps(e, methodresponse=1, allow_none=1), headers
            )
        except Exception as e:
            fault_response = _generate_xmlrpc_fault(
                *_fault_for_exception("MCPObjectController", e)
            )
            return request.make_response(fault_response, [("Content-Type", "text/xml")])
