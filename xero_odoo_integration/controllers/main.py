# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import request
import logging
import base64
import requests
from werkzeug.utils import redirect

_logger = logging.getLogger(__name__)

class XeroAuthController(http.Controller):

    @http.route('/xero/auth/callback', type='http', auth='public', csrf=False)
    def xero_auth_callback(self, **kwargs):
        """
        Xero callback endpoint after OAuth2 authorization.
        Expects: code and state (state == xero.connect.id we passed earlier)
        """
        code = kwargs.get("code")
        state = kwargs.get("state")
        if not code or not state:
            return "Invalid Xero callback"
        xero_connect = request.env['xero.connect'].sudo().browse(int(state))
        try:
            if not xero_connect.exists():
                raise ValueError(f"Xero connection ID {state} not found")

            token_url = xero_connect.auth_token_url
            client_cred = f"{xero_connect.client_id}:{xero_connect.client_secret}"
            auth_header = base64.b64encode(client_cred.encode()).decode()

            headers = {
                "Accept": "application/json",
                "Content-Type": "application/x-www-form-urlencoded",
                "Authorization": f"Basic {auth_header}"
            }
            payload = {
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": xero_connect.redirect_url
            }

            response = requests.post(token_url, headers=headers, data=payload, timeout=30)
            if response.status_code != 200:
                raise ValueError(f"Token exchange failed: {response.text}")

            tokens = response.json()
            access_token = tokens.get("access_token")
            refresh_token = tokens.get("refresh_token")
            if not access_token or not refresh_token:
                raise ValueError(f"Token response invalid: {tokens}")

            xero_connect.sudo().write({
                "access_token": access_token,
                "refresh_token": refresh_token,
            })

            tenant_headers = {"Authorization": f"Bearer {access_token}", "Accept": "application/json"}
            tenant_resp = requests.get("https://api.xero.com/connections", headers=tenant_headers, timeout=30)
            if tenant_resp.status_code != 200:
                raise ValueError(f"Tenant fetch failed: {tenant_resp.text}")

            tenants = tenant_resp.json()
            tenant_id = tenants[0].get("tenantId") if tenants else None
            if not tenant_id:
                raise ValueError(f"No tenantId returned from Xero: {tenants}")

            xero_connect.sudo().write({
                "tenant_id": tenant_id,
                "state": "connected",
                "reason": "Successfully connected with Xero"
            })

            if xero_connect.xero_base_url:
                org_headers = {
                    "Authorization": f"Bearer {access_token}",
                    "Xero-tenant-id": tenant_id,
                    "Accept": "application/json"
                }
                org_url = xero_connect.xero_base_url.rstrip('/') + "/Organisation"
                org_info = requests.get(org_url, headers=org_headers, timeout=30)
                xero_company_obj = request.env['xero.company.vts']

                if org_info.status_code == 200:
                    org_json = org_info.json()
                    org_data = org_json.get("Organisations", [{}])[0]
                    cmp_country_code = org_data.get("CountryCode")
                    xero_country_id = False
                    if cmp_country_code:
                        xero_country_id = request.env['res.country'].search([('code', '=', cmp_country_code)], limit=1)
                    company_vals = {
                        "name": org_data.get('Name'),
                        "tenant_id": tenant_id,
                        "xero_response": org_json,
                    }
                    xero_company = xero_company_obj.sudo().search([('tenant_id','=',tenant_id),])
                    if xero_company:
                        xero_company.write(company_vals)
                        xero_connect.xero_company_id = xero_company.id
                        xero_connect.country_id = xero_country_id.id if xero_country_id else False
                    else:
                        xero_company_id = xero_company_obj.create(company_vals)
                        xero_connect.xero_company_id = xero_company_id.id
                        xero_connect.country_id = xero_country_id.id if xero_country_id else False

        except Exception as e:
            _logger.exception("Xero auth callback failed: %s", e)
            xero_connect.sudo().write({
                "state": "failed",
                "reason": str(e)
            })
            return redirect(f"/odoo/xero.connect/{xero_connect.id}")

        return redirect(f"/odoo/xero.connect/{xero_connect.id}")
