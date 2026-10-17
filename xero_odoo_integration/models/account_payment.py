# -*- coding: utf-8 *-*
import requests
import logging
from odoo import models, fields
from odoo.exceptions import ValidationError
import  json


class AccountPayment(models.Model):
    _inherit = "account.payment"

    xero_instance_id = fields.Many2one('xero.connect', string="Xero Instance",copy=False)
    xero_payment_id = fields.Char(string="Xero Payment Id",copy=False)
    xero_payment_type = fields.Selection(
        selection=[
            ('RECEIVE-OVERPAYMENT', 'Customer Overpayment'),
            ('SPEND-OVERPAYMENT', 'Vendor Overpayment'),
            ('RECEIVE-PREPAYMENT', 'Customer Prepayment'),
            ('SPEND-PREPAYMENT', 'Vendor Prepayment'),
            ('RECBATCH', 'Customer Payment'),
            ('PAYBATCH', "Vendor Payment"),
            ("ACCRECPAYMENT", 'Customer Payment'),
            ('ACCPAYPAYMENT', "Vendor Payment"),
        ],
        string='Xero Payment Type')
    def action_xero_instance_for_payment(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Xero Instance Wizard',
            'res_model': 'xero.instance.wizard',
            'view_mode': 'form',
            'target': 'new',
        }

    def create_payment_payload(self,payment,instance):

        is_customer = payment.payment_type == 'inbound'
        account = payment.journal_id.default_account_id
        xero_account_map = self.env['xero.account.map'].sudo().search(
            [('account_id', '=', account.id), ('xero_instance_id', '=', instance.id)], limit=1)
        if not xero_account_map:
            xero_account_map = account.export_account_to_xero(account, instance)
            if xero_account_map:
                payment.message_post(
                    body=f"Charts Of Account Successfully exported with ID : {xero_account_map.xero_account_id}")
            else:
                msg = "Failed to export charts of account to xero"
                log_id = self.env['xero.log.vts'].sudo().generate_xero_logs(
                    xero_operation_name="account", xero_operation_type="export",
                    instance=instance.id, xero_operation_message=f"failed to export charts of account tp xero.")
                self.env['xero.log.vts.line'].sudo().generate_xero_process_line(xero_operation_name="account",
                                                                                xero_operation_type="export",
                                                                                instance=instance.id,
                                                                                xero_operation_message=msg,
                                                                                log_id=log_id, fault_operation=True)
                return
        xero_account_id = xero_account_map.xero_account_id

        payload = {
            "Payments": [{
                "Invoice": {
                        "InvoiceID": payment.invoice_ids[0].xero_ref_id
                    },
                "Account": {
                    "AccountID": xero_account_id
                },
                "Amount": payment.amount,
                "Date": payment.date.strftime('%Y-%m-%d'),
                "PaymentType": "ACCRECPAYMENT" if is_customer else "ACCPAYPAYMENT",
                "Reference": payment.memo,
            }]
        }
        return payload


    def export_payment_to_xero(self,payment,instance):
        log_id = self.env['xero.log.vts'].sudo().generate_xero_logs(
            xero_operation_name='payment',
            xero_operation_type='export',
            instance=instance.id,
            xero_operation_message='Export Payment To Xero'
        )

        if payment.state != "paid" and payment.state != 'in_process':
            payment.message_post(body='Payment not in valid state to export, Only In Process and Paid Payments are Exported')
            self.env['xero.log.vts.line'].sudo().generate_xero_process_line(
                xero_operation_name='payment',
                xero_operation_type='export',
                instance=instance.id,
                xero_operation_message= 'Payment not in valid state to export, Only In Process and Paid Payments are Exported',
                log_id=log_id,
                fault_operation=True
            )
            return

        if payment.xero_payment_id:
            payment.message_post(body='Payment is Already Exported to Xero')
            self.env['xero.log.vts.line'].sudo().generate_xero_process_line(
                xero_operation_name='payment',
                xero_operation_type='export',
                instance=instance.id,
                xero_operation_message=f"Payment is Already Exported to Xero",
                log_id=log_id,
                fault_operation=False
            )
            return


        if not payment.invoice_ids:
            message = "Failed to exported Payment as it is not linked to any invoice/bill"
            payment.message_post(body=message)
            self.env['xero.log.vts.line'].sudo().generate_xero_process_line(
                xero_operation_name='payment',
                xero_operation_type='export',
                instance=instance.id,
                xero_operation_message=message,
                log_id=log_id,
                fault_operation=True
            )
            return
        invoice = payment.invoice_ids[0]

        if not invoice.xero_ref_id:
            payment.message_post(body='Failed to export Payment because the related Invoice/Bill has not been exported to Xero')
            self.env['xero.log.vts.line'].sudo().generate_xero_process_line(
                xero_operation_name='payment',
                xero_operation_type='export',
                instance=instance.id,
                xero_operation_message=" Customer Invoice not exported to Xero",
                log_id=log_id,
                fault_operation=True
            )
            return

        payload = self.create_payment_payload(payment,instance)
        try:
            request_url = f"{instance.xero_base_url}/Payments"

            data, status_code = self.env['xero.api.vts'].sudo().xero_post_request(instance.access_token,
                                                                                          instance.tenant_id,
                                                                                          request_url, payload)

            if status_code in (200, 201):
                xero_payment = data['Payments'][0]
                xero_payment_id = xero_payment.get('PaymentID')

                vals={
                    'xero_instance_id': instance.id,
                    'xero_payment_id': xero_payment_id,
                    'xero_payment_type' : "ACCRECPAYMENT" if xero_payment.get('PaymentType') == "ACCRECPAYMENT" else "ACCPAYPAYMENT"
                }

                payment.write(vals)
                payment.message_post(body=f"Exported Payment  to Xero with ID: {xero_payment_id}")
                self.env['xero.log.vts.line'].sudo().generate_xero_process_line(
                    xero_operation_name='payment',
                    xero_operation_type='export',
                    instance=instance.id,
                    xero_operation_message=f"Payment Successfully Exported",
                    log_id=log_id,
                    fault_operation=False
                )
            else:
                res_error = data.get('Message', data)
                msg = f"Failed to Export Payment to Xero, Response: {res_error}"
                payment.message_post(body=msg)
                self.env['xero.log.vts.line'].sudo().generate_xero_process_line(
                    xero_operation_name='payment',
                    xero_operation_type='export',
                    instance=instance.id,
                    xero_operation_message=msg,
                    process_request_message= payload,
                    process_response_message=data,
                    log_id=log_id,
                    fault_operation=True
                )
        except Exception as e:
            payment.message_post(body=f"Exception while exporting Payment  to Xero: {str(e)}")
            self.env['xero.log.vts.line'].sudo().generate_xero_process_line(xero_operation_name="payment",
                                                                                xero_operation_type="export",
                                                                                instance=instance.id,
                                                                                xero_operation_message=f"Exception: {str(e)}",
                                                                                process_request_message=payload,
                                                                                process_response_message=str(e),
                                                                                log_id=log_id, fault_operation=True)
        return None

    def create_batchpayment_payload(self, payment,instance):
        is_customer = payment.payment_type == 'inbound'
        account = payment.journal_id.default_account_id
        xero_account_map = self.env['xero.account.map'].sudo().search([('account_id', '=', account.id),('xero_instance_id', '=', instance.id)], limit=1)
        if not xero_account_map:
            xero_account_map = account.export_account_to_xero(account,instance)
            if xero_account_map:
                payment.message_post(body=f"Charts Of Account Successfully exported with ID : {xero_account_map.xero_account_id}")
            else:
                msg = "Failed to export charts of account to xero"
                log_id = self.env['xero.log.vts'].sudo().generate_xero_logs(
                    xero_operation_name="account", xero_operation_type="export",
                    instance=instance.id, xero_operation_message=f"failed to export charts of account tp xero.")
                self.env['xero.log.vts.line'].sudo().generate_xero_process_line(xero_operation_name="account",
                                                                                xero_operation_type="export",
                                                                                instance=instance.id,
                                                                                xero_operation_message=msg,
                                                                                log_id=log_id, fault_operation=True)
                return
        xero_account_id = xero_account_map.xero_account_id

        payments = []
        for invoice in payment.invoice_ids:
            widget=invoice.invoice_payments_widget
            if widget:
                if isinstance(widget,str):
                    widget=json.loads(widget)
                allocated_amount = 0.0
                for line in widget.get('content', []):

                    if line.get('move_id') == payment.move_id.id:
                        allocated_amount += line.get('amount')

                payments.append({
                        "Invoice": {
                            "InvoiceID": invoice.xero_ref_id
                        },
                        "Amount": allocated_amount
                    })
            else:
                payments.append({
                        "Invoice": {
                            "InvoiceID": invoice.xero_ref_id
                        },
                        "Amount": invoice.amount_total
                    })

        payload = {
            "Date": payment.date.strftime('%Y-%m-%d'),
            "Account": {
                "AccountID": xero_account_id
            },
            "Payments": payments
        }
        if is_customer:
            payload["Reference"] = payment.memo
        return payload

    def export_batchpayment_to_xero(self,payment,instance):
        log_id = self.env['xero.log.vts'].sudo().generate_xero_logs(
            xero_operation_name='payment',
            xero_operation_type='export',
            instance=instance.id,
            xero_operation_message='Export Payment To Xero'
        )

        if payment.state != "paid" and payment.state != 'in_process':
            payment.message_post(body=f"Payment not in valid state to export, Only In Process and Paid Payments are Exported")
            self.env['xero.log.vts.line'].sudo().generate_xero_process_line(
                xero_operation_name='payment',
                xero_operation_type='export',
                instance=instance.id,
                xero_operation_message= 'Payment not in valid state to export, Only In Process and Paid Payments are Exported',
                log_id=log_id,
                fault_operation=True
            )
            return
        if payment.xero_payment_id:
            payment.message_post(body=f"Skipping Already Exported Payment")
            self.env['xero.log.vts.line'].sudo().generate_xero_process_line(
                xero_operation_name='payment',
                xero_operation_type='export',
                instance=instance.id,
                xero_operation_message=f"Skipping Already Exported Payment",
                log_id=log_id,
                fault_operation=False
            )
            return

        if not payment.invoice_ids:
            message = "Payment not Exported as it is not linked to any invoice/bill"
            payment.message_post(body=message)
            self.env['xero.log.vts.line'].sudo().generate_xero_process_line(
                xero_operation_name='payment',
                xero_operation_type='export',
                instance=instance.id,
                xero_operation_message=message,
                log_id=log_id,
                fault_operation=True
            )
            return

        is_customer = payment.payment_type == 'inbound'
        invalid_invoice = False
        for invoice in payment.invoice_ids:
            if is_customer and not invoice.xero_ref_id:
                msg="Failed to Export Payments as Customer invoices not exported to Xero"
                payment.message_post(body=msg)
                self.env['xero.log.vts.line'].sudo().generate_xero_process_line(
                    xero_operation_name='payment',
                    xero_operation_type='export',
                    instance=instance.id,
                    xero_operation_message=msg,
                    log_id=log_id,
                    fault_operation=True
                )
                invalid_invoice=True
            if not is_customer and not invoice.xero_ref_id:
                msg="Failed to Export Payments as Vendor bills not exported to Xero"
                payment.message_post(body=msg)
                self.env['xero.log.vts.line'].sudo().generate_xero_process_line(
                    xero_operation_name='payment',
                    xero_operation_type='export',
                    instance=instance.id,
                    xero_operation_message=msg,
                    log_id=log_id,
                    fault_operation=True
                )
                invalid_invoice=True
        if invalid_invoice:
            return

        payload = self.create_batchpayment_payload(payment,instance)
        try:
            request_url = f"{instance.xero_base_url}/BatchPayments"
            response_json, status_code = self.env['xero.api.vts'].sudo().xero_put_request(instance.access_token,
                                                                                              instance.tenant_id,request_url,payload)
            if status_code in (200, 201):
                batch = response_json['BatchPayments'][0]
                batch_payment_id = batch['BatchPaymentID']

                vals={
                    'xero_instance_id': instance.id,
                    'xero_payment_id': batch_payment_id,
                    'xero_payment_type': "RECBATCH" if batch.get('Type') == "RECBATCH" else "PAYBATCH",
                }

                payment.write(vals)
                payment.message_post(body=f"Exported Payment  to Xero with ID: {batch_payment_id}")
                self.env['xero.log.vts.line'].sudo().generate_xero_process_line(
                    xero_operation_name='payment',
                    xero_operation_type='export',
                    instance=instance.id,
                    xero_operation_message=f"Payment Successfully Exported to Xero",
                    process_request_message= payload,
                    process_response_message = response_json,
                    log_id=log_id,
                    fault_operation=False
                )
            else:
                res_error = response_json.get('Message', response_json)
                msg=f"Failed to Export Payment to Xero, Response: {res_error}"
                payment.message_post(body=msg)
                self.env['xero.log.vts.line'].sudo().generate_xero_process_line(
                    xero_operation_name='payment',
                    xero_operation_type='export',
                    instance=instance.id,
                    xero_operation_message=msg,
                    process_request_message=payload,
                    process_response_message=response_json,
                    log_id=log_id,
                    fault_operation=True
            )
        except Exception as e:
            payment.message_post(body=f"Exception while exporting Payment to Xero: {str(e)}")
            self.env['xero.log.vts.line'].sudo().generate_xero_process_line(xero_operation_name="payment",
                                                                                xero_operation_type="export",
                                                                                instance=instance.id,
                                                                                xero_operation_message=f"Exception: {str(e)}",
                                                                                process_request_message=payload,
                                                                                process_response_message=str(e),
                                                                                log_id=log_id, fault_operation=True)
        return None

    def delete_xero_payment(self):
        log_id = self.env['xero.log.vts'].sudo().generate_xero_logs(
            xero_operation_name='payment',
            xero_operation_type='delete',
            instance=self.xero_instance_id.id,
            xero_operation_message="Delete Xero Payment",
        )

        instance = self.xero_instance_id

        batch_id = self.xero_payment_id
        request_url = f"{instance.xero_base_url}/BatchPayments/{batch_id}"
        payload = {"Status": "DELETED"}

        try:
            response_json, status_code = self.env['xero.api.vts'].sudo().xero_post_request(
                instance.access_token, instance.tenant_id, request_url, payload
            )

            if status_code in (200, 201):
                self.env['xero.log.vts.line'].sudo().generate_xero_process_line(
                    xero_operation_name='payment',
                    xero_operation_type='delete',
                    instance=instance.id,
                    xero_operation_message=f"Payment Successfully Deleted",
                    process_request_message=payload,
                    process_response_message=response_json,
                    log_id=log_id,
                    fault_operation=False
                )
            else:
                self.env['xero.log.vts.line'].sudo().generate_xero_process_line(
                    xero_operation_name='payment',
                    xero_operation_type='delete',
                    instance=instance.id,
                    xero_operation_message=f"Failed to Delete Payment , Response: {response_json}",
                    process_request_message=payload,
                    process_response_message=response_json,
                    log_id=log_id,
                    fault_operation=True)
                raise ValidationError(f"Failed to delete Xero Batch Payment.\nResponse: {response_json}")

        except Exception as e:
            self.env['xero.log.vts.line'].sudo().generate_xero_process_line(xero_operation_name="payment",
                                                                            xero_operation_type="delete",
                                                                            instance=instance.id,
                                                                            xero_operation_message=f"Exception: {str(e)}",
                                                                            process_request_message=payload,
                                                                            process_response_message=str(e),
                                                                            log_id=log_id, fault_operation=True)

            raise ValidationError(
                f"Cannot delete payment because Xero deletion failed.\n{str(e)}"
            )
    def unlink(self):
        for payment in self:
            if payment.xero_payment_id and payment.xero_instance_id and payment.xero_instance_id.state == 'connected':                payment.delete_xero_payment()
        return super().unlink()


    def export_xero_payment(self,instance):
        for payment in self:
            if len(payment.invoice_ids) == 1:
                self.export_payment_to_xero(payment,instance)
            else:
                self.export_batchpayment_to_xero(payment,instance)
class AccountPaymentRegister(models.TransientModel):
    _inherit = 'account.payment.register'

    def _create_payments(self):
        payments = super(AccountPaymentRegister, self)._create_payments()

        for payment in payments:
            xero_instance = self.env['xero.connect'].sudo().search([
                ('state', '=', 'connected'),
                ('company_id', '=', payment.company_id.id),
            ], limit=1)
            if not xero_instance.auto_payment_export:
                continue
            payment.export_payment_to_xero(payment,xero_instance)

        return payments

