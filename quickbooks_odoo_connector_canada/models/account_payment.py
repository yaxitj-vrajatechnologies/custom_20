# -*- coding: utf-8 *-*
import requests
import json
import pprint
import logging
from odoo import models, fields

_logger = logging.getLogger(__name__)

class AccountPayment(models.Model):
    _inherit = "account.payment"

    qck_instance_id = fields.Many2one('quickbooks.connect', string="Quickbook Instance", copy=False)
    qkca_payment_ID = fields.Char(string="Quickbook Payment ID",copy=False)
    qkca_billpay_ID = fields.Char(string="Quickbook Bill Payment ID", copy=False)
    is_export_error = fields.Boolean(string="Error in QuickBooks Export", default=False)
    is_cust_payment_exported = fields.Boolean(string="Is Customer Payment Exported ", default=False, copy=False)
    is_bill_payment_exported = fields.Boolean(string="Is Bill Payment Exported ", default=False, copy=False)

    def action_qkca_instance_for_payment(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Quickbook Instance Wizard',
            'res_model': 'quickbook.instance.wizard',
            'view_mode': 'form',
            'target': 'new',
        }

    def write(self, vals):
        if self.env.context.get('skip_update'):
            return super(AccountPayment, self).write(vals)

        qbo_trigger_fields = ['name', 'partner_id', 'amount', 'date']

        update_needed = any(field in vals for field in qbo_trigger_fields)
        res = super(AccountPayment, self).write(vals)
        if not update_needed:
            return res

        res = super(AccountPayment, self).write(vals)

        payment_type_map = {'inbound': {'qkca_id_field': 'qkca_payment_ID', 'url_endpoint': 'payment'},
                            'outbound': {'qkca_id_field': 'qkca_billpay_ID', 'url_endpoint': 'billpayment'}}

        for payment in self:
            company_id = payment.company_id.id if payment.company_id else False
            quickbook_instance = self.env['quickbooks.connect'].sudo().search([('state', '=', 'connected'), ('company_id', '=', company_id)], limit=1)
            if quickbook_instance and quickbook_instance.qkca_auto_update_payment:
                payment_type_info = payment_type_map.get(payment.payment_type)
                if not payment_type_info:
                    continue

                qkca_id = getattr(payment, payment_type_info['qkca_id_field'], None)
                if not qkca_id:
                    continue

                company = payment.company_id.id if payment.company_id else False
                quickbook_instance = self.env['quickbooks.connect'].sudo().search(
                    [('company_id', '=', company), ('state', '=', 'connected')], limit=1)

                if not (quickbook_instance and quickbook_instance.access_token and quickbook_instance.realm_id):
                    payment.message_post(body="QuickBooks Payment Update Failed: Authentication required")
                    continue

                try:
                    headers = {"Authorization": f"Bearer {quickbook_instance.access_token}",
                               "Content-Type": "application/json",
                               "Accept-Encoding": "identity", }

                    payment_account = payment.journal_id.default_account_id

                    if payment.payment_type == 'inbound':
                        partner_mapping = self.env['qbo.partner.map.vts'].sudo().search(
                            [('partner_id', '=', payment.partner_id.id),
                             ('quickbook_instance_id', '=', quickbook_instance.id),
                             ('company_id', '=', payment.company_id.id)])

                        payment_payload, endpoint = self._prepare_customer_payment_payload(payment,partner_mapping,quickbook_instance)
                    else:
                        account_mapping = self.env['qbo.account.vts'].sudo().search(
                            [('account_id', '=', payment_account.id), ('quickbook_account_id', '!=', False),
                             ('quickbook_instance_id', '=', quickbook_instance.id)], limit=1)
                        partner_mapping = self.env['qbo.vendor.ca.map.vts'].sudo().search([('vendor_id', '=', payment.partner_id.id),
                             ('quickbook_instance_id', '=', quickbook_instance.id),
                             ('company_id', '=', payment.company_id.id)])

                        if payment_account and not account_mapping:
                            payment.message_post(body=f"Account {payment_account.display_name} not mapped with QuickBooks.")
                            continue

                        payment_payload, endpoint = self._prepare_bill_payment_payload(payment,partner_mapping,quickbook_instance)

                    url_get = f"{quickbook_instance.quickbook_base_url}/{quickbook_instance.realm_id}/{payment_type_info['url_endpoint']}/{qkca_id}"
                    response_get = requests.get(url_get, headers=headers)
                    response_get.raise_for_status()

                    response_data = quickbook_instance.convert_response_xmltodict(response_get.text).get("IntuitResponse", {})
                    existing_payment = response_data.get('BillPayment' if payment.payment_type == 'outbound' else 'Payment',
                                                         {}) or {}
                    sync_token = existing_payment.get("SyncToken", "0")

                    payment_payload.update({"Id": qkca_id, "SyncToken": sync_token})

                    parsed_dict = json.dumps(payment_payload)
                    _logger.info("Export Update Dict for Payment %s: %s", payment.name, parsed_dict)

                    url_update = f"{quickbook_instance.quickbook_base_url}/{quickbook_instance.realm_id}/{payment_type_info['url_endpoint']}"
                    result = requests.post(url_update, headers=headers, data=parsed_dict)
                    update_result_res = quickbook_instance.convert_response_xmltodict(result.text)

                    if result.ok:
                        payment.message_post(body=f"{payment.name} updated successfully to QuickBooks")
                    else:
                        fault = update_result_res.get("IntuitResponse", {}).get("Fault", {})
                        error = fault.get("Error", {})
                        combined_msg = error.get("Message", "")
                        if error.get("Detail"):
                            combined_msg += f": {error.get('Detail')}"
                        payment.message_post(body=f"Payment Update Error: {combined_msg}")

                except requests.exceptions.RequestException as req_err:
                    payment.message_post(body=f"Request error while updating {payment.name}: {req_err}")
                except Exception as e:
                    payment.message_post(body=f"Unexpected error while updating {payment.name}: {e}")

        return res

    def _prepare_customer_payment_payload(self, payment,mapping_partner,quickbook_instance):
        payment_method_map = self.env['qbo.payment.method.vts'].sudo().search(
            [('journal_id', '=', payment.journal_id.id)], limit=1)
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
        invoices = invoices.filtered(lambda m: m.move_type in ['out_invoice', 'out_refund'])

        # Single invoice → send full payment amount
        if len(invoices) == 1:
            inv = invoices[0]

            # Customer invoice payment
            if inv.move_type == 'out_invoice' and inv.qkca_invoice_ID:
                payment_payload["Line"] = [{
                    "Amount": payment.amount,
                    "LinkedTxn": [{
                        "TxnId": str(inv.qkca_invoice_ID),
                        "TxnType": "Invoice"
                    }]
                }]

            # Customer credit note payment (refund)
            elif inv.move_type == 'out_refund' and inv.qkca_invoice_ID:
                payment_payload["Line"] = [{
                    "Amount": payment.amount,
                    "LinkedTxn": [{
                        "TxnId": str(inv.qkca_invoice_ID),
                        "TxnType": "CreditMemo"
                    }]
                }]


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
                    if inv.move_type == 'out_invoice' and inv.qkca_invoice_ID:
                        payment_payload["Line"].append({
                            "Amount": apply_amount,
                            "LinkedTxn": [{
                                "TxnId": str(inv.qkca_invoice_ID),
                                "TxnType": "Invoice"
                            }]
                        })

                    # Customer credit note lines
                    elif inv.move_type == 'out_refund' and inv.qkca_invoice_ID:
                        payment_payload["Line"].append({
                            "Amount": apply_amount,
                            "LinkedTxn": [{
                                "TxnId": str(inv.qkca_invoice_ID),
                                "TxnType": "CreditMemo"
                            }]
                        })

        payment_account = payment.journal_id.default_account_id
        account_mapping = self.env['qbo.account.vts'].sudo().search(
            [('account_id', '=', payment_account.id), ('quickbook_account_id', '!=', False),
             ('quickbook_instance_id', '=', quickbook_instance.id)], limit=1)

        quickbooks_id =  account_mapping.quickbook_account_id
        quickbooks_name = account_mapping.quickbook_account_name

        if payment_account and quickbooks_id:
            payment_payload["DepositToAccountRef"] = {
                "value": quickbooks_id,
                "name": quickbooks_name}

        return payment_payload, "payment"

    def export_customer_payment_qkca(self, payment,quickbook_instance):

        if payment.qkca_payment_ID:
            payment.message_post(body=f"Payment already exported to QuickBooks with ID {payment.qkca_payment_ID}.")
            return

        company = payment.company_id.id if payment.company_id else False

        if not quickbook_instance:
            payment.message_post(body=f"No QuickBooks instance configured for {company} company.")
            return

        log_id = self.env['quickbooks.log.vts'].sudo().generate_quickbooks_logs(
            quickbooks_operation_name="customer_payment", quickbooks_operation_type="export",
            instance=quickbook_instance.id, quickbooks_operation_message=f"Starting export for Payment {payment.name}")

        mapping_partner = self.env['qbo.partner.map.vts'].search(
            [('partner_id', '=', payment.partner_id.id), ('quickbook_id', '!=', False),('quickbook_instance_id','=',quickbook_instance.id)], limit=1)
        if not mapping_partner:
            qbk_id = payment.partner_id.export_to_quickbooks_ca(payment.partner_id, 'customer', 'quickbook_id',quickbook_instance)
            mapping_partner = self.env['qbo.partner.map.vts'].search(
                [('partner_id', '=', payment.partner_id.id), ('quickbook_id', '=', qbk_id),
                 ('quickbook_instance_id', '=', quickbook_instance.id)], limit=1)

            if mapping_partner:
                msg = f"Customer {payment.partner_id.name} Created into QuickBooks, ID:{qbk_id}"
                payment.message_post(body=msg)
            else:
                msg = qbk_id
                payment.message_post(body=msg)
                payment.is_export_error = True
                self.env['quickbooks.log.vts.line'].sudo().generate_quickbooks_process_line(
                    quickbooks_operation_name="customer_payment",
                    quickbooks_operation_type="export", instance=quickbook_instance.id,
                    quickbooks_operation_message=msg, process_request_message={},
                    process_response_message={}, log_id=log_id, fault_operation=True)
                return

        payment_payload, endpoint = self._prepare_customer_payment_payload(payment, mapping_partner,quickbook_instance)

        try:
            payment_url = f"{quickbook_instance.quickbook_base_url}/{quickbook_instance.realm_id}/{endpoint}"

            response_json, status_code = self.env['quickbooks.api.vts'].sudo().qb_post_request(
                quickbook_instance.access_token, payment_url, payment_payload)

            if status_code == 200:
                payment_data = response_json.get("Payment", {})
                qkca_payment_ID = payment_data.get("Id")
                payment.qkca_payment_ID = qkca_payment_ID
                payment.qck_instance_id = quickbook_instance.id
                payment.is_export_error = False
                payment.is_cust_payment_exported = True
                map_payment_vals = {
                    'quickbook_instance_id': quickbook_instance.id,
                    'quickbook_cust_payment_id': qkca_payment_ID,
                    'partner_id': mapping_partner.partner_id.id,
                    'payment_id': self.id,
                    'company_id': company,
                    'qbo_response': pprint.pformat(payment_data)
                }
                mapping_payment = self.env['qbo.payment.ca.map.vts'].create(map_payment_vals)
                payment.message_post(body=f"Exported Payment {payment.name} to QuickBooks, ID: {qkca_payment_ID}")
                self.env['quickbooks.log.vts.line'].sudo().generate_quickbooks_process_line(
                    quickbooks_operation_name="customer_payment", quickbooks_operation_type="export",
                    instance=quickbook_instance.id,
                    quickbooks_operation_message=f"Successfully exported Payment {payment.name}",
                    process_request_message=payment_payload, process_response_message=response_json,
                    log_id=log_id)
                return response_json
            else:
                msg = f"Failed to export Payment {payment.name} to QuickBooks. Response: {response_json}"
                payment.message_post(body=msg)
                payment.is_export_error = True
                self.env['quickbooks.log.vts.line'].sudo().generate_quickbooks_process_line(
                    quickbooks_operation_name="customer_payment", quickbooks_operation_type="export",
                    instance=quickbook_instance.id, quickbooks_operation_message=msg,
                    process_request_message=payment_payload, process_response_message=response_json,
                    log_id=log_id, fault_operation=True)
                return None

        except Exception as e:
            payment.message_post(body=f"Exception while exporting Payment {payment.name} to QuickBooks: {str(e)}")
            payment.is_export_error = True
            self.env['quickbooks.log.vts.line'].sudo().generate_quickbooks_process_line(
                quickbooks_operation_name="customer_payment", quickbooks_operation_type="export",
                instance=quickbook_instance.id, quickbooks_operation_message=f"Exception: {str(e)}",
                process_request_message=payment_payload, process_response_message=str(e),
                log_id=log_id, fault_operation=True)
            return None


    def _prepare_bill_payment_payload(self, payment,mapping_vendor,quickbook_instance):

        bills = payment.invoice_ids.sudo() or payment.reconciled_bill_ids.sudo()
        bills = bills.filtered(lambda inv: inv.move_type in ["in_invoice"])

        payment_method_map = self.env['qbo.payment.method.vts'].search([('journal_id', '=', payment.journal_id.id)],limit=1)
        bill_payment_payload = {"DocNumber": payment.name,
                                "VendorRef": {"value": mapping_vendor.quickbook_vendor_id,
                                              "name": mapping_vendor.quickbook_vendor_name},
                                "PayType": payment_method_map.quickbook_payment_method_name if payment_method_map else "Check",
                                "TxnDate": str(payment.date),
                                "TotalAmt": payment.amount,
                                "PrivateNote": payment.memo or "",
                                "Line": []}

        if len(bills) == 1:
            bill = bills[0]

            if bill.move_type == "in_invoice" and bill.qkca_bill_ID:
                bill_payment_payload["Line"] = [{
                    "Amount": payment.amount,
                    "LinkedTxn": [{
                        "TxnId": str(bill.qkca_bill_ID),
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
                            apply_amount += total_amount  # assign remainder to last

                        if bill.move_type == "in_invoice" and bill.qkca_bill_ID:
                            bill_payment_payload["Line"].append({
                                "Amount": apply_amount,
                                "LinkedTxn": [{
                                    "TxnId": str(bill.qkca_bill_ID),
                                    "TxnType": "Bill"
                                }]
                            })

        payment_account = payment.journal_id.default_account_id
        account_mapping = self.env['qbo.account.vts'].sudo().search(
            [('account_id', '=', payment_account.id), ('quickbook_account_id', '!=', False),
             ('quickbook_instance_id', '=', quickbook_instance.id)], limit=1)

        quickbook_acc_id =  account_mapping.quickbook_account_id
        quickbooks_acc_name =  account_mapping.quickbook_account_name

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

    def export_bill_payment_qkca(self,payment,quickbook_instance):
        if payment.qkca_billpay_ID:
            payment.message_post(
                body=f"Bill Payment already exported to QuickBooks with ID {payment.qkca_billpay_ID}.")
            return

        company = payment.company_id.id if payment.company_id else False

        if not quickbook_instance:
            payment.message_post(body=f"No QuickBooks instance configured for {company} company.")
            return

        log_id = self.env['quickbooks.log.vts'].sudo().generate_quickbooks_logs(
            quickbooks_operation_name="billpayment",
            quickbooks_operation_type="export", instance=quickbook_instance.id,
            quickbooks_operation_message=f"Starting export for Bill Payment {payment.name}")

        mapping_vendor = self.env['qbo.vendor.ca.map.vts'].search([('vendor_id','=',payment.partner_id.id),('quickbook_vendor_id','!=',False),('company_id','=',company)])

        if not mapping_vendor:
            qkca_vendor_ID = payment.partner_id.export_to_quickbooks_ca(payment.partner_id, 'vendor', 'quickbook_vendor_id',quickbook_instance)
            mapping_vendor = self.env['qbo.vendor.ca.map.vts'].search(
                [('vendor_id', '=', payment.partner_id.id), ('quickbook_vendor_id', '=', qkca_vendor_ID),('company_id', '=', company)],limit=1)

            if mapping_vendor:
                msg = f"Vendor {payment.partner_id.name} Created into QuickBooks."
                payment.message_post(body=msg)
            else:
                msg = qkca_vendor_ID
                payment.message_post(body=msg)
                payment.is_export_error = True
                self.env['quickbooks.log.vts.line'].sudo().generate_quickbooks_process_line(
                    quickbooks_operation_name="billpayment",
                    quickbooks_operation_type="export", instance=quickbook_instance.id,
                    quickbooks_operation_message=msg, process_request_message={},
                    process_response_message={}, log_id=log_id, fault_operation=True)
                return

        bill_payment_payload, endpoint = self._prepare_bill_payment_payload(payment, mapping_vendor,quickbook_instance)

        try:

            billpay_url = f"{quickbook_instance.quickbook_base_url}/{quickbook_instance.realm_id}/{endpoint}"

            response_json, status_code = self.env['quickbooks.api.vts'].sudo().qb_post_request(
                quickbook_instance.access_token, billpay_url, bill_payment_payload)

            if status_code == 200:
                billp_data = response_json.get("BillPayment", {})
                qbk_bp_id = billp_data.get("Id")
                payment.qkca_billpay_ID = qbk_bp_id
                payment.qck_instance_id = quickbook_instance.id
                payment.is_export_error = False
                payment.is_bill_payment_exported = True
                payment.message_post(body=f"Exported Bill Payment {payment.name} to QuickBooks, ID: {qbk_bp_id}")
                map_payment_vals = {
                    'quickbook_instance_id': quickbook_instance.id,
                    'quickbook_bill_payment_id': qbk_bp_id,
                    'partner_id': mapping_vendor.vendor_id.id,
                    'payment_id': self.id,
                    'company_id': company,
                    'qbo_response': pprint.pformat(billp_data)
                }
                mapping_payment = self.env['qbo.bill.payment.ca.map.vts'].create(map_payment_vals)
                self.env['quickbooks.log.vts.line'].sudo().generate_quickbooks_process_line(
                    quickbooks_operation_name="billpayment", quickbooks_operation_type="export",
                    instance=quickbook_instance.id,
                    quickbooks_operation_message=f"Successfully exported Bill Payment {payment.name}",
                    process_request_message=bill_payment_payload, process_response_message=response_json,
                    log_id=log_id)
                return response_json
            else:
                msg = f"Failed to export Bill Payment {payment.name} to QuickBooks. Response: {response_json}"
                payment.message_post(body=msg)
                payment.is_export_error = True
                self.env['quickbooks.log.vts.line'].sudo().generate_quickbooks_process_line(
                    quickbooks_operation_name="billpayment", quickbooks_operation_type="export",
                    instance=quickbook_instance.id, quickbooks_operation_message=msg,
                    process_request_message=bill_payment_payload, process_response_message=response_json,
                    log_id=log_id, fault_operation=True)
                return None

        except Exception as e:
            payment.message_post(
                body=f"Exception while exporting Bill Payment {payment.name} to QuickBooks: {str(e)}")
            payment.is_export_error = True
            self.env['quickbooks.log.vts.line'].sudo().generate_quickbooks_process_line(
                quickbooks_operation_name="billpayment", quickbooks_operation_type="export",
                instance=quickbook_instance.id, quickbooks_operation_message=f"Exception: {str(e)}",
                process_request_message=bill_payment_payload, process_response_message=str(e),
                log_id=log_id, fault_operation=True)

            return None

    def export_payment_to_quickbooks_ca(self,quickbook_instance):
        for payment in self:
            if payment.payment_type == "outbound":
                invoices = (payment.invoice_ids.sudo() or payment.reconciled_invoice_ids.sudo())
                if any(inv.move_type == "out_refund" for inv in invoices):
                    export_payment = self.export_customer_payment_qkca(payment,quickbook_instance)
                else:
                    export_bill_payment = self.export_bill_payment_qkca(payment,quickbook_instance)
            elif payment.payment_type == "inbound":
                export_payment = self.export_customer_payment_qkca(payment,quickbook_instance)
