# -*- coding: utf-8 -*-
import pprint
import requests
import json
import logging
from odoo import models, fields, _

_logger = logging.getLogger(__name__)

class AccountPayment(models.Model):
    _inherit = "account.payment"

    qk_bill_payment_ID = fields.Char(string="QuickBooks Bill Payment ID")
    qk_payment_ID = fields.Char(string="QuickBooks Payment ID")
    error_in_export = fields.Boolean(string="Error In Export")
    is_inv_pay_exported = fields.Boolean(string="Is Invoice Payment Exported", default=False)
    is_bill_pay_exported = fields.Boolean(string="Is Bill Payment Exported", default=False)
    qck_instance_id = fields.Many2one('quickbooks.connect', string="Quickbook Instance", copy=False)

    def action_qbk_instance_for_payment(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Quickbook Instance Wizard',
            'res_model': 'instance.wizard',
            'view_mode': 'form',
            'target': 'new',
        }

    def write(self, vals):
        qbo_trigger_fields = ['name', 'partner_id', 'amount', 'date']

        res = super(AccountPayment, self).write(vals)
        if not any(field in vals for field in qbo_trigger_fields):
            return res

        payment_type_map = {
            'inbound': {'url_endpoint': 'payment','partner_map_model': 'qbo.partner.map.vts','qbk_id_field': 'qk_payment_ID',},
            'outbound': {'url_endpoint': 'billpayment','partner_map_model' : 'qbo.vendor.map.vts','qbk_id_field': 'qk_bill_payment_ID'}
        }
        for payment in self:
            quickbook_instance = self.env['quickbooks.connect'].sudo().search([
                ('state', '=', 'connected'),
                ('company_id', '=', payment.company_id.id)
            ], limit=1)

            if not (quickbook_instance and quickbook_instance.qbk_auto_update_payment):
                continue

            payment_type_info = payment_type_map.get(payment.payment_type)
            if not payment_type_info:
                continue

            qbk_id = getattr(payment, payment_type_info['qbk_id_field'], None)
            if not qbk_id:
                continue

            if not (quickbook_instance.access_token and quickbook_instance.realm_id):
                payment.message_post(body="QuickBooks Payment Update Failed: Authentication required")
                continue

            try:
                headers = {
                    "Authorization": f"Bearer {quickbook_instance.access_token}",
                    "Content-Type": "application/json",
                    "Accept-Encoding": "identity",
                }

                if payment.payment_type == 'inbound':
                    partner_mapping = self.env['qbo.partner.map.vts'].sudo().search(
                        [('partner_id', '=', payment.partner_id.id), ('quickbook_instance_id','=',quickbook_instance.id),('company_id','=',payment.company_id.id)])

                    payment_payload, endpoint = self._prepare_payment_payload(payment,quickbook_instance,partner_mapping)
                else:
                    partner_mapping = self.env['qbo.vendor.map.vts'].sudo().search([('vendor_id','=',payment.partner_id.id), ('quickbook_instance_id','=',quickbook_instance.id),('company_id','=',payment.company_id.id)])
                    payment_payload, endpoint = self._prepare_billpayment_payload(payment,quickbook_instance,partner_mapping)

                url_get = f"{quickbook_instance.quickbook_base_url}/{quickbook_instance.realm_id}/{payment_type_info['url_endpoint']}/{qbk_id}"
                response_get = requests.get(url_get, headers=headers)
                response_get.raise_for_status()

                existing = quickbook_instance.convert_xmltodict(
                    response_get.text
                ).get("IntuitResponse", {}).get(
                    'BillPayment' if payment.payment_type == 'outbound' else 'Payment', {}
                ) or {}

                payment_payload.update({
                    "Id": qbk_id,
                    "SyncToken": existing.get("SyncToken", "0"),
                })
                result = requests.post(
                    f"{quickbook_instance.quickbook_base_url}/{quickbook_instance.realm_id}/{payment_type_info['url_endpoint']}",
                    headers=headers,
                    data=json.dumps(payment_payload))
                if result.ok:
                    payment.message_post(body=f"{payment.name} updated successfully to QuickBooks")
                else:
                    error = quickbook_instance.convert_xmltodict(result.text).get("IntuitResponse", {}).get("Fault",{}).get("Error", {})
                    msg = error.get("Message", "")
                    if error.get("Detail"):
                        msg += f": {error.get('Detail')}"
                    payment.message_post(body=f"Payment Update Error: {msg}")

            except Exception as e:
                payment.message_post(body=f"Unexpected error while updating {payment.name}: {e}")

        return res

    def _prepare_billpayment_payload(self, payment, quickbook_instance,mapping_vendor=None):

        bills = payment.invoice_ids.sudo() or payment.reconciled_bill_ids.sudo()
        bills = bills.filtered(lambda inv: inv.move_type in["in_invoice"])

        first_bill = bills[:1]
        vendor_name = first_bill.partner_id.name if first_bill else ""
        payment_method_map = self.env['qbo.payment.method.vts'].sudo().search([('journal_id', '=', payment.journal_id.id)],limit=1)
        bill_payment_payload = {"DocNumber": payment.name,
                "VendorRef": {"value": mapping_vendor.qbk_vendor_id,
                            "name": vendor_name},
                "PayType": payment_method_map.quickbook_payment_method_name if payment_method_map else "Check",
                "TxnDate": str(payment.date),
                "TotalAmt": payment.amount,
                "PrivateNote": payment.memo or "",
                "Line":[]}

        if len(bills) == 1:
            bill = bills[0]

            if bill.move_type == "in_invoice" and bill.qbk_bill_id:
                bill_payment_payload["Line"] = [{
                    "Amount": payment.amount,
                    "LinkedTxn": [{
                        "TxnId": str(bill.qbk_bill_id),
                        "TxnType": "Bill"
                    }]
                }]

        #  Multiple bills/credits → split using invoice_payments_widget
        else:
            total_amount = payment.amount
            last_index = len(bills)

            for idx, bill in enumerate(bills, start=1):
                apply_amount = 0
                widget = bill.invoice_payments_widget
                if isinstance(widget, str):
                    widget = json.loads(widget)

                for dct in widget.get("content", []):
                    if dct.get("account_payment_id") == payment.id:
                        apply_amount = dct.get("amount", 0)
                        break

                if apply_amount:
                    total_amount -= apply_amount
                    if idx == last_index and total_amount > 0:
                        apply_amount += total_amount

                    if bill.move_type == "in_invoice" and bill.qbk_bill_id:
                        bill_payment_payload["Line"].append({
                            "Amount": apply_amount,
                            "LinkedTxn": [{
                                "TxnId": str(bill.qbk_bill_id),
                                "TxnType": "Bill"
                            }]
                        })

        payment_account = payment.journal_id.default_account_id
        account_mapping = self.env['qbo.account.vts'].search([('account_id','=',payment_account.id),('quickbook_account_id','!=',False),('quickbook_instance_id','=',quickbook_instance.id)], limit=1)

        quickbook_acc_id =  account_mapping.quickbook_account_id
        quickbooks_acc_name= payment_account.name or account_mapping.quickbook_account_name

        if not quickbook_acc_id:
            msg = f"Account {payment_account.display_name} not mapped with QuickBooks."
            payment.message_post(body=msg)

        if payment.payment_method_line_id.payment_method_id.code == 'credit':
            bill_payment_payload.update({
                        "CreditCardPayment": {
                            "CCAccountRef": {
                                "name": quickbooks_acc_name,
                                "value": quickbook_acc_id}}})
        else:
            bill_payment_payload.update({
                        "CheckPayment": {
                            "BankAccountRef": {
                                "name": quickbooks_acc_name,
                                "value": quickbook_acc_id}}})

        return bill_payment_payload, "billpayment"

    def export_bill_payment_qbo(self, payment,quickbook_instance):

        if payment.qk_bill_payment_ID:
            payment.message_post(body=f"Bill Payment already exported to QuickBooks with ID {payment.qk_bill_payment_ID}.")
            return

        company = payment.company_id.id if payment.company_id else False

        if not quickbook_instance:
            payment.message_post(body=f"No QuickBooks instance configured for {company} company.")
            return

        log_id = self.env['quickbooks.log.vts'].sudo().generate_quickbooks_logs(quickbooks_operation_name="billpayment",
            quickbooks_operation_type="export",instance=quickbook_instance.id,
            quickbooks_operation_message=f"Starting export for Bill Payment {payment.name}")

        mapping_vendor = self.env['qbo.vendor.map.vts'].search([('vendor_id','=',payment.partner_id.id),('qbk_vendor_id','!=',False),('quickbook_instance_id', '=', quickbook_instance.id)],limit=1)
        if not mapping_vendor:
                qbk_vendor_id = payment.partner_id._export_to_quickbooks(payment.partner_id, 'vendor', 'qbk_vendor_id',quickbook_instance)
                mapping_vendor = self.env['qbo.vendor.map.vts'].search([('vendor_id', '=', payment.partner_id.id), ('qbk_vendor_id', '=', qbk_vendor_id),('company_id', '=', company)], limit=1)
                if mapping_vendor:
                    msg = f"Vendor {payment.partner_id.name} Created into QuickBooks."
                    payment.message_post(body=msg)
                else:
                    msg = qbk_vendor_id
                    payment.message_post(body=msg)
                    payment.error_in_export = True
                    self.env['quickbooks.log.vts.line'].sudo().generate_quickbooks_process_line(quickbooks_operation_name="billpayment",
                        quickbooks_operation_type="export",instance=quickbook_instance.id,
                        quickbooks_operation_message=msg,process_request_message={},
                        process_response_message={},log_id=log_id,fault_operation=True)
                    return

        bill_payment_payload, endpoint = self._prepare_billpayment_payload(payment,quickbook_instance, mapping_vendor)
        
        try:

            billp_url = f"{quickbook_instance.quickbook_base_url}/{quickbook_instance.realm_id}/{endpoint}"

            response_json, status_code = self.env['quickbooks.api.vts'].sudo().qb_post_request(
                quickbook_instance.access_token, billp_url, bill_payment_payload)

            if status_code == 200:
                billp_data = response_json.get("BillPayment", {})
                qbk_bp_id = billp_data.get("Id")
                payment.qk_bill_payment_ID = qbk_bp_id
                payment.qck_instance_id = quickbook_instance.id
                payment.error_in_export = False
                payment.is_bill_pay_exported = True
                payment.message_post(body=f"Exported Bill Payment {payment.name} to QuickBooks, ID: {qbk_bp_id}")
                self.env['quickbooks.log.vts.line'].sudo().generate_quickbooks_process_line(
                    quickbooks_operation_name="billpayment",quickbooks_operation_type="export",
                    instance=quickbook_instance.id,quickbooks_operation_message=f"Successfully exported Bill Payment {payment.name}",
                    process_request_message=bill_payment_payload,process_response_message=response_json,log_id=log_id)
                return response_json
            else:
                msg = f"Failed to export Bill Payment {payment.name} to QuickBooks. Response: {response_json}"
                payment.message_post(body=msg)
                payment.error_in_export = True
                self.env['quickbooks.log.vts.line'].sudo().generate_quickbooks_process_line(
                    quickbooks_operation_name="billpayment",quickbooks_operation_type="export",
                    instance=quickbook_instance.id,quickbooks_operation_message=msg,
                    process_request_message=bill_payment_payload,process_response_message=response_json,
                    log_id=log_id,fault_operation=True)
                return None

        except Exception as e:
            payment.message_post(body=f"Exception while exporting Bill Payment {payment.name} to QuickBooks: {str(e)}")
            payment.error_in_export = True
            self.env['quickbooks.log.vts.line'].sudo().generate_quickbooks_process_line(
                quickbooks_operation_name="billpayment",quickbooks_operation_type="export",
                instance=quickbook_instance.id,quickbooks_operation_message=f"Exception: {str(e)}",
                process_request_message=bill_payment_payload,process_response_message=str(e),
                log_id=log_id,fault_operation=True)
            
            return None

    def _prepare_payment_payload(self, payment,quickbook_instance,mapping_partner=None):
        payment_method_map = self.env['qbo.payment.method.vts'].sudo().search([('journal_id', '=', payment.journal_id.id)],limit=1)
        payment_payload = {
            "CustomerRef": {
                "value": mapping_partner.quickbook_id,
                "name": mapping_partner.quick_name
            },
            "PaymentRefNum": payment.name,
            "TotalAmt": payment.amount,
            "TxnDate": str(payment.date),
            "PrivateNote": payment.memo or "",
            "Line": []
        }
        if payment_method_map:
            payment_payload['PaymentMethodRef'] = {'value': payment_method_map.quickbook_id}

        invoices = payment.invoice_ids.sudo() or payment.reconciled_invoice_ids.sudo()
        invoices = invoices.filtered(lambda m: m.move_type in ['out_invoice','out_refund'])

        # Single invoice → send full payment amount
        if len(invoices) == 1:
            inv = invoices[0]

            # Customer invoice payment
            if inv.move_type == 'out_invoice' and inv.qbk_invoice_id:
                payment_payload["Line"] = [{
                    "Amount": payment.amount,
                    "LinkedTxn": [{
                        "TxnId": str(inv.qbk_invoice_id),
                        "TxnType": "Invoice"
                    }]
                }]

            # Customer credit note payment (refund)
            elif inv.move_type == 'in_refund' and inv.qbk_bill_id:
                payment_payload["Line"].append({
                    "Amount": payment.amount,
                    "LinkedTxn": [{
                        "TxnId": str(inv.qbk_bill_id),
                        "TxnType": "CreditMemo"
                    }]
                })

        # Multiple invoices → detect applied amounts from widget
        else:

            total_amount = payment.amount
            last_index = len(invoices)

            for idx, inv in enumerate(invoices, start=1):
                apply_amount = 0
                widget = inv.invoice_payments_widget

                if isinstance(widget, str):
                    widget = json.loads(widget)

                for dct in widget.get("content", []):
                    if dct.get("account_payment_id") == payment.id:
                        apply_amount = dct.get("amount", 0)
                        break

                if apply_amount:
                    total_amount -= apply_amount
                    if idx == last_index and total_amount > 0:
                        apply_amount += total_amount

                    # Customer invoice lines
                    if inv.move_type == 'out_invoice' and inv.qbk_invoice_id:
                        payment_payload["Line"].append({
                            "Amount": apply_amount,
                            "LinkedTxn": [{
                                "TxnId": str(inv.qbk_invoice_id),
                                "TxnType": "Invoice"
                            }]
                        })

                    # Customer credit note lines
                    elif inv.move_type == 'in_refund' and inv.qbk_bill_id:
                        payment_payload["Line"].append({
                            "Amount": apply_amount,
                            "LinkedTxn": [{
                                "TxnId": str(inv.qbk_bill_id),
                                "TxnType": "CreditMemo"
                            }]
                        })

        payment_account = payment.journal_id.default_account_id
        account_mapping = self.env['qbo.account.vts'].sudo().search([('account_id','=',payment_account.id),('quickbook_account_id','!=',False),('quickbook_instance_id','=',quickbook_instance.id)], limit=1)

        quickbooks_id = account_mapping.quickbook_account_id
        quickbooks_name= account_mapping.quickbook_account_name

        if quickbooks_id:
            payment_payload["DepositToAccountRef"] = {
                "value": quickbooks_id,
                "name":quickbooks_name,
            }
        return payment_payload, "payment"

    def export_payment_qbo(self, payment,quickbook_instance):

        if payment.qk_payment_ID:
            payment.message_post(body=f"Payment already exported to QuickBooks with ID {payment.qk_payment_ID}.")
            self._cr.commit()
            return

        invoices = payment.invoice_ids.sudo() or payment.reconciled_invoice_ids.sudo()
        missing_qbk_invoice = invoices.filtered(lambda inv: not inv.qbk_invoice_id)
        if missing_qbk_invoice:
            payment.message_post(body="Payment export skipped : linked invoices are not exported to QuickBooks.")
            return


        company = payment.company_id.id if payment.company_id else False

        if not quickbook_instance:
            payment.message_post(body=f"No QuickBooks instance configured for {company} company.")
            self._cr.commit()
            return

        log_id = self.env['quickbooks.log.vts'].sudo().generate_quickbooks_logs(
            quickbooks_operation_name="payment",quickbooks_operation_type="export",
            instance=quickbook_instance.id,quickbooks_operation_message=f"Starting export for Payment {payment.name}"
        )

        mapping_partner = self.env['qbo.partner.map.vts'].sudo().search([('partner_id','=',payment.partner_id.id),('quickbook_id','!=',False),('quickbook_instance_id', '=', quickbook_instance.id)], limit=1)
        if not mapping_partner:
                qbk_id = payment.partner_id._export_to_quickbooks(payment.partner_id, 'customer', 'quickbook_id',quickbook_instance)
                mapping_partner = self.env['qbo.partner.map.vts'].search([('partner_id', '=', payment.partner_id.id), ('quickbook_id', '=', qbk_id),('company_id', '=', company)], limit=1)

                if mapping_partner:
                    msg = f"Customer {payment.partner_id.name} Created into QuickBooks."
                    payment.message_post(body=msg)
                else:
                    msg = qbk_id
                    payment.message_post(body=msg)
                    payment.error_in_export = True
                    self.env['quickbooks.log.vts.line'].sudo().generate_quickbooks_process_line(quickbooks_operation_name="payment",
                        quickbooks_operation_type="export",instance=quickbook_instance.id,
                        quickbooks_operation_message=msg,process_request_message={},
                        process_response_message={},log_id=log_id,fault_operation=True)
                    return

        payment_payload, endpoint = self._prepare_payment_payload(payment, quickbook_instance,mapping_partner)

        try:
            payment_url = f"{quickbook_instance.quickbook_base_url}/{quickbook_instance.realm_id}/{endpoint}"

            response_json, status_code = self.env['quickbooks.api.vts'].sudo().qb_post_request(
                quickbook_instance.access_token, payment_url, payment_payload)

            if status_code == 200:
                payment_data = response_json.get("Payment", {})
                qk_payment_id = payment_data.get("Id")
                payment.qk_payment_ID = qk_payment_id
                payment.qck_instance_id = quickbook_instance.id
                payment.error_in_export = False
                payment.is_inv_pay_exported = True
                payment.message_post(body=f"Exported Payment {payment.name} to QuickBooks, ID: {qk_payment_id}")
                self.env['quickbooks.log.vts.line'].sudo().generate_quickbooks_process_line(
                    quickbooks_operation_name="payment",quickbooks_operation_type="export",
                    instance=quickbook_instance.id,quickbooks_operation_message=f"Successfully exported Payment {payment.name}",
                    process_request_message=payment_payload,process_response_message=response_json,
                    log_id=log_id)
                self._cr.commit()
                return response_json
            else:
                msg = f"Failed to export Payment {payment.name} to QuickBooks. Response: {response_json}"
                payment.message_post(body=msg)
                payment.error_in_export = True
                self.env['quickbooks.log.vts.line'].sudo().generate_quickbooks_process_line(
                    quickbooks_operation_name="payment",quickbooks_operation_type="export",
                    instance=quickbook_instance.id,quickbooks_operation_message=msg,
                    process_request_message=payment_payload,process_response_message=response_json,
                    log_id=log_id,fault_operation=True)
                self._cr.commit()
                return None

        except Exception as e:
            payment.message_post(body=f"Exception while exporting Payment {payment.name} to QuickBooks: {str(e)}")
            payment.error_in_export = True
            self.env['quickbooks.log.vts.line'].sudo().generate_quickbooks_process_line(
                quickbooks_operation_name="payment",quickbooks_operation_type="export",
                instance=quickbook_instance.id,quickbooks_operation_message=f"Exception: {str(e)}",
                process_request_message=payment_payload,process_response_message=str(e),
                log_id=log_id,fault_operation=True)
            self._cr.commit()
            return None

    def export_payment_to_quickbooks(self,quickbook_instance):
        for payment in self:
            if payment.payment_type == "outbound":
                invoices = (payment.invoice_ids.sudo() or payment.reconciled_invoice_ids.sudo())
                if any(inv.move_type == "out_refund" for inv in invoices):
                    export_payment = self.export_payment_qbo(payment,quickbook_instance)
                else:
                    export_bill_payment = self.export_bill_payment_qbo(payment,quickbook_instance)

            elif payment.payment_type == "inbound":
                export_payment = self.export_payment_qbo(payment,quickbook_instance)
            


