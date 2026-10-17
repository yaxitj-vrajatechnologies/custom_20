# -*- coding: utf-8 *-*
import urllib.parse
import base64
import requests
import logging
from odoo import models, fields,_
_logger = logging.getLogger(__name__)

class XeroConnect(models.Model):

    _name = "xero.connect"
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = "Xero Connect"


    name = fields.Char(string="Name",tracking=True,help="Name of the Xero Instance")
    client_id = fields.Char(string="Client ID",tracking=True,copy=False, help="Xero client ID used for authentication" )
    client_secret = fields.Char(string="Client Secret",tracking=True,copy=False, help="Xero client secret used for authentication")
    redirect_url = fields.Char(string="Redirect URL",tracking=True,copy=False, help="Xero authentication redirect URL")
    tenant_id = fields.Char(string="Tenant ID", copy=False, help="Tenant identifier of the connected organization")
    xero_code = fields.Char(string="Xero Code", copy=False)
    xero_base_url = fields.Char(string="URL", default="https://api.xero.com/api.xro/2.0", help="Xero URL used for API requests")
    login_auth_url = fields.Char(string="Login Auth URL", default="https://login.xero.com/identity/connect/authorize", help="Authorization URL used for login")
    auth_token_url = fields.Char(string="Auth Token URL", default="https://identity.xero.com/connect/token", help="Token URL used to generate access credentials")
    access_token = fields.Char(string="Access token")
    refresh_token = fields.Char(string="Refresh token")
    from_date = fields.Datetime(string="From Date")
    state = fields.Selection([('connecting','Connecting'),('connected','Connected'),('failed','Failed')],string="State",tracking=True,default="connecting")
    reason = fields.Text(string="Reason")
    company_id = fields.Many2one('res.company',string="Company",tracking=True,default=lambda self: self.env.user.company_id)
    country_id = fields.Many2one('res.country',string="Country",copy=False)
    xero_company_id = fields.Many2one('xero.company.vts',tracking=True, string="Xero Company")
    user_id = fields.Many2one('res.users',tracking=True, string="Failure User", help="On import failure, an activity is created in the chatter and assigned to this user")
    xero_customer_count = fields.Integer(string="Customer Count", compute='_compute_customer_count')
    xero_account_count = fields.Integer(string="Accounts Count", compute='_compute_xero_account_count')
    xero_taxes_count = fields.Integer(string="Taxes Count", compute='_compute_xero_taxes_count')
    xero_product_count = fields.Integer(string="Product Count", compute='_compute_xero_product_count')
    xero_invoice_count = fields.Integer(string="Invoice Count", compute='_compute_xero_invoice_count')
    xero_bill_count = fields.Integer(string="Bill Count", compute='_compute_xero_bill_count')
    xero_vendor_count = fields.Integer(string="Vendor Count", compute='_compute_vendor_count')
    xero_payment_count = fields.Integer(string="Payments Count",compute="_compute_xero_payment_count")
    xero_purchase_order_count = fields.Integer(string="Purchase Order Count",compute='_compute_xero_purchase_order_count')
    xero_customer_creation = fields.Boolean(string="Customer Creation", default=False, help="Enable this option to allow creation of customer")
    xero_product_creation = fields.Boolean(string="Product Creation", default=False, help="Enable this option to allow creation of product")
    xero_account_creation = fields.Boolean(string="Account Creation", default=False, help="Enable this option to allow creation of account")
    xero_tax_creation = fields.Boolean(string="Tax Creation", default=False, help="Enable this option to allow creation of tax")
    xero_analytic_creation = fields.Boolean(string="Analytic Account Creation", default=False, help="Enable this option to allow creation of analytic account")
    xero_contact_group_creation = fields.Boolean(string="Contact Group Creation", default=False, help="Enable this option to allow creation of contact group")
    auto_update_invoice_bill = fields.Boolean(string="Auto Update Invoices & Bills",help="Enable this option to automatically update Invoice/bill")
    auto_invoice_bill_export = fields.Boolean(string="Automatic Export Invoices & Bills to Xero", help="Enable this option to automatically export Invoice/bill")
    auto_payment_export = fields.Boolean(string="Automatic Export Payment to Xero", help="Enable this option to automatically export payment")
    partner_id = fields.Many2one('res.partner',string="Consolidated Partner", help="Select the partner for invoice consolidated")
    consolidated_invoice = fields.Boolean(string="Consolidated Invoices", default=False,help="Enable this option to consolidate (merge) multiple invoices into a single invoice during export")
    auto_import_invoice_bill = fields.Boolean(string="Automatic Import Invoice/bill",default=False, help="Enable this option if you want to import Invoice/bill automatically")
    auto_import_payment = fields.Boolean(string="Automatic Import Payment",default=False, help="Enable this option if you want to  import payment automatically")

    def _compute_customer_count(self):
        for rec in self:
            rec.xero_customer_count = self.env['xero.partner.map'].search_count([('xero_instance_id', '=', rec.id)])

    def action_xero_customer(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Xero Customer Mapping',
            'res_model': 'xero.partner.map',
            'view_mode': 'list,form',
            'target': 'current',
            'domain': [('xero_instance_id', '=', self.id)],
        }

    def _compute_vendor_count(self):
        for rec in self:
            rec.xero_vendor_count = self.env['xero.partner.map'].search_count([('xero_instance_id', '=', rec.id)])

    def action_xero_vendor(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Xero Customer Mapping',
            'res_model': 'xero.partner.map',
            'view_mode': 'list,form',
            'target': 'current',
            'domain': [('xero_instance_id', '=', self.id)],

        }

    def _compute_xero_account_count(self):
        for rec in self:
            rec.xero_account_count = self.env['xero.account.map'].search_count([('xero_instance_id', '=', rec.id)])

    def action_xero_account(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Xero Account Mapping',
            'res_model': 'xero.account.map',
            'view_mode': 'list,form',
            'target': 'current',
            'domain': [('xero_instance_id', '=', self.id)],
        }

    def _compute_xero_taxes_count(self):
        for rec in self:
            rec.xero_taxes_count = self.env['xero.tax.map'].search_count([('xero_instance_id', '=', rec.id)])

    def action_xero_taxes(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Xero Tax Mapping',
            'res_model': 'xero.tax.map',
            'view_mode': 'list,form',
            'target': 'current',
            'domain': [('xero_instance_id', '=', self.id)],
        }

    def _compute_xero_product_count(self):
        for rec in self:
            rec.xero_product_count = self.env['xero.product.map'].search_count([('xero_instance_id', '=', rec.id)])

    def action_xero_product(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Xero Product Mapping',
            'res_model': 'xero.product.map',
            'view_mode': 'list,form',
            'target': 'current',
            'domain': [('xero_instance_id', '=', self.id)],
        }

    def _compute_xero_invoice_count(self):
        for rec in self:
            rec.xero_invoice_count  = self.env['account.move'].search_count([('xero_ref_id', '!=', False),('move_type', '=', 'out_invoice')])

    def action_xero_invoice(self):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id("account.action_move_out_invoice_type")
        action['domain'] = [('xero_ref_id', '!=', False), ('move_type', '=', 'out_invoice')]
        return action

    def _compute_xero_bill_count(self):
        for rec in self:
            rec.xero_bill_count = self.env['account.move'].search_count([('xero_ref_id','!=', False),('move_type', '=', 'in_invoice')])

    def action_xero_bill(self):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id("account.action_move_in_invoice_type")
        action['domain'] = [('xero_ref_id', '!=', False), ('move_type', '=', 'in_invoice')]
        return action

    def _compute_xero_payment_count(self):
        for rec in self:
            rec.xero_payment_count = self.env['account.payment'].search_count([('xero_instance_id', '=', rec.id)])

    def action_xero_payment(self):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id("account.action_account_payments")
        action['domain'] = [('xero_instance_id', '=', self.id)]
        return action

    def _compute_xero_purchase_order_count(self):
        for rec in self:
            rec.xero_purchase_order_count = self.env['purchase.order'].search_count([
                ('xero_instance_id', '=', rec.id)
            ])
    def action_xero_purchase_order(self):
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id(
            "purchase.purchase_rfq"
        )
        action['domain'] = [('xero_instance_id', '=', self.id)]
        return  action

    def action_xero_open_instance_view_form(self):
        """
        Action to open instance form view
        """
        form_id = self.sudo().env.ref('xero_odoo_integration.xero_connect_form_view')
        action = {
            'name': _('Xero Instance'),
            'view_id': False,
            'res_model': 'xero.connect',
            'context': self._context,
            'view_mode': 'form',
            'res_id': self.id,
            'views': [(form_id.id, 'form')],
            'type': 'ir.actions.act_window',
        }
        return action

    def action_connect_xero(self):
        """
        Redirect user to Xero OAuth2 authorization page
        """
        self.ensure_one()

        scope_values = "offline_access accounting.transactions accounting.contacts accounting.settings"
        encoded_scopes = urllib.parse.quote(scope_values)

        auth_url = (
            f"{self.login_auth_url}"
            f"?response_type=code"
            f"&client_id={self.client_id}"
            f"&redirect_uri={urllib.parse.quote(self.redirect_url)}"
            f"&scope={encoded_scopes}"
            f"&state={self.id}"
        )

        return {
            "type": "ir.actions.act_url",
            "url": auth_url,
            "target": "self",
        }

    def refresh_xero_access_token(self):
        """
        Method to refresh the access token of xero
        """
        xero_connects = self if self else self.env['xero.connect'].sudo().search([('state','=', 'connected')])
        for rec in xero_connects:
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
                        "reason": "Successfully connected with Xero"
                    })
                else:
                    rec.write({"reason": f"Token refresh failed: {response.text}"})
            except requests.exceptions.RequestException as e:
                rec.write({"reason": str(e)})

    def reconnect_with_xero(self):
        self.state = 'connecting'
        self.access_token = ''

    def action_import_operation(self):
        """
        Action for opening Operation Wizard in instance
        """
        operation = self.env['xero.operations']
        return {
            'type': 'ir.actions.act_window',
            'name': 'Xero Import Operation',
            'res_model': 'xero.operations',
            'view_mode': 'form',
            'target': 'new',
            'res_id': operation.id,
        }

    def action_xero_logs_view(self):
        """
        Logs Button Action in Instance
        """
        return {
            'type': 'ir.actions.act_window',
            'name': 'Xero Logs',
            'res_model': 'xero.log.vts',
            'view_mode': 'list,form',
            'target': 'current',
        }

    def auto_import_moves_payment_from_xero(self):
        """
        This method is used for :
        Auto import of Invoice,Bill,Credit Note and refund if the flag of auto_import_invoice_bill is true at instance level
        Auto Import of prepayment,Overpayment and Payment if the flag of auto_import_payment is true at instance level
        """
        XeroConnect = self.env['xero.connect'].sudo()
        XeroOperationModel = self.env['xero.operations'].sudo()

        xero_instances = XeroConnect.search([('state', '=', 'connected')])

        for instance in xero_instances:
            try:

                XeroOperation = XeroOperationModel.create({'xero_instance_id': instance.id})

                xero_url = instance.xero_base_url
                company_id = instance.tenant_id
                token = instance.access_token

                if instance.auto_import_invoice_bill:
                    invoice_info,invoice_status = self.env['xero.api.vts'].get_data_from_xero(
				            xero_url, company_id, token, 'import_invoice')

                    if invoice_info and invoice_status:
                        invoice_list = invoice_info.get("Invoices", [])
                        queue_ids = self.env['move.data.queue'].create_xero_invoice_queue_job(instance, invoice_list)
                        if queue_ids:
                            model_action = "xero_odoo_integration.action_xero_creditnote_queue"
                            model_form = "xero_odoo_integration.xero_creditnote_queue_form_view"

                    credit_info,credit_status = self.env['xero.api.vts'].get_data_from_xero(
				            xero_url, company_id, token, 'import_creditnote')

                    if credit_info and credit_status:
                        creditnote_list = credit_info.get("CreditNotes", [])
                        queue_ids = self.env['creditnote.data.queue'].create_xero_creditnote_queue_job(
                            instance, creditnote_list)
                        if queue_ids:
                            model_action = "xero_odoo_integration.action_xero_creditnote_queue"
                            model_form = "xero_odoo_integration.xero_creditnote_queue_form_view"

                if instance.auto_import_payment:
                    payment_info,payment_status = self.env['xero.api.vts'].get_data_from_xero(
				            xero_url, company_id, token, 'import_payment')
                    XeroOperation.get_payments_from_xero(payment_info,payment_status)

                    prepayment_info,prepayment_status = self.env['xero.api.vts'].get_data_from_xero(
				            xero_url, company_id, token, 'import_prepayment')

                    XeroOperation.get_prepayment_from_xero(prepayment_info,prepayment_status)

                    overpayment_info, overpayment_status =  self.env['xero.api.vts'].get_data_from_xero(
				            xero_url, company_id, token, 'import_overpayment')

                    XeroOperation.get_overpayment_from_xero(overpayment_info, overpayment_status)

            except Exception as e:
                _logger.error("Xero import failed for instance %s", instance.id, e)

    def unlink(self):
        for rec in self:
            self.env['xero.partner.map'].sudo().search([('xero_instance_id', '=', rec.id)]).unlink()
            self.env['xero.product.map'].sudo().search([('xero_instance_id', '=', rec.id)]).unlink()
            self.env['xero.tax.map'].sudo().search([('xero_instance_id', '=', rec.id)]).unlink()
            self.env['xero.analytic.account.map'].sudo().search([('xero_instance_id', '=', rec.id)]).unlink()
            self.env['xero.contact.group.map'].sudo().search([('xero_instance_id', '=', rec.id)]).unlink()
            self.env['xero.account.map'].sudo().search([('xero_instance_id', '=', rec.id)]).unlink()

        return super(XeroConnect, self).unlink()



