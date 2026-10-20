# -*- coding: utf-8 -*-
from odoo import models, fields, api
import json
import xmltodict
from xmltodict import ParsingInterrupted
from dateutil.relativedelta import relativedelta


class QuickbooksConnect(models.Model):
    _inherit = 'quickbooks.connect'

    product_creation = fields.Boolean(string="Product Creation",help="Enable this option to create a product if does not exist when importing.",copy=False)
    qck_product_count = fields.Integer(string="Product Count", compute='_compute_product_count')
    company_include_tax = fields.Boolean(string="Send Invoice Tax Included", copy=False)
    auto_export_moves = fields.Boolean(string='Automatic Invoice/Bills Export to QBO', default=False,help="Allow automatic export invoices from the beginning of the 'Export Date Point'.")
    auto_export_payments = fields.Boolean(string='Automatic Payment Export to QBO', default=False,help="Special 'Scheduled action' will run periodically and send to QBO Payments that were manually registered in Odoo for Vendor Bills/Customer Invoices.'.")
    export_moves_point_date = fields.Date(string="Export Date Point", default=fields.Date.today(),                                      help="Invoices/Bills export date point.")
    exp_qbk_moves_next_call_point = fields.Datetime(string="Next Export Point", compute="_compute_moves_next_exp_call")
    qbk_auto_update_invoice_bill = fields.Boolean(string="Auto Update Invoice/Bill",copy=False)
    qbk_auto_update_payment = fields.Boolean(string="Auto Update Payments",copy=False)
    payment_method_creation = fields.Boolean(string="Payment Method Creation", help="Ennable this option to create a Payment method if does not exist when importing.", copy=False)
    qck_vendor_count = fields.Integer(string="Vendor Counts", compute='_compute_vendor_count')
    vendor_creation = fields.Boolean(string="Vendor Creation",help="Enable this option to create a Vendor if does not exist when importing.")


    def unlink(self):
        for rec in self:
            self.env['qbo.product.vts'].sudo().search([('quickbook_instance_id', '=', rec.id)]).unlink()
        return super(QuickbooksConnect, self).unlink()


    def _compute_moves_next_exp_call(self):
        cron = self.env.ref('quickbooks_online_odoo_connector.excute_export_moves_to_quickbooks',
                            raise_if_not_found=False, )
        value = cron.nextcall if cron else False
        for rec in self:
            rec.exp_qbk_moves_next_call_point = value


    """Return dictionary object"""


    @api.model
    def convert_xmltodict(self, response):
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


    def _compute_product_count(self):
        for rec in self:
            rec.qck_product_count = self.env['qbo.product.vts'].search_count([('quickbook_instance_id', '=', rec.id)])

    def _compute_vendor_count(self):
        for rec in self:
            rec.qck_vendor_count = self.env['qbo.vendor.map.vts'].search_count([('quickbook_instance_id', '=', rec.id)])

    def action_qck_product(self):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id('quickbooks_online_odoo_connector.action_qbo_product_map')
        action['domain'] = [('quickbook_instance_id', '=', self.id)]
        return action

    def action_qck_vendor(self):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id("quickbooks_online_odoo_connector.action_qbk_vendor_map")
        # action['context'] = {}
        action['domain'] = [('quickbook_instance_id', '=', self.id)]
        return action

    def export_account_moves_to_qbk(self):
        QBConnect = self.env['quickbooks.connect'].sudo()
        AccountMove = self.env['account.move'].sudo()
        quickbook_instances = QBConnect.search([('state', '=', 'connected'), ('auto_export_moves', '=', True)])
        for qbk in quickbook_instances:
            if qbk.export_moves_point_date:
                base_domain = [('state', '=', 'posted'), ('invoice_date', '>=', qbk.export_moves_point_date),
                               ('error_in_export', '=', False), ('company_id', '=', qbk.company_id.id)]

                invoices = AccountMove.search(base_domain + [('move_type', '=', 'out_invoice'),
                                                             ('is_inv_exported', '=', False)])
                for inv in invoices:
                    inv.export_invoice_quickbooks(inv)

                bills = AccountMove.search(base_domain + [('move_type', '=', 'in_invoice'),
                                                          ('is_bill_exported', '=', False)])

                for bill in bills:
                    bill.export_vendor_bill_quickbooks(bill)

                qbk.export_moves_point_date = fields.Date.today()


    def export_payments_to_qbk(self):
        QBConnect = self.env['quickbooks.connect'].sudo()
        AccountPayment = self.env['account.payment'].sudo()
        quickbook_instances = QBConnect.search([('state', '=', 'connected'), ('auto_export_payments', '=', True)])
        for qbk in quickbook_instances:
            payments_domain = [('date', '>=', qbk.export_moves_point_date),
                               ('state', 'in', ['in_process', 'paid']),
                               ('error_in_export', '=', False),
                               ('company_id', '=', qbk.company_id.id)]
            payments = AccountPayment.search(payments_domain)

            outbound_payments = payments.filtered(lambda p: p.payment_type == 'outbound' and not p.is_bill_pay_exported)
            inbound_payments = payments.filtered(lambda p: p.payment_type == 'inbound' and not p.is_inv_pay_exported)

            for payment in outbound_payments:
                payment.export_bill_payment_qbo(payment)

            for payment in inbound_payments:
                payment.export_payment_qbo(payment)


    def export_credit_note_to_qbk(self):
        QBConnect = self.env['quickbooks.connect'].sudo()
        AccountMove = self.env['account.move'].sudo()
        quickbook_instances = QBConnect.search([('state', '=', 'connected'), ('auto_export_moves', '=', True)])
        for qbk in quickbook_instances:
            if qbk.export_moves_point_date:
                base_domain = [('state', '=', 'posted'), ('invoice_date', '>=', qbk.export_moves_point_date),
                               ('error_in_export', '=', False), ('company_id', '=', qbk.company_id.id)]

                invoices = AccountMove.search(base_domain + [('move_type', '=', 'out_refund'),
                                                             ('is_inv_exported', '=', False)])
                for inv in invoices:
                    inv.export_credit_note_quickbooks(inv)

                bills = AccountMove.search(base_domain + [('move_type', '=', 'in_refund'),
                                                          ('is_bill_exported', '=', False)])

                for bill in bills:
                    bill.export_bill_credit_note_to_quickbooks(bill)

                qbk.export_moves_point_date = fields.Date.today()
