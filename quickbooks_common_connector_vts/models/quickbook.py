# -*- coding: utf-8 *-*
from odoo import models, fields, api, _
import requests
import base64
from odoo.exceptions import UserError
import urllib.parse


class QuickbooksConnect(models.Model):
    _name = 'quickbooks.connect'
    _description = "Quickbooks Connect"

    name = fields.Char(string="Name")
    client_id = fields.Char(string="Client ID", copy=False)
    client_secret = fields.Char(string="Client Secret", copy=False)
    redirect_url = fields.Char(string="Redirect URL", copy=False)
    environment = fields.Selection([('sandbox', 'Sandbox'), ('production', 'Production')], default="sandbox",
                                   string="Environment")
    qk_company_id = fields.Many2one('quickbooks.company.vts', string="Quickbooks Company")
    access_token = fields.Char(string="Access token")
    refresh_token = fields.Char(string="Refresh token")
    realm_id = fields.Char(string="Realm ID")
    state = fields.Selection([('connecting', 'Connecting'), ('connected', 'Connected'), ('failed', 'Failed')],
                             string="State", default="connecting")
    reason = fields.Text(string="Reason")
    quickbook_base_url = fields.Char(string="URL")
    company_id = fields.Many2one('res.company', string="Company", default=lambda self: self.env.user.company_id)
    country_id = fields.Many2one('res.country', string="Country", copy=False)
    customer_creation = fields.Boolean(string="Customer Creation",
                                       help="Enable this option to create a customer if does not exist when importing.")
    account_creation = fields.Boolean(string="Chart Of Account Creation",
                                      help="Enable this option to create a chart of account if does not exist when importing.")
    payment_term_creation = fields.Boolean(string="Payment Terms Creation",
                                           help="Enable this option to create a payment terms if does not exist when importing.")
    taxes_creation = fields.Boolean(string="Taxes Creation",
                                    help="Enable this option to create a taxes if does not exist when importing.")
    qck_customer_count = fields.Integer(string="Customer Counts", compute='_compute_customer_count')
    qck_payment_term_count = fields.Integer(string="Payment Terms Counts", compute='_compute_payment_term_count')
    qck_account_count = fields.Integer(string="Account Counts", compute='_compute_account_count')
    qck_taxes_count = fields.Integer(string="Taxes Count", compute='_compute_taxes_count')
    qbk_scope_ids = fields.Many2many('quickbooks.scope', 'rel_quick_connect_scope', string="Features",
                                     default=lambda self: self.env.ref(
                                         'quickbooks_common_connector_vts.quickbooks_scope_accounting'))
    auto_send_fail_transaction = fields.Boolean(string="Auto Send Failed Transaction Report", copy=False)
    email_send_transaction = fields.Char(string="Email For Send Transaction", copy=False)
    auth_token_url = fields.Char(string="Auth Token URL",
                                 default="https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer", copy=False)
    qkca_is_company_canada = fields.Boolean(string="Is Canada Company", compute='_compute_is_company_canada',
                                            default=False, store=True, copy=False)

    @api.depends('company_id.country_id.code')
    def _compute_is_company_canada(self):
        for rec in self:
            rec.qkca_is_company_canada = rec.company_id.country_id.code == 'CA' if rec.company_id and rec.company_id.country_id else False

    def action_quickbook_open_instance_view_form(self):
        form_id = self.sudo().env.ref('quickbooks_common_connector_vts.quickbooks_connect_form_view')
        action = {
            'name': _('Quickbooks Instance'),
            'view_id': False,
            'res_model': 'quickbooks.connect',
            'context': self._context,
            'view_mode': 'form',
            'res_id': self.id,
            'views': [(form_id.id, 'form')],
            'type': 'ir.actions.act_window',
        }
        return action

    @api.onchange('environment')
    def change_quick_environment(self):
        if self.environment == 'production':
            self.quickbook_base_url = "https://quickbooks.api.intuit.com/v3/company"
        elif self.environment == 'sandbox':
            self.quickbook_base_url = "https://sandbox-quickbooks.api.intuit.com/v3/company"

    def action_connect_quickbooks(self):
        scope_values = " ".join(self.qbk_scope_ids.mapped('value'))
        encoded_scopes = urllib.parse.quote(scope_values)
        auth_url = (
            f"https://appcenter.intuit.com/connect/oauth2"
            f"?client_id={self.client_id}"
            f"&response_type=code"
            f"&scope={encoded_scopes}"
            f"&redirect_uri={self.redirect_url}"
            f"&state={self.id}"
        )
        return {
            "type": "ir.actions.act_url",
            "url": auth_url,
            "target": "self",
        }

    def reconnect_quickbook(self):
        self.state = 'connecting'
        self.access_token = ''

    def refresh_access_token(self):
        quick_connects = self if self else self.env['quickbooks.connect'].sudo().search([])
        for rec in quick_connects:
            token_url = rec.auth_token_url
            client_creds = f"{rec.client_id}:{rec.client_secret}"
            auth_header = base64.b64encode(client_creds.encode()).decode()

            headers = {
                "Accept": "application/json",
                "Content-Type": "application/x-www-form-urlencoded",
                "Authorization": f"Basic {auth_header}"
            }
            payload = {
                "grant_type": "refresh_token",
                "refresh_token": rec.refresh_token
            }

            try:
                response = requests.post(token_url, headers=headers, data=payload, timeout=30)
                if response.status_code == 200:
                    tokens = response.json()
                    rec.write({
                        "access_token": tokens.get("access_token"),
                        "refresh_token": tokens.get("refresh_token"),
                    })
                else:
                    rec.write({"reason": response.text})
            except requests.exceptions.RequestException as e:
                rec.write({"reason": str(e)})

    def _compute_customer_count(self):
        for rec in self:
            rec.qck_customer_count = self.env['res.partner'].search_count(
                [('qbk_id', '!=', False), ('qck_instance_id', '=', rec.id)])

    def _compute_account_count(self):
        for rec in self:
            rec.qck_account_count = self.env['account.account'].search_count([('qck_instance_id', '=', rec.id)])

    def _compute_payment_term_count(self):
        for rec in self:
            rec.qck_payment_term_count = self.env['account.payment.term'].search_count(
                [('qck_instance_id', '=', rec.id)])

    def _compute_taxes_count(self):
        for rec in self:
            rec.qck_taxes_count = self.env['account.tax'].search_count([('qck_instance_id', '=', rec.id)])

    def action_qck_customer(self):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id("account.res_partner_action_customer")
        action['context'] = {}
        action['domain'] = [('qbk_id', '!=', False), ('qck_instance_id', '=', self.id)]
        return action

    def action_qck_account(self):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id("account.action_account_form")
        action['context'] = {}
        action['domain'] = [('qck_instance_id', '=', self.id)]
        return action

    def action_qck_taxes(self):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id("account.action_tax_form")
        action['context'] = {}
        action['domain'] = [('qck_instance_id', '=', self.id)]
        return action

    def action_qck_payment_terms(self):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id("account.action_payment_term_form")
        action['domain'] = [('qck_instance_id', '=', self.id)]
        return action

    def unlink(self):
        for rec in self:
            self.env['qbo.partner.map.vts'].sudo().search([('quickbook_instance_id', '=', rec.id)]).unlink()
            self.env['qbo.payment.terms.vts'].sudo().search([('quickbook_instance_id', '=', rec.id)]).unlink()
            self.env['qbo.account.vts'].sudo().search([('quickbook_instance_id', '=', rec.id)]).unlink()
            self.env['qbo.taxes.vts'].sudo().search([('quickbook_instance_id', '=', rec.id)]).unlink()
        return super(QuickbooksConnect, self).unlink()

    def action_import_operation(self):
        operation = self.env['quickbooks.operations'].create({'quickbook_instance_id': self.id})
        return {
            'type': 'ir.actions.act_window',
            'name': 'Quickbook Import Operation',
            'res_model': 'quickbooks.operations',
            'view_mode': 'form',
            'target': 'new',
            'res_id': operation.id,
        }

    def action_logs_view(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Quickbook Logs',
            'res_model': 'quickbooks.log.vts',
            'view_mode': 'list',
            'target': 'current',
        }

    def _send_quickbooks_failure_email(self):
        quickbook_instance = self.env['quickbooks.connect'].sudo().search([('state', '=', 'connected')])
        move_records = False
        payment_records = False
        move_model = self.env['account.move']
        payment_model = self.env['account.payment']
        for instance in quickbook_instance:
            if instance.auto_send_fail_transaction and instance.email_send_transaction:
                if 'error_in_export' in move_model._fields and instance.company_id.country_id.code != 'CA':
                    move_records = move_model.search(
                        [('error_in_export', '=', True), ('is_error_mail_send', '=', False),
                         ('company_id', '=', instance.company_id.id)])
                    payment_records = payment_model.search(
                        [('error_in_export', '=', True), ('is_error_mail_send', '=', False),
                         ('company_id', '=', instance.company_id.id)])
                if 'is_export_error' in move_model._fields and instance.company_id.country_id.code == 'CA':
                    move_records = move_model.search(
                        [('is_export_error', '=', True), ('is_error_mail_send', '=', False),
                         ('company_id', '=', instance.company_id.id)])
                    payment_records = payment_model.search(
                        [('is_export_error', '=', True), ('is_error_mail_send', '=', False),
                         ('company_id', '=', instance.company_id.id)])

                if move_records or payment_records:
                    data = {
                        'move_records': move_records.ids,
                        'payment_records': payment_records.ids,
                    }

                    report_action = self.env.ref(
                        'quickbooks_common_connector_vts.action_report_quickbooks_failed_document')

                    pdf_content, _ = self.env['ir.actions.report']._render_qweb_pdf(
                        report_action,
                        data={'data': data}
                    )
                    attachment = self.env['ir.attachment'].sudo().create({
                        'name': "QuickBooks_Failed_Records.pdf",
                        'type': 'binary',
                        'raw': pdf_content,
                        'res_model': 'quickbooks.connect',
                        'res_id': instance.id or 0,
                        'mimetype': 'application/pdf',
                    })
                    template = self.env.ref('quickbooks_common_connector_vts.email_template_quickbooks_failed_export')
                    template.attachment_ids = [(6, 0, [attachment.id])]
                    template.send_mail(instance.id, force_send=True)

                    if move_records:
                        move_records.write({'is_error_mail_send': True})
                    if payment_records:
                        payment_records.write({'is_error_mail_send': True})

        return True


class QuickbooksScope(models.Model):
    _name = "quickbooks.scope"
    _description = "QuickBooks Scope"

    name = fields.Char(string="Scope Name")
    value = fields.Char(string="Scope Value")
