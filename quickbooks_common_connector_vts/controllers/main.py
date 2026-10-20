# -*- coding: utf-8 *-*
from odoo import http
from odoo.http import request
import base64
import requests
import logging
from werkzeug.utils import redirect

_logger = logging.getLogger(__name__)

class QuickbookAuthController(http.Controller):

    @http.route('/quickbook/auth/redirect', type='http', auth="public", csrf=False)
    def quickbook_auth_redirect(self, **kwargs):
        code = kwargs.get("code")
        realm_id = kwargs.get("realmId")
        quickbook_id = kwargs.get("state")

        quickbook_connect = request.env['quickbooks.connect'].sudo().browse(int(quickbook_id))
        if not quickbook_connect:
            return "Invalid Quickbook"

        token_url = quickbook_connect.auth_token_url
        client_cred = f"{quickbook_connect.client_id}:{quickbook_connect.client_secret}"
        auth_header = base64.b64encode(client_cred.encode()).decode()

        headers = {
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
            "Authorization": f"Basic {auth_header}"
        }
        payload = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": quickbook_connect.redirect_url
        }

        response = requests.post(token_url, headers=headers, data=payload)
        if response.status_code != 200:
            _logger.error("QuickBooks token exchange failed: %s", response.text)
            quickbook_connect.sudo().write({
                "state": "failed",
                "reason" : f"Connection Error: {response.text}"})
            return redirect(f"/web#id={quickbook_connect.id}&model=quickbooks.connect&view_type=form")

        tokens = response.json()
        
        quickbook_connect.write({
            "access_token": tokens.get("access_token"),
            "refresh_token": tokens.get("refresh_token"),
            "realm_id": realm_id,
            "state": "connected",
            "reason": "Successfully Connected with Quickbooks"
        })

        if tokens.get("access_token") and quickbook_connect.quickbook_base_url:
            qkb_company_obj = request.env['quickbooks.company.vts']
            company_url = quickbook_connect.quickbook_base_url + f"/{realm_id}/companyinfo/{realm_id}"
            company_info, cmp_status = request.env['quickbooks.api.vts'].qb_get_request(tokens["access_token"], company_url)

            if cmp_status == 200 and company_info:
                company_data = company_info.get('CompanyInfo', {})
                cmp_country_code = company_data.get('Country', '')
                qck_country_id = False
                if cmp_country_code:
                    qck_country_id = request.env['res.country'].search([('code','=', cmp_country_code)], limit=1)
                company_vals = {
                    'name': company_data.get('CompanyName', ''),
                    'quickbook_ID': realm_id,
                    'company_email': company_data.get('Email', ''),
                    'company_response': company_info,
                }

                qkb_company = qkb_company_obj.sudo().search([('quickbook_ID', '=', realm_id)], limit=1)

                if qkb_company:
                    qkb_company.write(company_vals)
                    quickbook_connect.qk_company_id = qkb_company.id
                    quickbook_connect.country_id = qck_country_id.id if qck_country_id else False
                else:
                    qk_company_id = qkb_company_obj.sudo().create(company_vals)
                    quickbook_connect.qk_company_id = qk_company_id.id
                    quickbook_connect.country_id = qck_country_id.id if qck_country_id else False
                    
        return redirect(f"/web#id={quickbook_connect.id}&model=quickbooks.connect&view_type=form")
