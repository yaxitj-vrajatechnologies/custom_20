# -*- coding: utf-8 *-*
from odoo import models, fields
import requests
import json
import pprint
import logging
_logger = logging.getLogger(__name__)

TAX_INCLUDED = 'TaxInclusive'
TAX_EXCLUDED = 'TaxExcluded'


class AccountMove(models.Model):
    
    _inherit = "account.move"

    qck_instance_id = fields.Many2one('quickbooks.connect', string="Quickbook Instance", copy=False)
    qkca_invoice_ID = fields.Char(string="Quickbook Invoice ID",copy=False)
    qck_invoice_doc = fields.Char(string="Quickbook Doc-Number",copy=False)
    is_export_error = fields.Boolean(string="Error in QuickBooks Export", default=False)
    is_qkca_inv_exported = fields.Boolean(string="Is Invoice Exported ", default=False, copy=False)
    is_qkca_bill_exported =fields.Boolean("Is Bill Exported", default=False, copy=False)
    qck_bill_doc = fields.Char(string="Quickbook Bill Doc-Number")
    qkca_bill_ID = fields.Char(string="Quickbook Bill ID",copy=False)

    def action_qkca_instance_for_move(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Quickbook Canada Instance Wizard',
            'res_model': 'quickbook.instance.wizard',
            'view_mode': 'form',
            'target': 'new',
        }

    def write(self, vals):
        if self.env.context.get('skip_update'):
            return super(AccountMove, self).write(vals)

        qbo_trigger_fields = ['name','invoice_date','partner_id','invoice_payment_term_id','invoice_line_ids']

        update_needed = any(field in vals for field in qbo_trigger_fields)

        res = super(AccountMove, self).write(vals)
        if not update_needed:
            return res

        session = requests.Session()

        for move in self:
            company_id = move.company_id.id if move.company_id else False
            quickbook_instance = self.env['quickbooks.connect'].sudo().search([('state', '=', 'connected'), ('company_id', '=', company_id)], limit=1)
            if quickbook_instance and quickbook_instance.qkca_auto_update_invoice_bill:
                if move.move_type == 'out_invoice':
                    qkca_id_field = 'qkca_invoice_ID'
                    prepare_method = '_prepare_qkca_invoice_vals'
                    url_endpoint = 'invoice'
                    partner_map_model = 'qbo.partner.map.vts'
                    partner_field = 'partner_id'
                elif move.move_type == 'in_invoice':
                    qkca_id_field = 'qkca_bill_ID'
                    prepare_method = '_prepare_qkca_bill_vals'
                    url_endpoint = 'bill'
                    partner_map_model = 'qbo.vendor.ca.map.vts'
                    partner_field = 'vendor_id'
                else:
                    continue

                if qkca_id_field and prepare_method and url_endpoint:
                    qbk_id = getattr(move, qkca_id_field)
                    if qbk_id:
                        partner_map = self.env[partner_map_model].sudo().search(
                            [(partner_field, '=', move.partner_id.id),('quickbook_instance_id','=',quickbook_instance.id), ('company_id', '=', move.company_id.id) ],
                            limit=1)

                        if quickbook_instance.access_token and quickbook_instance.realm_id:
                            try:
                                headers = {
                                    "Authorization": f"Bearer {quickbook_instance.access_token}",
                                    "Content-Type": "application/json",
                                    "Accept-Encoding": "identity",
                                }

                                export_vals = getattr(move, prepare_method)(move, quickbook_instance,partner_map)
                                url_base = f"{quickbook_instance.quickbook_base_url}/{quickbook_instance.realm_id}/{url_endpoint}"

                                response_get = session.get(f"{url_base}/{qbk_id}", headers=headers, timeout=15)
                                response_get.raise_for_status()
                                existing_move = quickbook_instance.convert_response_xmltodict(response_get.text)
                                existing_move = existing_move.get("IntuitResponse", {}).get(url_endpoint.capitalize(),
                                                                                            {}) or {}
                                sync_token = existing_move.get("SyncToken")

                                for addr_type in ("BillAddr", "ShipAddr"):
                                    addr_id = existing_move.get(addr_type, {}).get("Id")
                                    if addr_id:
                                        export_vals[addr_type] = {"Id": addr_id}

                                export_vals["Id"] = qbk_id
                                export_vals["SyncToken"] = sync_token

                                parsed_dict = json.dumps(export_vals)
                                _logger.info("Export Update Dict for %s %s: %s", move.move_type, move.name, parsed_dict)

                                result = session.post(url_base, headers=headers, data=parsed_dict, timeout=30)
                                if result.ok:
                                    quickbook_instance.convert_response_xmltodict(result.text)
                                    move.message_post(body=f"{move.name} updated successfully to QuickBooks")
                                else:
                                    msg = f"{result.status_code} - {result.content.decode(errors='ignore')}"
                                    move.message_post(body=f"{move.move_type.capitalize()} Update Error: {msg}")

                            except requests.exceptions.RequestException as req_err:
                                move.message_post(body=f"Request error while updating {move.name}: {str(req_err)}")
                            except Exception as e:
                                move.message_post(body=f"Unexpected error while updating {move.name}: {str(e)}")
                        else:
                            move.message_post(body="QuickBooks Update Failed: Authentication required")

        return res

    def _prepare_qkca_invoice_vals(self, invoice, quickbook_instance, mapping_partner):
        qbo_invoice_val = {
                "TxnDate": str(invoice.invoice_date),
                "DocNumber": invoice.name,
                "CustomerRef": {
                    "value":  mapping_partner.quickbook_id,
                    "name": mapping_partner.quick_name,
                },
                "Line": [],
                "TotalAmt": float(invoice.amount_total),
                "Balance": float(invoice.amount_residual),
            }
        term_mapping=False
        if invoice.invoice_payment_term_id:
            term_mapping = self.env['qbo.payment.terms.vts'].sudo().search(
                [('payment_id', '=', invoice.invoice_payment_term_id.id), ('quickbook_payment_id', '!=', False),
                 ('company_id', '=', invoice.company_id.id)], limit=1)
        if term_mapping:
            qbo_invoice_val['SalesTermRef'] = {"value": str( term_mapping.quickbook_payment_id)}

        if quickbook_instance.country_id and quickbook_instance.country_id.code == "CA":
            qbo_invoice_val["GlobalTaxCalculation"] = "TaxExcluded"
        else:
            qbo_invoice_val["GlobalTaxCalculation"] = TAX_INCLUDED if quickbook_instance.qkca_company_included_tax else TAX_EXCLUDED

        line_number = 1
        qbk_tax_code = None

        for line in invoice.invoice_line_ids:
            tax_value= False
            if line.tax_ids:
                line_mapping = self.env['qbo.taxes.vts'].sudo().search([('tax_id', '=', line.tax_ids[0].id),('quickbook_instance_id', '=', quickbook_instance.id),
                    ('quickbook_tax_id', '!=', False)], limit=1)

                if line_mapping:
                    tax_value = line_mapping.quickbook_tax_id

                    if not qbk_tax_code:
                        qbk_tax_code = tax_value

            if not tax_value:
                tax_value = self.env['qbo.taxes.vts'].sudo().search([('quickbook_instance_id', '=', quickbook_instance.id),('quickbook_tax_id', '!=', False)], limit=1)

            if qbo_invoice_val["GlobalTaxCalculation"] == "TaxIncluded":
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
                    "TaxCodeRef": {"value": tax_value.quickbook_tax_id},
                }
            })
            line_number += 1

        if qbk_tax_code:
            qbo_invoice_val["TxnTaxDetail"] = {"TxnTaxCodeRef": {"value": qbk_tax_code}}

        return qbo_invoice_val

    def export_invoice_to_quickbooks_ca(self, invoice,quickbook_instance):
        if invoice.state != 'posted':
            return

        if invoice.qkca_invoice_ID:
            invoice.message_post(body=f"Invoice already exported to QuickBooks with ID {invoice.qkca_invoice_ID}.")
            return

        company = invoice.company_id.id if invoice.company_id else False
        # quickbook_instance = self.env['quickbooks.connect'].sudo().search([('state', '=', 'connected'), ('company_id', '=', company)], limit=1)

        if not quickbook_instance:
            invoice.message_post(body=f"No QuickBooks instance configured for {company} company.")
            return

        log_id = self.env['quickbooks.log.vts'].sudo().generate_quickbooks_logs(
            quickbooks_operation_name="invoice", quickbooks_operation_type="export",
            instance=quickbook_instance.id, quickbooks_operation_message=f"Starting export for Invoice {invoice.name}")

        inv_partner = invoice.partner_id.parent_id if invoice.partner_id.parent_id else invoice.partner_id
        mapping_partner = self.env['qbo.partner.map.vts'].search(
            [('partner_id', '=', inv_partner.id), ('quickbook_id', '!=', False), ('company_id', '=', company)], limit=1)

        if not mapping_partner:
            quickbook_id = inv_partner.export_to_quickbooks_ca(inv_partner, 'customer', 'quickbook_id',quickbook_instance)
            mapping_partner = self.env['qbo.partner.map.vts'].search([('partner_id', '=', inv_partner.id), ('quickbook_id', '=', quickbook_id), ('quickbook_instance_id', '=', quickbook_instance.id)],limit=1)

            if mapping_partner:
                msg = f"Customer {inv_partner.name} Created into QuickBooks.ID {mapping_partner.quickbook_id}"
                invoice.message_post(body=msg)
            else:
                msg = quickbook_id
                invoice.message_post(body=msg)
                invoice.is_export_error = True
                self.env['quickbooks.log.vts.line'].sudo().generate_quickbooks_process_line(
                    quickbooks_operation_name="invoice",
                    quickbooks_operation_type="export", instance=quickbook_instance.id,
                    quickbooks_operation_message=msg, process_request_message={},
                    process_response_message={}, log_id=log_id, fault_operation=True)
                return
        qbo_invoice_val = self._prepare_qkca_invoice_vals(invoice, quickbook_instance, mapping_partner)
        try:

            inv_url = f"{quickbook_instance.quickbook_base_url}/{quickbook_instance.realm_id}/invoice"

            response_json, status_code = self.env['quickbooks.api.vts'].sudo().qb_post_request(
                quickbook_instance.access_token,
                inv_url, qbo_invoice_val)

            if status_code in (200, 201):
                invoice_data = response_json.get("Invoice", {})
                qbk_inv_id = invoice_data.get("Id")
                invoice.qkca_invoice_ID = qbk_inv_id
                invoice.qck_instance_id = quickbook_instance.id
                invoice.is_export_error = False
                invoice.is_qkca_inv_exported = True
                mapping_vals = {
                    'quickbook_instance_id':quickbook_instance.id,
                    'qbk_invoice_id':qbk_inv_id,
                    'quickbook_invoice_number':invoice.name,
                    'customer_id':mapping_partner.partner_id.id,
                    'invoice_id':self.id,
                    'company_id':company,
                    'qbo_response':pprint.pformat(invoice_data)
                }
                mapping_invoice = self.env['qbo.invoice.map.vts'].create(mapping_vals)
                invoice.message_post(body=f"Exported Invoice {invoice.name} to QuickBooks, ID: {qbk_inv_id}")
                self.env['quickbooks.log.vts.line'].sudo().generate_quickbooks_process_line(
                    quickbooks_operation_name="invoice", quickbooks_operation_type="export",
                    instance=quickbook_instance.id,
                    quickbooks_operation_message=f"Successfully exported invoice {invoice.name}",
                    process_request_message=qbo_invoice_val, process_response_message=response_json,
                    log_id=log_id)
                return response_json
            else:

                msg = f"Failed to export Invoice {invoice.name} to QuickBooks. Response: {response_json}"
                invoice.message_post(body=msg)
                invoice.is_export_error = True
                self.env['quickbooks.log.vts.line'].sudo().generate_quickbooks_process_line(
                    quickbooks_operation_name="invoice",
                    quickbooks_operation_type="export", instance=quickbook_instance.id,
                    quickbooks_operation_message=msg, process_request_message=qbo_invoice_val,
                    process_response_message=response_json, log_id=log_id,
                    fault_operation=True)
                return None

        except Exception as e:
            invoice.message_post(body=f"Exception while exporting Invoice {invoice.name} to QuickBooks: {str(e)}")
            invoice.is_export_error = True
            self.env['quickbooks.log.vts.line'].sudo().generate_quickbooks_process_line(
                quickbooks_operation_name="invoice",
                quickbooks_operation_type="export", instance=quickbook_instance.id,
                quickbooks_operation_message=f"Exception: {str(e)}", process_request_message=qbo_invoice_val,
                process_response_message=str(e),
                log_id=log_id, fault_operation=True)
            return None

    def _prepare_qkca_bill_vals(self, bill, quickbook_instance, mapping_vendor, log_id=None):

        qbo_bill_val = {
            "TxnDate": str(bill.invoice_date),
            "DocNumber": bill.name,
            "VendorRef": {
                "value": mapping_vendor.quickbook_vendor_id,
                "name": mapping_vendor.quickbook_vendor_name,
            },
            "Line": [],
            "TotalAmt": float(bill.amount_total),
            "Balance": float(bill.amount_residual),
        }

        term_mapping = False
        if bill.invoice_payment_term_id:
            term_mapping = self.env['qbo.payment.terms.vts'].sudo().search(
                [('quickbook_payment_id', '!=', False),('payment_id', '=', bill.invoice_payment_term_id.id),('quickbook_payment_id', '!=', quickbook_instance.id)],limit=1)

        if term_mapping:
            qbo_bill_val['SalesTermRef'] = {
                "value": str(term_mapping.quickbook_payment_id)
            }

        if quickbook_instance.country_id and quickbook_instance.country_id.code == "CA":
            qbo_bill_val["GlobalTaxCalculation"] = "TaxExcluded"
        else:
            qbo_bill_val["GlobalTaxCalculation"] = (
                TAX_INCLUDED if quickbook_instance.qkca_company_included_tax else TAX_EXCLUDED)

        line_number = 1
        qbk_tax_code = None
        for line in bill.invoice_line_ids:
            product_mapping = self.env['qbo.product.ca.map.vts'].search([('product_id', '=', line.product_id.product_tmpl_id.id),
                    ('quickbook_product_id', '!=', False),('quickbook_instance_id', '=', quickbook_instance.id)],limit=1)

            if not product_mapping:
                qbk_product_id = line.product_id.product_tmpl_id.export_product_to_qkca(quickbook_instance)
                product_mapping = self.env['qbo.product.ca.map.vts'].search([('product_id', '=', line.product_id.product_tmpl_id.id),
                        ('quickbook_product_id', '=', qbk_product_id),('quickbook_instance_id', '=', quickbook_instance.id)],limit=1)

                if product_mapping:
                    msg = f"Product {line.product_id.name} Created into QuickBooks."
                    bill.message_post(body=msg)
                else:
                    msg = qbk_product_id
                    bill.message_post(body=msg)
                    bill.is_export_error = True
                    self.env['quickbooks.log.vts.line'].sudo().generate_quickbooks_process_line(
                        quickbooks_operation_name="bill",quickbooks_operation_type="export",instance=quickbook_instance.id,
                        quickbooks_operation_message=msg,process_request_message={},process_response_message={},log_id=log_id,fault_operation=True                    )
                    return

            tax_value = False
            if line.tax_ids:
                line_mapping = self.env['qbo.taxes.vts'].sudo().search([('tax_id', '=', line.tax_ids[0].id),('quickbook_instance_id', '=', quickbook_instance.id),
                        ('quickbook_tax_id', '!=', False)],limit=1)

                if line_mapping:
                    tax_value = line_mapping.quickbook_tax_id
                    if not qbk_tax_code:
                        qbk_tax_code = tax_value

            if not tax_value:
                tax_value = self.env['qbo.taxes.vts'].sudo().search([('quickbook_instance_id', '=', quickbook_instance.id),('quickbook_tax_id', '!=', False)],limit=1).quickbook_tax_id

            if qbo_bill_val["GlobalTaxCalculation"] == "TaxIncluded":
                line_amount = float(line.price_total)
            else:
                line_amount = float(line.price_subtotal)

            line_vals = {
                "DetailType": "ItemBasedExpenseLineDetail",
                "Amount": line_amount,
                "Description": line.name or "",
                "LineNum": line_number,
                "ItemBasedExpenseLineDetail": {
                    "ItemRef": {
                        "value": product_mapping.quickbook_product_id,
                        "name": product_mapping.quickbook_product_name
                    },
                    "Qty": line.quantity,
                    "UnitPrice": float(line.price_unit),
                    "TaxCodeRef": {"value": tax_value},
              }
            }

            qbo_bill_val["Line"].append(line_vals)
            line_number += 1

        if qbk_tax_code:
            qbo_bill_val["TxnTaxDetail"] = {
                "TxnTaxCodeRef": {"value": qbk_tax_code}}

        return qbo_bill_val

    def export_bill_to_quickbook_ca(self, bill,quickbook_instance):
        if bill.state != 'posted':
            return

        if bill.qkca_bill_ID:
            bill.message_post(body=f"Vendor Bill already exported to QuickBooks with ID {bill.qkca_bill_ID}.")
            return

        company = bill.company_id.id if bill.company_id else False

        if not quickbook_instance:
            bill.message_post(body=f"No QuickBooks instance configured for {company} company.")
            return

        log_id = self.env['quickbooks.log.vts'].sudo().generate_quickbooks_logs(
            quickbooks_operation_name="bill",quickbooks_operation_type="export",
            instance=quickbook_instance.id,quickbooks_operation_message=f"Starting export for Vendor Bill {bill.name}")

        bill_partner = bill.partner_id.parent_id if bill.partner_id.parent_id else bill.partner_id
        mapping_vendor = self.env['qbo.vendor.ca.map.vts'].search([('vendor_id','=',bill_partner.id),('quickbook_vendor_id','!=',False),('quickbook_instance_id','=',quickbook_instance.id)],limit=1)

        if not mapping_vendor:
            qkca_vendor_ID = bill_partner.export_to_quickbooks_ca(bill_partner, 'vendor', 'quickbook_vendor_id',quickbook_instance)
            mapping_vendor = self.env['qbo.vendor.ca.map.vts'].search([('vendor_id', '=', bill_partner.id), ('quickbook_vendor_id', '=', qkca_vendor_ID),('quickbook_instance_id','=',quickbook_instance.id)], limit=1)

            if mapping_vendor:
                msg = f"Vendor {bill.partner_id.name} Created into QuickBooks."
                bill.message_post(body=msg)
            else:
                msg = qkca_vendor_ID
                bill.message_post(body=msg)
                bill.is_export_error = True
                self.env['quickbooks.log.vts.line'].sudo().generate_quickbooks_process_line(
                    quickbooks_operation_name="bill",
                    quickbooks_operation_type="export", instance=quickbook_instance.id,
                    quickbooks_operation_message=msg, process_request_message={},
                    process_response_message={}, log_id=log_id, fault_operation=True)
                return

        qbo_bill_val = self._prepare_qkca_bill_vals(bill, quickbook_instance, mapping_vendor, log_id)

        try:

            bill_url = f"{quickbook_instance.quickbook_base_url}/{quickbook_instance.realm_id}/bill"

            response_json, status_code = self.env['quickbooks.api.vts'].sudo().qb_post_request(
                quickbook_instance.access_token,
                bill_url, qbo_bill_val)

            if status_code in (200, 201):
                bill_data = response_json.get("Bill", {})
                qkca_bill_ID = bill_data.get("Id")
                bill.qkca_bill_ID = qkca_bill_ID
                bill.qck_instance_id = quickbook_instance.id
                bill.is_export_error = False
                bill.is_qkca_bill_exported = True
                mapping_vals = {
                    'quickbook_instance_id':quickbook_instance.id,
                    'quickbook_bill_id':qkca_bill_ID,
                    'partner_id':mapping_vendor.vendor_id.id,
                    'quickbook_bill_number':bill.name,
                    'bill_id':self.id,
                    'company_id':company,
                    'qbo_response':pprint.pformat(bill_data)
                }
                mapping_bill = self.env['qbo.bill.ca.map.vts'].create(mapping_vals)
                bill.message_post(body=f"Exported Vendor Bill {bill.name} to QuickBooks, ID: {qkca_bill_ID}")
                self.env['quickbooks.log.vts.line'].sudo().generate_quickbooks_process_line(
                    quickbooks_operation_name="bill",quickbooks_operation_type="export",instance=quickbook_instance.id,quickbooks_operation_message=f"Successfully exported Vendor Bill {bill.name}",
                    process_request_message=qbo_bill_val,process_response_message=response_json,log_id=log_id)
                return response_json
            else:
                msg = f"Failed to export Vendor Bill {bill.name} to QuickBooks. Response: {response_json}"
                bill.message_post(body=msg)
                bill.is_export_error = True
                self.env['quickbooks.log.vts.line'].sudo().generate_quickbooks_process_line(
                    quickbooks_operation_name="bill",quickbooks_operation_type="export", instance=quickbook_instance.id,
                    quickbooks_operation_message=msg, process_request_message=qbo_bill_val,
                    process_response_message=response_json, log_id=log_id,fault_operation=True)
                return None

        except Exception as e:
            bill.message_post(body=f"Exception while exporting Vendor Bill {bill.name} to QuickBooks: {str(e)}")
            bill.is_export_error = True
            self.env['quickbooks.log.vts.line'].sudo().generate_quickbooks_process_line(
                quickbooks_operation_name="bill", quickbooks_operation_type="export",
                instance=quickbook_instance.id, quickbooks_operation_message=f"Exception: {str(e)}",
                process_request_message=qbo_bill_val, process_response_message=str(e),
                log_id=log_id, fault_operation=True)
            return None


    def _prepare_qbo_credit_note_vals(self, credit_note, quickbook_instance,mapping_partner):


        qbo_credit_val = {
            "TxnDate": str(credit_note.invoice_date),
            "DocNumber": credit_note.name,
            "CustomerRef": {
                "value": mapping_partner.quickbook_id,
                "name": mapping_partner.quick_name,
            },
            "Line": [],
            "TotalAmt": float(credit_note.amount_total),
        }
        term_mapping = False
        if credit_note.invoice_payment_term_id:
            term_mapping = self.env['qbo.payment.terms.vts'].sudo().search(
                [('payment_id', '=', credit_note.invoice_payment_term_id.id), ('quickbook_payment_id', '!=', False),
                 ('company_id', '=', credit_note.company_id.id)], limit=1)
        if term_mapping:
            qbo_credit_val['SalesTermRef'] = {
                "value": str( term_mapping.quickbook_payment_id)
            }

        if quickbook_instance.country_id and quickbook_instance.country_id.code == "CA":
            qbo_credit_val["GlobalTaxCalculation"] = "TaxExcluded"
        else:
            qbo_credit_val[
                "GlobalTaxCalculation"] = TAX_INCLUDED if quickbook_instance.qkca_company_included_tax else TAX_EXCLUDED

        line_number = 1
        qbk_tax_code = None

        for line in credit_note.invoice_line_ids:
            tax_value = False
            if line.tax_ids:
                line_mapping = self.env['qbo.taxes.vts'].sudo().search(
                    [('tax_id', '=', line.tax_ids[0].id), ('quickbook_instance_id', '=', quickbook_instance.id),
                     ('quickbook_tax_id', '!=', False)], limit=1)

                if line_mapping:
                    tax_value = line_mapping.quickbook_tax_id
                    if not qbk_tax_code:
                        qbk_tax_code = tax_value

            if not tax_value:
                tax_value = self.env['qbo.taxes.vts'].sudo().search(
                    [('quickbook_instance_id', '=', quickbook_instance.id), ('quickbook_tax_id', '!=', False)],
                    limit=1).quickbook_tax_id

            if qbo_credit_val["GlobalTaxCalculation"] == "TaxIncluded":
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
                    "TaxCodeRef": {"value": tax_value},
                }
            })
            line_number += 1

        if qbk_tax_code:
            qbo_credit_val["TxnTaxDetail"] = {"TxnTaxCodeRef": {"value": qbk_tax_code}}
        if credit_note.reversed_entry_id:
            qbo_credit_val["LinkedTxn"] = [{
                "TxnId": credit_note.reversed_entry_id.qkca_invoice_ID,
                "TxnType": "Invoice"
            }]

        return qbo_credit_val

    def export_credit_note_quickbooks_ca(self, credit_note,quickbook_instance):
        if credit_note.state != 'posted':
            return

        if credit_note.qkca_invoice_ID:
            credit_note.message_post(body=f"Credit note already exported to QuickBooks with ID {credit_note.qkca_invoice_ID}.")
            return
        company = credit_note.company_id.id if credit_note.company_id else False

        if not quickbook_instance:
            credit_note.message_post(body=f"No QuickBooks instance configured for {company} company.")
            return

        log_id = self.env['quickbooks.log.vts'].sudo().generate_quickbooks_logs(
            quickbooks_operation_name="credit_note", quickbooks_operation_type="export",
            instance=quickbook_instance.id, quickbooks_operation_message=f"Starting export for Credit Note {credit_note.name}")

        credit_partner = credit_note.partner_id.parent_id if credit_note.partner_id.parent_id else credit_note.partner_id
        mapping_partner = self.env['qbo.partner.map.vts'].search(
            [('partner_id', '=', credit_partner.id), ('quickbook_id', '!=', False),('company_id','=',company)],limit=1)

        if not mapping_partner:
            quickbook_id = credit_partner.export_to_quickbooks_ca(credit_partner, 'customer', 'quickbook_id',quickbook_instance)
            mapping_partner = self.env['qbo.partner.map.vts'].search([('partner_id', '=', credit_partner.id), ('quickbook_id', '=', quickbook_id), ('company_id', '=', company)],limit=1)

            if mapping_partner:
                msg = f"Customer {credit_partner.name} Created into QuickBooks."
                credit_note.message_post(body=msg)
            else:
                msg = quickbook_id
                credit_note.message_post(body=msg)
                credit_note.is_export_error = True
                self.env['quickbooks.log.vts.line'].sudo().generate_quickbooks_process_line(quickbooks_operation_name="invoice",
                    quickbooks_operation_type="export", instance=quickbook_instance.id,
                    quickbooks_operation_message=msg, process_request_message={},
                    process_response_message={}, log_id=log_id, fault_operation=True)
                return

        qbo_credit_note_val = self._prepare_qbo_credit_note_vals(credit_note, quickbook_instance, mapping_partner)

        try:

            credit_url = f"{quickbook_instance.quickbook_base_url}/{quickbook_instance.realm_id}/creditmemo"

            response_json, status_code = self.env['quickbooks.api.vts'].sudo().qb_post_request(quickbook_instance.access_token,
                credit_url, qbo_credit_note_val)

            if status_code in (200, 201):
                invoice_data = response_json.get("CreditMemo", {})
                qbk_credit_note_id = invoice_data.get("Id")
                credit_note.qkca_invoice_ID = qbk_credit_note_id
                credit_note.qck_instance_id = quickbook_instance.id
                credit_note.is_export_error = False
                credit_note.is_qkca_inv_exported = True
                credit_note.message_post(body=f"Exported credit note {credit_note.name} to QuickBooks, ID: {qbk_credit_note_id}")
                self.env['quickbooks.log.vts.line'].sudo().generate_quickbooks_process_line(
                    quickbooks_operation_name="credit_note", quickbooks_operation_type="export",
                    instance=quickbook_instance.id,quickbooks_operation_message=f"Successfully exported credit note {credit_note.name}",
                    process_request_message=qbo_credit_note_val, process_response_message=response_json,log_id=log_id)
                return response_json
            else:
                msg = f"Failed to export credit note {credit_note.name} to QuickBooks. Response: {response_json}"
                credit_note.message_post(body=msg)
                credit_note.is_export_error = True
                self.env['quickbooks.log.vts.line'].sudo().generate_quickbooks_process_line(
                    quickbooks_operation_name="credit_note",
                    quickbooks_operation_type="export", instance=quickbook_instance.id,
                    quickbooks_operation_message=msg, process_request_message=qbo_credit_note_val,
                    process_response_message=response_json, log_id=log_id,
                    fault_operation=True)
                return None
        except Exception as e:
            credit_note.message_post(body=f"Exception while exporting Credit Note {credit_note.name} to QuickBooks: {str(e)}")
            credit_note.is_export_error = True
            self.env['quickbooks.log.vts.line'].sudo().generate_quickbooks_process_line(quickbooks_operation_name="credit_note",quickbooks_operation_type="export",
                instance=quickbook_instance.id,quickbooks_operation_message=f"Exception: {str(e)}",process_request_message=qbo_credit_note_val,
                process_response_message=str(e),log_id=log_id, fault_operation=True,)
        return None

    """Method for creating a bill credit note vals for exporting """
    def _prepare_qbo_bill_credit_note_vals(self, bill_credit, quickbook_instance, mapping_vendor,log_id=None):


        qbo_bill_credit_val = {
            "TxnDate": str(bill_credit.invoice_date),
            "DocNumber": bill_credit.name,
            "VendorRef": {
                "value":  mapping_vendor.quickbook_vendor_id,
                "name": mapping_vendor.quickbook_vendor_name,
            },
            "Line": [],
            "TotalAmt": float(bill_credit.amount_total),
        }

        term_mapping = False
        if bill_credit.invoice_payment_term_id:
            term_mapping = self.env['qbo.payment.terms.vts'].sudo().search(
                [('payment_id', '=', bill_credit.invoice_payment_term_id.id), ('quickbook_payment_id', '!=', False),
                 ('company_id', '=', bill_credit.company_id.id)], limit=1)
        if term_mapping:
            qbo_bill_credit_val['SalesTermRef'] = {
                "value": str(term_mapping.quickbook_payment_id)
            }
        if quickbook_instance.country_id and quickbook_instance.country_id.code == "CA":
            qbo_bill_credit_val["GlobalTaxCalculation"] = "TaxExcluded"
        else:
            qbo_bill_credit_val[
                "GlobalTaxCalculation"] = TAX_INCLUDED if quickbook_instance.qkca_company_included_tax else TAX_EXCLUDED

        line_number = 1
        qbk_tax_code = None
        for line in bill_credit.invoice_line_ids:
            product_mapping = self.env['qbo.product.ca.map.vts'].search([('product_id', '=', line.product_id.product_tmpl_id.id), ('quickbook_product_id', '!=', False),('quickbook_instance_id','=',quickbook_instance.id)], limit=1)

            if not product_mapping:
                qbk_product_id = line.product_id.product_tmpl_id.export_product_to_qkca(quickbook_instance)
                product_mapping = self.env['qbo.product.ca.map.vts'].search(
                    [('product_id', '=', line.product_id.product_tmpl_id.id), ('quickbook_product_id', '=', qbk_product_id),('quickbook_instance_id', '=', quickbook_instance.id)], limit=1)

                if product_mapping:
                    msg = f"Product {line.product_id.name} Created into QuickBooks."
                    bill_credit.message_post(body=msg)
                else:
                    msg = qbk_product_id
                    bill_credit.message_post(body=msg)
                    bill_credit.is_export_error = True
                    self.env['quickbooks.log.vts.line'].sudo().generate_quickbooks_process_line(
                        quickbooks_operation_name="bill",
                        quickbooks_operation_type="export", instance=quickbook_instance.id,
                        quickbooks_operation_message=msg, process_request_message={},
                        process_response_message={}, log_id=log_id, fault_operation=True)
                    return

            tax_value = False
            if line.tax_ids:
                line_mapping = self.env['qbo.taxes.vts'].sudo().search(
                    [('tax_id', '=', line.tax_ids[0].id), ('quickbook_instance_id', '=', quickbook_instance.id),
                     ('quickbook_tax_id', '!=', False)], limit=1)

                if line_mapping:
                    tax_value = line_mapping.quickbook_tax_id
                    if not qbk_tax_code:
                        qbk_tax_code = tax_value

            if not tax_value:
                tax_value = self.env['qbo.taxes.vts'].sudo().search(
                    [('quickbook_instance_id', '=', quickbook_instance.id), ('quickbook_tax_id', '!=', False)],
                    limit=1).quickbook_tax_id

            if qbo_bill_credit_val["GlobalTaxCalculation"] == "TaxIncluded":
                line_amount = float(line.price_total)
            else:
                line_amount = float(line.price_subtotal)

            line_vals = {
                "DetailType": "ItemBasedExpenseLineDetail",
                "Amount": line_amount,
                "Description": line.name or "",
                "LineNum": line_number,
                "ItemBasedExpenseLineDetail": {
                    "ItemRef": {
                        "value": product_mapping.quickbook_product_id,
                        "name": product_mapping.quickbook_product_name
                    },
                    "Qty": line.quantity,
                    "UnitPrice": float(line.price_unit),
                    "TaxCodeRef": {"value": tax_value},
                }
            }

            qbo_bill_credit_val["Line"].append(line_vals)
            line_number += 1

        if qbk_tax_code:
            qbo_bill_credit_val["TxnTaxDetail"] = {"TxnTaxCodeRef": {"value": qbk_tax_code}}

        if bill_credit.reversed_entry_id:
            qbo_bill_credit_val["LinkedTxn"] = [{
                "TxnId": bill_credit.reversed_entry_id.qkca_bill_ID,
                "TxnType": "Bill"
            }]
        return qbo_bill_credit_val

    """ Method to Export Bill (Vendor) Credit Note to Quickbooks"""
    def export_bill_credit_note_to_quickbooks_ca(self, bill_credit,quickbook_instance):
        if bill_credit.state != 'posted':
            return

        if bill_credit.qkca_bill_ID:
            bill_credit.message_post(
                body=f"Bill Refund already exported to QuickBooks with ID {bill_credit.qkca_bill_ID}.")
            return

        company = bill_credit.company_id.id if bill_credit.company_id else False
        # quickbook_instance = self.env['quickbooks.connect'].sudo().search(
        #     [('state', '=', 'connected'), ('company_id', '=', company)], limit=1)

        if not quickbook_instance:
            bill_credit.message_post(body=f"No QuickBooks instance configured for {company} company.")
            return

        log_id = self.env['quickbooks.log.vts'].sudo().generate_quickbooks_logs(
            quickbooks_operation_name="bill_credit_note",
            quickbooks_operation_type="export",instance=quickbook_instance.id,
            quickbooks_operation_message=f"Starting export for Bill Refund {bill_credit.name}"
        )
        bill_credit_partner = bill_credit.partner_id.parent_id if bill_credit.partner_id.parent_id else bill_credit.partner_id

        mapping_vendor = self.env['qbo.vendor.ca.map.vts'].search([('vendor_id','=',bill_credit_partner.id),('quickbook_vendor_id','!=',False),('company_id','=',company)],limit=1)
        if not mapping_vendor:
            qkca_vendor_ID = bill_credit_partner.export_to_quickbooks_ca(bill_credit_partner, 'vendor','quickbook_vendor_id',quickbook_instance)
            mapping_vendor = self.env['qbo.vendor.ca.map.vts'].search([('vendor_id', '=', bill_credit_partner.id), ('quickbook_vendor_id', '=', qkca_vendor_ID),('company_id', '=', company)], limit=1)

            if mapping_vendor:
                msg = f"Bill Refund {bill_credit_partner.name} Created into QuickBooks."
                bill_credit.message_post(body=msg)
            else:
                msg = qkca_vendor_ID
                bill_credit.message_post(body=msg)
                bill_credit.is_export_error = True
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
                bill_credit.qkca_bill_ID = qbk_bill_id
                bill_credit.qck_instance_id = quickbook_instance.id
                bill_credit.is_export_error = False
                bill_credit.is_qkca_bill_exported = True
                bill_credit.message_post(
                    body=f"Exported Bill Refund {bill_credit.name} to QuickBooks, ID: {qbk_bill_id}")
                self.env['quickbooks.log.vts.line'].sudo().generate_quickbooks_process_line(
                    quickbooks_operation_name="bill_credit_note",quickbooks_operation_type="export",instance=quickbook_instance.id,
                    quickbooks_operation_message=f"Successfully exported Bill Refund {bill_credit.name}",
                    process_request_message=qbo_bill_credit_val,process_response_message=response_json,log_id=log_id)
                return response_json
            else:
                msg = f"Failed to export Bill Credit note {bill_credit.name} to QuickBooks. Response: {response_json}"
                bill_credit.message_post(body=msg)
                bill_credit.is_export_error = True
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
            bill_credit.is_export_error = True
            self.env['quickbooks.log.vts.line'].sudo().generate_quickbooks_process_line(
                quickbooks_operation_name="bill_credit_note", quickbooks_operation_type="export",
                instance=quickbook_instance.id, quickbooks_operation_message=f"Exception: {str(e)}",
                process_request_message=qbo_bill_credit_val, process_response_message=str(e),
                log_id=log_id, fault_operation=True)
            return None


    def export_invoice_and_bill_to_quickbooks_ca(self,quickbook_instance):
        for move in self:
            if move.move_type == 'out_invoice':
                invoice = self.export_invoice_to_quickbooks_ca(move,quickbook_instance)
            elif move.move_type == 'in_invoice':
                vendor_bill = self.export_bill_to_quickbook_ca(move,quickbook_instance)
            elif move.move_type == 'out_refund':
                credit_note = self.export_credit_note_quickbooks_ca(move,quickbook_instance)
            elif move.move_type == 'in_refund':
                bill_credit_note = self.export_bill_credit_note_to_quickbooks_ca(move,quickbook_instance)
