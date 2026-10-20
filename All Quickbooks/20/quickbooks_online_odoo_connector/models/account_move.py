# -*- coding: utf-8 -*-
import requests
import json
import logging
import pprint
from odoo import models, fields
_logger = logging.getLogger(__name__)

TAX_INCLUDED = 'TaxInclusive'
TAX_EXCLUDED = 'TaxExcluded'

class AccountMove(models.Model):
    _inherit = "account.move"

    qbk_invoice_id = fields.Char("QuickBooks Invoice ID", copy=False)
    qbk_bill_id = fields.Char("QuickBooks Bill ID", copy=False)
    error_in_export = fields.Boolean("Error in QuickBooks Export", default=False)
    is_inv_exported = fields.Boolean(string="Is Invoice Exported", default=False, copy=False)
    is_bill_exported = fields.Boolean(string="Is Vendor Bill Exported", default=False, copy=False)
    qck_instance_id = fields.Many2one('quickbooks.connect', string="Quickbook Instance", copy=False)

    def action_qbk_instance_for_move(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Quickbook Instance Wizard',
            'res_model': 'instance.wizard',
            'view_mode': 'form',
            'target': 'new',
        }

    def write(self, vals):
        qbo_trigger_fields = ['name', 'invoice_date', 'partner_id', 'invoice_payment_term_id', 'invoice_line_ids']

        res = super(AccountMove, self).write(vals)
        if not any(f in vals for f in qbo_trigger_fields):
            return res

        for move in self:
            qb = self.env['quickbooks.connect'].sudo().search([('state', '=', 'connected'),('company_id', '=', move.company_id.id)], limit=1)

            if not (qb and qb.qbk_auto_update_invoice_bill):
                continue

            if move.move_type == 'out_invoice':
                prepare_method = '_prepare_qbo_invoice_vals'
                url_endpoint = 'invoice'
                partner_map_model = 'qbo.partner.map.vts'
                partner_field = 'partner_id'
                qbk_id_field = 'qbk_invoice_id'
            elif move.move_type == 'in_invoice':
                prepare_method = '_prepare_qbo_vendor_bill_vals'
                url_endpoint = 'bill'
                partner_map_model = 'qbo.vendor.map.vts'
                partner_field = 'vendor_id'
                qbk_id_field = 'qbk_bill_id'
            else:
                continue

            if not (qb.access_token and qb.realm_id):
                move.message_post(body="QuickBooks Update Failed: Authentication required")
                continue

            qbk_id = getattr(move, qbk_id_field)
            if not qbk_id:
                continue

            partner_map = self.env[partner_map_model].sudo().search([(partner_field, '=', move.partner_id.id),('company_id', '=', move.company_id.id),], limit=1)

            if not partner_map:
                continue

            try:
                headers = {
                    "Authorization": f"Bearer {qb.access_token}",
                    "Content-Type": "application/json",
                    "Accept-Encoding": "identity",
                }

                export_vals = getattr(move, prepare_method)(move, qb, partner_map)

                url_get = f"{qb.quickbook_base_url}/{qb.realm_id}/{url_endpoint}/{qbk_id}"
                response_get = requests.get(url_get, headers=headers)
                response_get.raise_for_status()

                data = qb.convert_xmltodict(response_get.text)
                existing = data.get("IntuitResponse", {}).get(url_endpoint.capitalize(), {}) or {}
                sync_token = existing.get("SyncToken")

                for addr in ("BillAddr", "ShipAddr"):
                    addr_id = existing.get(addr, {}).get("Id")
                    if addr_id:
                        export_vals[addr] = {"Id": addr_id}

                export_vals.update({"Id": qbk_id, "SyncToken": sync_token})
                payload = json.dumps(export_vals)

                url_update = f"{qb.quickbook_base_url}/{qb.realm_id}/{url_endpoint}"
                result = requests.post(url_update, headers=headers, data=payload, timeout=30)

                if result.ok:
                    qb.convert_xmltodict(result.text)
                    move.message_post(body=f"{move.name} updated successfully to QuickBooks")
                else:
                    move.message_post(
                        body=f"{move.move_type.capitalize()} Update Error: "
                             f"{result.status_code} - {result.content.decode(errors='ignore')}")

            except requests.exceptions.RequestException as req_err:
                move.message_post(body=f"Request error while updating {move.name}: {req_err}")
            except Exception as e:
                move.message_post(body=f"Unexpected error while updating {move.name}: {e}")

        return res

    def _prepare_qbo_invoice_vals(self, invoice, quickbook_instance,mapping_partner):

        qbo_invoice_val = {
            "TxnDate": str(invoice.invoice_date),
            "DocNumber": invoice.name,
            "CustomerRef": {
                "value": mapping_partner.quickbook_id,
                "name": mapping_partner.quick_name,
            },
            "Line": [],
            "TotalAmt": float(invoice.amount_total),
            "Balance": float(invoice.amount_residual),
        }
        term_mapping = False
        if invoice.invoice_payment_term_id:
            term_mapping = self.env['qbo.payment.terms.vts'].sudo().search(
                [('payment_id', '=', invoice.invoice_payment_term_id.id), ('quickbook_payment_id', '!=', False),
                 ('quickbook_instance_id', '=', quickbook_instance.id)], limit=1)
        if term_mapping:
            qbo_invoice_val['SalesTermRef'] = {
                "value": str(term_mapping.quickbook_payment_id)
            }

        if quickbook_instance.country_id and quickbook_instance.country_id.code == "US":
            qbo_invoice_val["GlobalTaxCalculation"] = TAX_EXCLUDED
        else:
            qbo_invoice_val["GlobalTaxCalculation"] = TAX_INCLUDED if quickbook_instance.company_include_tax else TAX_EXCLUDED

        line_number = 1
        qbk_tax_code = None

        for line in invoice.invoice_line_ids:
            tax_value = "NON"
            if line.tax_ids:
                if line.tax_ids[0].amount > 0:
                    tax_value = "TAX"
                else:
                    tax_value = "NON"
                mapping_tax = self.env['qbo.taxes.vts'].sudo().search([('tax_id','=',line.tax_ids[0].id),('quickbook_instance_id','=',quickbook_instance.id)],limit=1)
                # if not qbk_tax_code and line.tax_ids[0].qck_taxes_ID:
                if not qbk_tax_code and mapping_tax.quickbook_tax_id:
                    # qbk_tax_code = line.tax_ids[0].qck_taxes_ID
                    qbk_tax_code = mapping_tax.quickbook_tax_id
                    tax_value = "TAX"

            if qbo_invoice_val["GlobalTaxCalculation"] == TAX_INCLUDED:
                line_amount = float(line.price_total)
            else:
                line_amount = float(line.price_subtotal)

            qbo_invoice_val["Line"].append({
                "Description": line.name,
                "Amount": line_amount,
                "DetailType": "SalesItemLineDetail",
                "LineNum": line_number,
                "SalesItemLineDetail": {
                    "Qty": line.quantity,
                    "UnitPrice": float(line.price_unit),
                    "TaxCodeRef": {"value": tax_value}
                }
            })
            line_number += 1

        if qbk_tax_code:
            qbo_invoice_val["TxnTaxDetail"] = {"TxnTaxCodeRef": {"value": qbk_tax_code}}

        return qbo_invoice_val

    # Export Invoice to QuickBooks
    def export_invoice_quickbooks(self, invoice,quickbook_instance):
        if invoice.state != 'posted':
            return

        if invoice.qbk_invoice_id:
            invoice.message_post(body=f"Invoice already exported to QuickBooks with ID {invoice.qbk_invoice_id}.")
            self._cr.commit()
            return

        company = invoice.company_id.id if invoice.company_id else False

        if not quickbook_instance:
            invoice.message_post(body=f"No QuickBooks instance configured for {company} company.")
            self._cr.commit()
            return

        log_id = self.env['quickbooks.log.vts'].sudo().generate_quickbooks_logs(
            quickbooks_operation_name="invoice", quickbooks_operation_type="export",
            instance=quickbook_instance.id, quickbooks_operation_message=f"Starting export for Invoice {invoice.name}")

        inv_partner = invoice.partner_id.parent_id if invoice.partner_id.parent_id else invoice.partner_id
        mapping_partner = self.env['qbo.partner.map.vts'].search([('partner_id','=',inv_partner.id),('quickbook_id','!=',False),('quickbook_instance_id','=',quickbook_instance.id)],limit=1)

        if not mapping_partner:
            qbk_id = inv_partner._export_to_quickbooks(inv_partner, 'customer', 'quickbook_id',quickbook_instance)
            mapping_partner = self.env['qbo.partner.map.vts'].search([('partner_id', '=', inv_partner.id), ('quickbook_id', '=', qbk_id), ('quickbook_instance_id', '=', quickbook_instance.id)],limit=1)

            if mapping_partner:
                msg = f"Customer {inv_partner.name} Created into QuickBooks."
                invoice.message_post(body=msg)
            else:
                msg = qbk_id
                invoice.message_post(body=msg)
                invoice.error_in_export = True
                self.env['quickbooks.log.vts.line'].sudo().generate_quickbooks_process_line(quickbooks_operation_name="invoice",
                    quickbooks_operation_type="export", instance=quickbook_instance.id,
                    quickbooks_operation_message=msg, process_request_message={},
                    process_response_message={}, log_id=log_id, fault_operation=True)
                self._cr.commit()
                return

        qbo_invoice_val = self._prepare_qbo_invoice_vals(invoice, quickbook_instance, mapping_partner)
        try:

            inv_url = f"{quickbook_instance.quickbook_base_url}/{quickbook_instance.realm_id}/invoice"

            response_json, status_code = self.env['quickbooks.api.vts'].sudo().qb_post_request(quickbook_instance.access_token,
                inv_url, qbo_invoice_val)

            if status_code in (200, 201):
                invoice_data = response_json.get("Invoice", {})
                qbk_inv_id = invoice_data.get("Id")
                invoice.qbk_invoice_id = qbk_inv_id
                invoice.qck_instance_id = quickbook_instance.id
                invoice.error_in_export = False
                invoice.is_inv_exported = True
                invoice.message_post(body=f"Exported Invoice {invoice.name} to QuickBooks, ID: {qbk_inv_id}")
                self.env['quickbooks.log.vts.line'].sudo().generate_quickbooks_process_line(
                    quickbooks_operation_name="invoice", quickbooks_operation_type="export",
                    instance=quickbook_instance.id,quickbooks_operation_message=f"Successfully exported invoice {invoice.name}",
                    process_request_message=qbo_invoice_val, process_response_message=response_json,
                    log_id=log_id)
                self._cr.commit()
                return qbk_inv_id
            else:

                msg = f"Failed to export Invoice {invoice.name} to QuickBooks. Response: {response_json}"
                invoice.message_post(body=msg)
                invoice.error_in_export = True
                self.env['quickbooks.log.vts.line'].sudo().generate_quickbooks_process_line(quickbooks_operation_name="invoice",
                    quickbooks_operation_type="export", instance=quickbook_instance.id,
                    quickbooks_operation_message=msg, process_request_message=qbo_invoice_val,
                    process_response_message=response_json, log_id=log_id,
                    fault_operation=True)
                self._cr.commit()
                return None

        except Exception as e:
            invoice.message_post(body=f"Exception while exporting Invoice {invoice.name} to QuickBooks: {str(e)}")
            invoice.error_in_export = True
            self.env['quickbooks.log.vts.line'].sudo().generate_quickbooks_process_line(quickbooks_operation_name="invoice",
                quickbooks_operation_type="export",instance=quickbook_instance.id,quickbooks_operation_message=f"Exception: {str(e)}",
                process_request_message='',process_response_message=str(e),log_id=log_id, fault_operation=True)
            return None

    def _prepare_qbo_vendor_bill_vals(self, bill, quickbook_instance,mapping_vendor, log_id=None):

        qbo_bill_val = {
            "TxnDate": str(bill.invoice_date),
            "DocNumber": bill.name,
            "VendorRef": {
                "value": mapping_vendor.qbk_vendor_id,
                "name": mapping_vendor.qbk_vendor_name,
            },
            "Line": [],
            "TotalAmt": float(bill.amount_total),
            "Balance": float(bill.amount_residual),
        }
        term_mapping = False
        if bill.invoice_payment_term_id:
            term_mapping = self.env['qbo.payment.terms.vts'].sudo().search(
                [('payment_id', '=', bill.invoice_payment_term_id.id), ('quickbook_payment_id', '!=', False),
                 ('quickbook_instance_id', '=', quickbook_instance.id)], limit=1)
        if term_mapping:
            qbo_bill_val['SalesTermRef'] = {
                "value": str(term_mapping.quickbook_payment_id)
            }

        line_number = 1
        for line in bill.invoice_line_ids:
                product_mapping = self.env['qbo.product.vts'].sudo().search([('product_id', '=', line.product_id.product_tmpl_id.id), ('quickbook_product_id', '!=', False),('quickbook_instance_id','=',quickbook_instance.id)],limit=1)
                if not product_mapping:
                    mapped_product = line.product_id.product_tmpl_id.export_product_to_qbk(quickbook_instance)
                    product_mapping = self.env['qbo.product.vts'].sudo().search([('product_id', '=', line.product_id.product_tmpl_id.id),('quickbook_product_id', '=', mapped_product),('quickbook_instance_id','=',quickbook_instance.id)], limit=1)

                    if product_mapping:
                        msg = f"Product {line.product_id.name} Created into QuickBooks."
                        bill.message_post(body=msg)
                    else:
                        msg = mapped_product
                        bill.message_post(body=msg)
                        bill.error_in_export = True
                        self.env['quickbooks.log.vts.line'].sudo().generate_quickbooks_process_line(quickbooks_operation_name="bill",
                            quickbooks_operation_type="export", instance=quickbook_instance.id,
                            quickbooks_operation_message=msg, process_request_message={},
                            process_response_message={}, log_id=log_id, fault_operation=True)
                        return

                qbo_bill_val["Line"].append({
                    "DetailType": "ItemBasedExpenseLineDetail",
                    "Amount": float(line.price_subtotal),
                    "Description": line.name or "",
                    "ItemBasedExpenseLineDetail": {
                        "ItemRef": {
                            "value": product_mapping.quickbook_product_id,
                            "name": line.product_id.name
                        },
                        "Qty": line.quantity,
                        "UnitPrice": float(line.price_unit),
                    }
                })

        return qbo_bill_val

    """Export vendor bill to QuickBooks"""
    def export_vendor_bill_quickbooks(self, bill,quickbook_instance):
        if bill.state != 'posted':
            return

        if bill.qbk_bill_id:
            bill.message_post(body=f"Vendor Bill already exported to QuickBooks with ID {bill.qbk_bill_id}.")
            self._cr.commit()
            return

        company = bill.company_id.id if bill.company_id else False

        if not quickbook_instance:
            bill.message_post(body=f"No QuickBooks instance configured for {company} company.")
            self._cr.commit()
            return

        log_id = self.env['quickbooks.log.vts'].sudo().generate_quickbooks_logs(
            quickbooks_operation_name="bill",
            quickbooks_operation_type="export",
            instance=quickbook_instance.id,
            quickbooks_operation_message=f"Starting export for Vendor Bill {bill.name}"
        )
        bill_partner = bill.partner_id.parent_id if bill.partner_id.parent_id else bill.partner_id
        mapping_vendor = self.env['qbo.vendor.map.vts'].search([('vendor_id','=',bill_partner.id),('qbk_vendor_id','!=',False),('quickbook_instance_id','=',quickbook_instance.id)],limit=1)

        if not mapping_vendor:
            qbk_vendor_id = bill_partner._export_to_quickbooks(bill_partner, 'vendor', 'qbk_vendor_id',quickbook_instance)
            mapping_vendor = self.env['qbo.vendor.map.vts'].search([('vendor_id', '=', bill_partner.id), ('qbk_vendor_id', '=', qbk_vendor_id),('quickbook_instance_id','=',quickbook_instance.id)],limit=1)
            if mapping_vendor:
                msg = f"Vendor {bill.partner_id.name} Created into QuickBooks, ID = {qbk_vendor_id}."
                bill.message_post(body=msg)
                self._cr.commit()
            else:
                msg = qbk_vendor_id
                bill.message_post(body=msg)
                bill.error_in_export = True
                self.env['quickbooks.log.vts.line'].sudo().generate_quickbooks_process_line(quickbooks_operation_name="bill",
                    quickbooks_operation_type="export", instance=quickbook_instance.id,
                    quickbooks_operation_message=msg, process_request_message={},
                    process_response_message={}, log_id=log_id, fault_operation=True)
                self._cr.commit()
                return

        qbo_bill_val = self._prepare_qbo_vendor_bill_vals(bill, quickbook_instance,mapping_vendor, log_id)

        try:

            bill_url = f"{quickbook_instance.quickbook_base_url}/{quickbook_instance.realm_id}/bill"

            response_json, status_code = self.env['quickbooks.api.vts'].sudo().qb_post_request(quickbook_instance.access_token,
                bill_url, qbo_bill_val)

            if status_code in (200, 201):
                bill_data = response_json.get("Bill", {})
                qbk_bill_id = bill_data.get("Id")
                bill.qbk_bill_id = qbk_bill_id
                bill.qck_instance_id = quickbook_instance.id
                bill.error_in_export = False
                bill.is_bill_exported = True
                bill.message_post(body=f"Exported Vendor Bill {bill.name} to QuickBooks, ID: {qbk_bill_id}")
                self.env['quickbooks.log.vts.line'].sudo().generate_quickbooks_process_line(
                    quickbooks_operation_name="bill",
                    quickbooks_operation_type="export",
                    instance=quickbook_instance.id,
                    quickbooks_operation_message=f"Successfully exported Vendor Bill {bill.name}",
                    process_request_message=qbo_bill_val,
                    process_response_message=response_json,
                    log_id=log_id
                )
                self._cr.commit()
                return response_json
            else:
                msg = f"Failed to export Vendor Bill {bill.name} to QuickBooks. Response: {response_json}"
                bill.message_post(body=msg)
                bill.error_in_export = True
                self.env['quickbooks.log.vts.line'].sudo().generate_quickbooks_process_line(quickbooks_operation_name="bill",
                    quickbooks_operation_type="export", instance=quickbook_instance.id,
                    quickbooks_operation_message=msg, process_request_message=qbo_bill_val,
                    process_response_message=response_json, log_id=log_id,
                    fault_operation=True)
                self._cr.commit()
                return None

        except Exception as e:
            bill.message_post(body=f"Exception while exporting Vendor Bill {bill.name} to QuickBooks: {str(e)}")
            bill.error_in_export = True
            self.env['quickbooks.log.vts.line'].sudo().generate_quickbooks_process_line(
                quickbooks_operation_name="bill", quickbooks_operation_type="export",
                instance=quickbook_instance.id, quickbooks_operation_message=f"Exception: {str(e)}",
                process_request_message=qbo_bill_val, process_response_message=str(e),
                log_id=log_id, fault_operation=True)
            self._cr.commit()
            return None

    def _prepare_qbo_credit_note_vals(self, credit_note, quickbook_instance,mapping_partner):

        qbo_credit_val = {
            "TxnDate": str(credit_note.invoice_date),
            "DocNumber": credit_note.name,
            "CustomerRef": {
                "value":  mapping_partner.quickbook_id,
                "name": mapping_partner.quick_name,
            },
            "Line": [],
            "TotalAmt": float(credit_note.amount_total),
        }
        term_mapping = False
        if credit_note.invoice_payment_term_id:
            term_mapping = self.env['qbo.payment.terms.vts'].sudo().search(
                [('payment_id', '=', credit_note.invoice_payment_term_id.id), ('quickbook_payment_id', '!=', False),
                 ('quickbook_instance_id','=',quickbook_instance.id)], limit=1)
        if  term_mapping:
            qbo_credit_val['SalesTermRef'] = {
                "value": str(term_mapping.quickbook_payment_id)
            }

        if quickbook_instance.country_id and quickbook_instance.country_id.code == "US":
            qbo_credit_val["GlobalTaxCalculation"] = TAX_EXCLUDED
        else:
            qbo_credit_val["GlobalTaxCalculation"] = (
                TAX_INCLUDED if quickbook_instance.company_include_tax else TAX_EXCLUDED
            )

        line_number = 1
        qbk_tax_code = None

        for line in credit_note.invoice_line_ids:
            tax_value = "NON"
            if line.tax_ids:
                if line.tax_ids[0].amount > 0:
                    tax_value = "TAX"
                else:
                    tax_value = "NON"
                mapping_tax = self.env['qbo.taxes.vts'].sudo().search([('tax_id','=',line.tax_ids[0].id),('quickbook_instance_id','=',quickbook_instance.id)],limit=1)

                if not qbk_tax_code and mapping_tax.quickbook_tax_id:
                    qbk_tax_code = mapping_tax.quickbook_tax_id
                    tax_value = "TAX"

            if qbo_credit_val["GlobalTaxCalculation"] == TAX_INCLUDED:
                line_amount = float(line.price_total)
            else:
                line_amount = float(line.price_subtotal)

            qbo_credit_val["Line"].append({
                "Description": line.name,
                "Amount": line_amount,
                "DetailType": "SalesItemLineDetail",
                "LineNum": line_number,
                "SalesItemLineDetail": {
                    "Qty": line.quantity,
                    "UnitPrice": float(line.price_unit),
                    "TaxCodeRef": {"value": tax_value}
                }
            })
            line_number += 1
        if qbk_tax_code:
            qbo_credit_val["TxnTaxDetail"] = {"TxnTaxCodeRef": {"value": qbk_tax_code}}

        if credit_note.reversed_entry_id:
            qbo_credit_val["LinkedTxn"] = [{
                "TxnId": credit_note.reversed_entry_id.qbk_invoice_id,
                "TxnType": "Invoice"
            }]

        return qbo_credit_val

    def export_credit_note_quickbooks(self, credit_note,quickbook_instance):
        if credit_note.state != 'posted':
            return

        if credit_note.qbk_invoice_id:
            credit_note.message_post(body=f"Credit note already exported to QuickBooks with ID {credit_note.qbk_invoice_id}.")
            self._cr.commit()
            return
        company = credit_note.company_id.id if credit_note.company_id else False
        if not quickbook_instance:
            credit_note.message_post(body=f"No QuickBooks instance configured for {company} company.")
            self._cr.commit()
            return

        log_id = self.env['quickbooks.log.vts'].sudo().generate_quickbooks_logs(
            quickbooks_operation_name="credit_note", quickbooks_operation_type="export",
            instance=quickbook_instance.id, quickbooks_operation_message=f"Starting export for Credit Note {credit_note.name}"
        )

        credit_partner = credit_note.partner_id.parent_id if credit_note.partner_id.parent_id else credit_note.partner_id
        mapping_partner = self.env['qbo.partner.map.vts'].search([('partner_id', '=', credit_partner.id), ('quickbook_id', '!=', False),('quickbook_instance_id','=',quickbook_instance.id)],limit=1)

        if not mapping_partner:
            qbk_id = credit_partner._export_to_quickbooks(credit_partner, 'customer', 'quickbook_id',quickbook_instance)
            mapping_partner = self.env['qbo.partner.map.vts'].search([('partner_id', '=', credit_partner.id), ('quickbook_id', '=', qbk_id),('quickbook_instance_id','=',quickbook_instance.id)],limit=1)

            if mapping_partner:
                msg = f"Customer {credit_partner.name} Created into QuickBooks."
                credit_note.message_post(body=msg)
                self._cr.commit()
            else:
                msg = qbk_id
                credit_note.message_post(body=msg)
                credit_note.error_in_export = True
                self.env['quickbooks.log.vts.line'].sudo().generate_quickbooks_process_line(quickbooks_operation_name="invoice",
                    quickbooks_operation_type="export", instance=quickbook_instance.id,
                    quickbooks_operation_message=msg, process_request_message={},
                    process_response_message={}, log_id=log_id, fault_operation=True)
                self._cr.commit()
                return

        try:

            qbo_credit_note_val = self._prepare_qbo_credit_note_vals(credit_note, quickbook_instance,mapping_partner)

            credit_url = f"{quickbook_instance.quickbook_base_url}/{quickbook_instance.realm_id}/creditmemo"

            response_json, status_code = self.env['quickbooks.api.vts'].sudo().qb_post_request(quickbook_instance.access_token,
                credit_url, qbo_credit_note_val)

            if status_code in (200, 201):
                invoice_data = response_json.get("CreditMemo", {})
                qbk_credit_note_id = invoice_data.get("Id")
                credit_note.qbk_invoice_id = qbk_credit_note_id
                credit_note.qck_instance_id = quickbook_instance.id
                credit_note.error_in_export = False
                credit_note.is_inv_exported = True
                credit_note.message_post(body=f"Exported credit note {credit_note.name} to QuickBooks, ID: {qbk_credit_note_id}")
                self.env['quickbooks.log.vts.line'].sudo().generate_quickbooks_process_line(
                    quickbooks_operation_name="credit_note", quickbooks_operation_type="export",
                    instance=quickbook_instance.id,
                    quickbooks_operation_message=f"Successfully exported credit note {credit_note.name}",
                    process_request_message=qbo_credit_note_val, process_response_message=response_json,
                    log_id=log_id)
                self._cr.commit()
                return response_json
            else:
                msg = f"Failed to export credit note {credit_note.name} to QuickBooks. Response: {response_json}"
                credit_note.message_post(body=msg)
                credit_note.error_in_export = True
                self.env['quickbooks.log.vts.line'].sudo().generate_quickbooks_process_line(
                    quickbooks_operation_name="credit_note",
                    quickbooks_operation_type="export", instance=quickbook_instance.id,
                    quickbooks_operation_message=msg, process_request_message=qbo_credit_note_val,
                    process_response_message=response_json, log_id=log_id,
                    fault_operation=True)
                self._cr.commit()
                return None
        except Exception as e:
            credit_note.message_post(body=f"Exception while exporting Credit Note {credit_note.name} to QuickBooks: {str(e)}")
            credit_note.error_in_export = True
            self.env['quickbooks.log.vts.line'].sudo().generate_quickbooks_process_line(quickbooks_operation_name="credit_note",quickbooks_operation_type="export",
                instance=quickbook_instance.id,quickbooks_operation_message=f"Exception: {str(e)}",
                process_response_message=str(e),log_id=log_id, fault_operation=True)
        self._cr.commit()
        return None

    def _prepare_qbo_bill_credit_note_vals(self, bill_credit, quickbook_instance, mapping_vendor,log_id=None):

        qbo_bill_credit_val = {
            "TxnDate": str(bill_credit.invoice_date),
            "DocNumber": bill_credit.name,
            "VendorRef": {
                "value": mapping_vendor.qbk_vendor_id,
                "name": mapping_vendor.qbk_vendor_name,
            },
            "Line": [],
            "TotalAmt": float(bill_credit.amount_total),
            "Balance": float(bill_credit.amount_residual),
        }
        term_mapping = False
        if bill_credit.invoice_payment_term_id:
            term_mapping = self.env['qbo.payment.terms.vts'].sudo().search(
                [('payment_id', '=', bill_credit.invoice_payment_term_id.id), ('quickbook_payment_id', '!=', False),
                 ('quickbook_instance_id','=',quickbook_instance.id)], limit=1)
        if term_mapping:
            qbo_bill_credit_val['SalesTermRef'] = {
                "value": str(term_mapping.quickbook_payment_id)
            }

        line_number = 1
        for line in bill_credit.invoice_line_ids:
            product_mapping = self.env['qbo.product.vts'].search([('product_id', '=', line.product_id.product_tmpl_id.id), ('quickbook_product_id', '!=', False),('quickbook_instance_id','=',quickbook_instance.id)], limit=1)
            if not product_mapping:
                mapped_product = line.product_id.product_tmpl_id.export_product_to_qbk(quickbook_instance)
                product_mapping = self.env['qbo.product.vts'].search([('product_id', '=', line.product_id.product_tmpl_id.id),
                     ('quickbook_product_id', '=', mapped_product),('quickbook_instance_id','=',quickbook_instance.id)], limit=1)

                if product_mapping:
                    msg = f"Product {line.product_id.name} Created into QuickBooks."
                    bill_credit.message_post(body=msg)
                else:
                    msg = mapped_product
                    bill_credit.message_post(body=msg)
                    bill_credit.error_in_export = True
                    self.env['quickbooks.log.vts.line'].sudo().generate_quickbooks_process_line(
                        quickbooks_operation_name="bill",
                        quickbooks_operation_type="export", instance=quickbook_instance.id,
                        quickbooks_operation_message=msg, process_request_message={},
                        process_response_message={}, log_id=log_id, fault_operation=True)
                    return

            qbo_bill_credit_val["Line"].append({
                "DetailType": "ItemBasedExpenseLineDetail",
                "Amount": float(line.price_subtotal),
                "Description": line.name or "",
                "ItemBasedExpenseLineDetail": {
                    "ItemRef": {
                        "value": product_mapping.quickbook_product_id,
                        "name": line.product_id.name
                    },
                    "Qty": line.quantity,
                    "UnitPrice": float(line.price_unit),
                }
            })
        if bill_credit.reversed_entry_id:
            qbo_bill_credit_val["LinkedTxn"] = [{
                "TxnId": bill_credit.reversed_entry_id.qbk_bill_id,
                "TxnType": "Bill"
            }]
        return qbo_bill_credit_val

    def export_bill_credit_note_to_quickbooks(self, bill_credit,quickbook_instance):
        if bill_credit.state != 'posted':
            return

        if bill_credit.qbk_bill_id:
            bill_credit.message_post(
                body=f"Bill Refund already exported to QuickBooks with ID {bill_credit.qbk_bill_id}.")
            return

        company = bill_credit.company_id.id if bill_credit.company_id else False

        if not quickbook_instance:
            bill_credit.message_post(body=f"No QuickBooks instance configured for {company} company.")
            return

        log_id = self.env['quickbooks.log.vts'].sudo().generate_quickbooks_logs(
            quickbooks_operation_name="bill_credit_note",
            quickbooks_operation_type="export",
            instance=quickbook_instance.id,
            quickbooks_operation_message=f"Starting export for Bill Refund {bill_credit.name}"
        )
        bill_credit_partner = bill_credit.partner_id.parent_id if bill_credit.partner_id.parent_id else bill_credit.partner_id
        mapping_vendor = self.env['qbo.vendor.map.vts'].search([('vendor_id','=',bill_credit_partner.id),('qbk_vendor_id','!=',False),('quickbook_instance_id','=',quickbook_instance.id)],limit=1)
        if not mapping_vendor:

            qbk_vendor_id = bill_credit_partner._export_to_quickbooks(bill_credit_partner, 'vendor','qbk_vendor_id',quickbook_instance)
            mapping_vendor = self.env['qbo.vendor.map.vts'].search(
                [('vendor_id', '=', bill_credit_partner.id), ('qbk_vendor_id', '=', qbk_vendor_id),
                 ('quickbook_instance_id', '=', quickbook_instance.id)], limit=1)

            if mapping_vendor:
                msg = f"Bill Refund {bill_credit_partner.name} Created into QuickBooks."
                bill_credit.message_post(body=msg)
            else:
                msg = qbk_vendor_id
                bill_credit.message_post(body=msg)
                bill_credit.error_in_export = True
                self.env['quickbooks.log.vts.line'].sudo().generate_quickbooks_process_line(
                    quickbooks_operation_name="bill_credit_note",
                    quickbooks_operation_type="export", instance=quickbook_instance.id,
                    quickbooks_operation_message=msg, process_request_message={},
                    process_response_message={}, log_id=log_id, fault_operation=True)
                return

        qbo_bill_credit_val = self._prepare_qbo_bill_credit_note_vals(bill_credit, quickbook_instance,mapping_vendor, log_id)

        try:

            bill_credit_url = f"{quickbook_instance.quickbook_base_url}/{quickbook_instance.realm_id}/vendorcredit"

            response_json, status_code = self.env['quickbooks.api.vts'].sudo().qb_post_request(
                quickbook_instance.access_token,
                bill_credit_url, qbo_bill_credit_val)

            if status_code in (200, 201):
                bill_data = response_json.get("VendorCredit", {})
                qbk_bill_id = bill_data.get("Id")
                bill_credit.qbk_bill_id = qbk_bill_id
                bill_credit.qck_instance_id = quickbook_instance.id
                bill_credit.error_in_export = False
                bill_credit.is_bill_exported = True
                bill_credit.message_post(
                    body=f"Exported Bill Refund {bill_credit.name} to QuickBooks, ID: {qbk_bill_id}")
                self.env['quickbooks.log.vts.line'].sudo().generate_quickbooks_process_line(
                    quickbooks_operation_name="bill_credit_note",
                    quickbooks_operation_type="export",
                    instance=quickbook_instance.id,
                    quickbooks_operation_message=f"Successfully exported Bill Refund {bill_credit.name}",
                    process_request_message=qbo_bill_credit_val,
                    process_response_message=response_json,
                    log_id=log_id
                )
                return response_json
            else:
                msg = f"Failed to export Bill Credit note {bill_credit.name} to QuickBooks. Response: {response_json}"
                bill_credit.message_post(body=msg)
                bill_credit.error_in_export = True
                self.env['quickbooks.log.vts.line'].sudo().generate_quickbooks_process_line(
                    quickbooks_operation_name="bill_credit_note",
                    quickbooks_operation_type="export", instance=quickbook_instance.id,
                    quickbooks_operation_message=msg, process_request_message=qbo_bill_credit_val,
                    process_response_message=response_json, log_id=log_id,
                    fault_operation=True)
                return None

        except Exception as e:
            bill_credit.message_post(
                body=f"Exception while exporting Vendor Bill {bill_credit.name} to QuickBooks: {str(e)}")
            bill_credit.error_in_export = True
            self.env['quickbooks.log.vts.line'].sudo().generate_quickbooks_process_line(
                quickbooks_operation_name="bill_credit_note", quickbooks_operation_type="export",
                instance=quickbook_instance.id, quickbooks_operation_message=f"Exception: {str(e)}",
                process_request_message=qbo_bill_credit_val, process_response_message=str(e),
                log_id=log_id, fault_operation=True)
            return None

    def export_invoice_bill_to_quickbooks(self,quickbook_instance):
        for move in self:
            if move.move_type == 'out_invoice':
                invoice = self.export_invoice_quickbooks(move,quickbook_instance)
            elif move.move_type == 'in_invoice':
                vendor_bill = self.export_vendor_bill_quickbooks(move,quickbook_instance)
            elif move.move_type == 'out_refund':
                credit_note = self.export_credit_note_quickbooks(move,quickbook_instance)
            elif move.move_type == 'in_refund':
                bill_credit_note = self.export_bill_credit_note_to_quickbooks(move,quickbook_instance)
