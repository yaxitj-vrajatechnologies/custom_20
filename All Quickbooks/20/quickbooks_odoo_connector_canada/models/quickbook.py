# -*- coding: utf-8 -*-
import json
import xmltodict
import logging
from odoo import models, fields, api
from xmltodict import ParsingInterrupted

_logger = logging.getLogger(__name__)


class QuickbooksConnect(models.Model):

    _inherit = 'quickbooks.connect'

    qkca_product_creation = fields.Boolean(string="Product Creation",help="Enable this option to create a product if does not exist when importing.",copy=False)
    qkca_vendor_creation = fields.Boolean(string="Vendor Creation", help="Enable this option to create a vendor if does not exist when importing",copy=False)
    qkca_category_creation = fields.Boolean(string="Product Category Creation",help="Enable this option to create a product category if does not exist when importing.",copy=False)
    qca_product_count = fields.Integer(string="Product Count",compute="_compute_ca_product_count")
    qca_vendor_count = fields.Integer(string="Vendor Count",compute="_compute_ca_vendor_count")
    qkca_invoice_creation = fields.Boolean(string="Invoice Creation",help="Enable this option to create a invoice if does not exist when importing.",copy=False)
    qkca_bill_creation = fields.Boolean(string="Bill Creation",help="Enable this option to create a bill if does not exist when importing.",copy=False)
    qca_invoice_count = fields.Integer(string="Invoice Count", compute="_compute_invoice_count")
    qca_bill_count = fields.Integer(string="Bill Count",compute="_compute_bill_count")
    qkca_payment_creation = fields.Boolean(string="Customer Payment Creation", help="Enable this option to create a customer payment if does not exist when importing",copy=False)
    qca_payment_count =  fields.Integer(string="Customer Payment Count",compute="_compute_payment_count")
    qkca_bill_payment_creation = fields.Boolean(string="Bill Payment Creation",help="Enable this option to create a Vendor Bill if does not exist when importing.",copy=False)
    qca_billpayment_count = fields.Integer(string="Vendor Bill Payment Count", compute="_compute_billpayment_count")
    qkca_company_included_tax = fields.Boolean(string="Send Tax Included", copy=False)
    qkca_auto_moves_export = fields.Boolean(string='Automatic Invoice/Bills Export to QBO', default=False, help="Allow automatic export invoices from the beginning of the 'Export Date Point'.")
    qkca_auto_payments_export = fields.Boolean(string='Automatic Payment Export to QBO', default=False, help="Special 'Scheduled action' will run periodically and send to QBO Payments that were manually registered in Odoo for Vendor Bills/Customer Invoices.'.")
    qkca_export_moves_point_date = fields.Date(string="Export Date Point", default=fields.Date.today, help="Invoices/Bills export date point.")
    qkca_next_export_move_date = fields.Datetime(string="Next Export Point", compute="_compute_moves_next_moves_export", help="Next export date of Invoice?Bills")
    qkca_auto_update_invoice_bill = fields.Boolean(string="Auto Update Invoice/Bill",copy=False)
    qkca_auto_update_payment = fields.Boolean(string="Auto Update Payments", copy=False)
    last_sync_invoice_bill_date = fields.Datetime(string="Last Sync Invoice and Bill Date")
    last_sync_payment_date = fields.Datetime(string="Last Sync Payment Date")

    def _compute_ca_product_count(self):
            for rec in self:
                rec.qca_product_count = self.env['qbo.product.ca.map.vts'].sudo().search_count([('quickbook_instance_id', '=', rec.id)])

    def _compute_moves_next_moves_export(self):
        cron = self.env.ref('quickbooks_odoo_connector_canada.execute_export_move_to_quickbook_canada',
                            raise_if_not_found=False, )
        value = cron.nextcall if cron else False
        for rec in self:
            rec.qkca_next_export_move_date = value

    def action_qkb_product(self):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id('quickbooks_odoo_connector_canada.action_qkca_product_map')
        # action['context'] = {}
        action['domain'] = [('quickbook_instance_id', '=', self.id)]
        return action

    def _compute_ca_vendor_count(self):
        for rec in self:
            rec.qca_vendor_count = self.env['qbo.vendor.ca.map.vts'].search_count([('quickbook_instance_id', '=', rec.id)])

    def action_qkb_vendor(self):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id("quickbooks_odoo_connector_canada.action_qkca_vendor_ca_map")
        # action['context'] = {}
        action['domain'] = [('quickbook_instance_id', '=', self.id)]
        return action

    def _compute_invoice_count(self):
        for rec in self:
            rec.qca_invoice_count = self.env['account.move'].search_count([('qkca_invoice_ID', '!=', False)])

    def action_qkb_invoice(self):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id("account.action_move_out_invoice_type")
        # action['context'] = {}
        action['domain'] = [('qkca_invoice_ID', '!=', False)]
        return action

    def _compute_bill_count(self):
        for rec in self:
            rec.qca_bill_count = self.env['account.move'].search_count([('qkca_bill_ID', '!=', False)])

    def action_qkb_bill(self):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id("account.action_move_in_invoice_type")
        # action['context'] = {}
        action['domain'] = [('qkca_bill_ID', '!=', False)]
        return action

    def _compute_payment_count(self):
        for rec in self:
            rec.qca_payment_count = self.env['account.payment'].search_count([('qkca_payment_ID', '!=', False)])

    def action_qkb_customer_payment(self):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id("account.action_account_payments")
        action['context'] = {}
        action['domain'] = [('qkca_payment_ID', '!=', False)]
        return action

    def _compute_billpayment_count(self):
        for rec in self:
            rec.qca_billpayment_count = self.env['account.payment'].search_count([('qkca_billpay_ID', '!=', False)])

    def action_qkb_bill_payment(self):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id("account.action_account_payments_payable")
        action['context'] = {}
        action['domain'] = [('qkca_billpay_ID', '!=', False)]
        return action

    def unlink(self):
        for rec in self:
            self.env['qbo.invoice.map.vts'].sudo().search([('quickbook_instance_id', '=', rec.id)]).unlink()
            self.env['qbo.bill.ca.map.vts'].sudo().search([('quickbook_instance_id', '=', rec.id)]).unlink()
            self.env['qbo.bill.payment.ca.map.vts'].sudo().search([('quickbook_instance_id', '=', rec.id)]).unlink()
            self.env['qbo.category.ca.map.vts'].sudo().search([('quickbook_instance_id', '=', rec.id)]).unlink()
            self.env['qbo.payment.ca.map.vts'].sudo().search([('quickbook_instance_id', '=', rec.id)]).unlink()
            self.env['qbo.product.ca.map.vts'].sudo().search([('quickbook_instance_id', '=', rec.id)]).unlink()
            self.env['qbo.vendor.ca.map.vts'].sudo().search([('quickbook_instance_id', '=', rec.id)]).unlink()
        return super(QuickbooksConnect, self).unlink()

    @api.model
    def convert_response_xmltodict(self, response):
        try:
            if type(response) != dict:
                order_dict = xmltodict.parse(response)
            else:
                order_dict = response
        except ParsingInterrupted as e:
            _logger.error(e)
            raise e

        response_dict = json.loads(json.dumps(order_dict))
        return response_dict

    def export_moves_to_qkca(self):
        QKCAConnect = self.env['quickbooks.connect'].sudo()
        AccountMove = self.env['account.move'].sudo()

        quickbook_instances = QKCAConnect.search([('state', '=', 'connected'), ('qkca_auto_moves_export', '=', True)])

        for qbk in quickbook_instances:
            if qbk.qkca_export_moves_point_date:
                moves_domain = [('state', '=', 'posted'), ('invoice_date', '>=', qbk.qkca_export_moves_point_date),
                               ('is_export_error', '=', False), ('company_id', '=', qbk.company_id.id)]

                invoices = AccountMove.search(moves_domain + [('move_type', '=', 'out_invoice'),
                                                             ('is_qkca_inv_exported', '=', False)])
                for inv in invoices:
                    inv.export_invoice_to_quickbooks_ca(inv)

                bills = AccountMove.search(moves_domain + [('move_type', '=', 'in_invoice'),
                                                          ('is_qkca_bill_exported', '=', False)])

                for bill in bills:
                    bill.export_bill_to_quickbook_ca(bill)

                qbk.qkca_export_moves_point_date = fields.Date.today()

    def export_payments_to_qkca(self):
        QKCAConnect = self.env['quickbooks.connect'].sudo()
        AccountPayment = self.env['account.payment'].sudo()

        quickbook_instances = QKCAConnect.search([('state', '=', 'connected'), ('qkca_auto_payments_export', '=', True)])

        for qbk in quickbook_instances:
            payments_domain = [('date', '>=', qbk.qkca_export_moves_point_date),('state', 'in', ['in_process', 'paid']),
                               ('is_export_error', '=', False),('company_id', '=', qbk.company_id.id)]

            payments = AccountPayment.search(payments_domain)

            bill_payment = payments.filtered(lambda p: p.payment_type == 'outbound' and not p.is_bill_payment_exported)
            invoice_payments = payments.filtered(lambda p: p.payment_type == 'inbound' and not p.is_cust_payment_exported)

            for payment in bill_payment:
                payment.export_bill_payment_qkca(payment)

            for payment in invoice_payments:
                payment.export_customer_payment_qkca(payment)

    def import_moves_to_qkca(self):
        QKCAConnect = self.env['quickbooks.connect'].sudo()
        QuickbookOperationModel = self.env['quickbooks.operations'].sudo()
        now = fields.Datetime.now()

        quickbook_instances = QKCAConnect.search([('state', '=', 'connected'),('qkca_is_company_canada', '=', True)])

        for instance in quickbook_instances:

            try:

                QuickbookOperation = QuickbookOperationModel.create({'quickbook_instance_id': instance.id})
                qck_url = instance.quickbook_base_url
                company_id = instance.realm_id
                token = instance.access_token

                last_sync = instance.last_sync_invoice_bill_date

                from_date = last_sync.strftime('%Y-%m-%dT%H:%M:%S-07:00') if last_sync else None
                to_date = now.strftime('%Y-%m-%dT%H:%M:%S-07:00')

                invoice_info, invoice_status = self.env['quickbooks.api.vts'].sudo().get_data_from_quickbooks(
                    qck_url, company_id, token, 'import_invoice',
                    from_date=from_date, to_date=to_date
                )

                if invoice_info and invoice_status:
                        QuickbookOperation.get_invoice_from_quickbooks(invoice_info, invoice_status)

                bill_info, bill_status = self.env['quickbooks.api.vts'].sudo().get_data_from_quickbooks(
                    qck_url, company_id, token, 'import_vendor_bill',
                    from_date=from_date, to_date=to_date
                )

                if bill_info and bill_status:
                    QuickbookOperation.get_bill_from_quickbooks(bill_info, bill_status)

                if invoice_info or bill_info:
                    instance.last_sync_invoice_bill_date = now

            except Exception as e:
                _logger.error("QKCA import failed for instance %s: %s", instance.id, e)


    def import_payments_to_qkca(self):
        QKCAConnect = self.env['quickbooks.connect'].sudo()
        QuickbookOperationModel = self.env['quickbooks.operations'].sudo()
        now = fields.Datetime.now()

        quickbook_instances = QKCAConnect.search([('state', '=', 'connected'),('qkca_is_company_canada', '=', True)])

        for instance in quickbook_instances:
            try:
                QuickbookOperation = QuickbookOperationModel.create({'quickbook_instance_id': instance.id})

                qck_url = instance.quickbook_base_url
                company_id = instance.realm_id
                token = instance.access_token

                last_sync = instance.last_sync_payment_date

                from_date = last_sync.strftime('%Y-%m-%dT%H:%M:%S-07:00') if last_sync else None
                to_date = now.strftime('%Y-%m-%dT%H:%M:%S-07:00')

                cust_payment_info, cust_payment_status = self.env['quickbooks.api.vts'].sudo().get_data_from_quickbooks(qck_url,
                    company_id,token,'import_customer_payment',from_date=from_date,to_date=to_date)

                if cust_payment_info and cust_payment_status:
                    QuickbookOperation.get_customer_payment_from_quickbooks(cust_payment_info, cust_payment_status)

                billpayment_info, billpayment_status = self.env['quickbooks.api.vts'].sudo().get_data_from_quickbooks(qck_url,
                    company_id,token,'import_billpayment',from_date=from_date,to_date=to_date)

                if billpayment_info and billpayment_status:
                    QuickbookOperation.get_billpayment_from_quickbooks(billpayment_info, billpayment_status)

                if cust_payment_info or billpayment_info:
                    instance.last_sync_payment_date = now

            except Exception as e:
                _logger.error("QKCA payment import failed for instance %s: %s", instance.id, e)
