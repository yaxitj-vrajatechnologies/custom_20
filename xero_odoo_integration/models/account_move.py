# -*- coding: utf-8 *-*
import json
import requests

from odoo import models, fields


class AccountMove(models.Model):
    _inherit = "account.move"

    xero_instance_id = fields.Many2one('xero.connect', string="Xero Instance", copy=False)
    # xero_invoice_id = fields.Char(string="Xero Invoice Id")
    xero_ref_id = fields.Char(string="Xero Move ID",
                              help="This Field Store all the id of xero Invoice/Bill/Credit note/Refund", copy=False)
    xr_invoice_num = fields.Char(string="Xero Invoice Number", copy=False)
    xr_move_type = fields.Selection(
        [('ACCREC', 'Invoice'), ('ACCPAY', 'Bill'), ('ACCRECCREDIT', 'Credit Notes'), ('ACCPAYCREDIT', 'Refund')],
        string="Xero Move Type")
    # xero_bill_id = fields.Char(string="Xero Bill Id")
    # xero_credit_note_id = fields.Char(string="Xero Credit Note Id")
    error_in_export = fields.Boolean("Error in Xero Export", default=False, copy=False)
    is_inv_exported = fields.Boolean(string="Is Invoice Exported", default=False, copy=False)
    is_bill_exported = fields.Boolean(string="Is Vendor Bill Exported", default=False, copy=False)
    is_skip_transaction = fields.Boolean(string="Skip Invoice",
                                         help="Enable this flag if you want to skip exporting this invoice", copy=False)
    is_consolidated_invoice = fields.Boolean(string="Is Consolidated Invoices",
                                             help=" This Flag becomes True if the Invoice is exported as Consolidated Invoice",
                                             copy=False)

    def action_post(self):
        res = super().action_post()
        if self.env.context.get('move_import_create'):
            return res

        xero_instance = self.env['xero.connect'].sudo().search([('company_id', '=', self.company_id.id),
                                                                ('auto_invoice_bill_export', '=', True),
                                                                ('state', '=', 'connected'), ], limit=1)
        if not xero_instance:
            return res

        for move in self:
            if move.move_type in ('out_invoice', 'in_invoice'):
                move.export_invoice_to_xero(move, xero_instance)
            if move.move_type in ('out_refund', 'in_refund'):
                move.export_credit_note_to_xero(move, xero_instance)
        return res

    def write(self, vals):
        # if self.env.context.get('skip_update'):
        #     return super(AccountMove, self).write(vals)

        xero_trigger_fields = ['name', 'invoice_date', 'partner_id', 'invoice_line_ids','state']

        update_needed = any(field in vals for field in xero_trigger_fields)

        res = super(AccountMove, self).write(vals)
        if not update_needed:
            return res

        session = requests.Session()

        for move in self:
            company_id = move.company_id.id if move.company_id else False
            xero_instance = self.env['xero.connect'].sudo().search(
                [('state', '=', 'connected'), ('company_id', '=', company_id)], limit=1)

            if xero_instance and xero_instance.auto_update_invoice_bill:
                # if move.move_type == 'out_invoice':
                #     xero_id_field = 'xero_ref_id'
                # elif move.move_type == 'in_invoice':
                #     xero_id_field = 'xero_ref_id'
                # elif move.move_type == 'out_refund':
                #     xero_id_field = 'xero_ref_id'
                # elif move.move_type == 'in_refund':
                #     xero_id_field = 'xero_ref_id'
                if move.move_type in ('out_invoice', 'in_invoice', 'out_refund', 'in_refund'):
                    xero_id = getattr(move, 'xero_ref_id', False)
                    if not xero_id:
                        continue

                if not xero_instance.access_token or not xero_instance.tenant_id:
                    move.message_post(body="Xero Update Failed: Authentication required")
                    continue

                partner_map = self.env['xero.partner.map'].sudo().search([
                    ('partner_id', '=', move.partner_id.id), ('xero_instance_id', '=', xero_instance.id), ], limit=1)

                try:
                    headers = self.env['xero.api.vts'].sudo().get_xero_header(xero_instance.access_token,
                                                                              xero_instance.tenant_id)
                    endpoint = 'Invoices' if 'invoice' in move.move_type else 'CreditNotes'

                    payload_method = {
                        'invoice': move.prepare_invoice_payload,
                        'refund': move.prepare_credit_note_payload,
                    }

                    export_vals = payload_method['refund' if 'refund' in move.move_type else 'invoice'](move,
                                                                                                        partner_map,
                                                                                                        xero_instance)

                    url = f"{xero_instance.xero_base_url}/{endpoint}/{xero_id}"

                    response_get = session.get(url, headers=headers, timeout=15)

                    existing_data = response_get.json().get(f"{endpoint}", [])
                    existing_invoice = existing_data[0] if existing_data else {}

                    if not existing_invoice:
                        move.message_post(body="Xero Update Failed: Invoice not found in Xero")
                        continue

                    if endpoint == 'Invoices':
                        export_vals['InvoiceID'] = xero_id
                    else:
                        export_vals['CreditNoteID'] = xero_id

                    payload = json.dumps({endpoint: [export_vals]})
                    response = session.post(url, headers=headers, data=payload, timeout=30)

                    if response.ok:
                        response_data = response.json()
                        if response_data.get("Errors"):
                            move.message_post(body=f"Xero Update Error: {response_data.get('Errors')}")
                        else:
                            move.message_post(body=f" {move.name} updated successfully to Xero")
                    else:
                        msg = f"{response.status_code} - {response.text}"
                        move.message_post(body=f"{move.move_type.capitalize()} Update Error: {msg}")
                except requests.exceptions.RequestException as req_err:
                    move.message_post(body=f"Request error while updating {move.name}: {str(req_err)}")
                except Exception as e:
                    move.message_post(body=f"Unexpected error while updating {move.name}: {str(e)}")
        return res

    def action_xero_instance_for_move(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Xero Instance Wizard',
            'res_model': 'xero.instance.wizard',
            'view_mode': 'form',
            'target': 'new',
        }

    def prepare_invoice_payload(self, invoice, partner_map, xero_instance):
        line_items = []
        tax_included = False
        for line in invoice.invoice_line_ids.filtered(
                lambda l: l.display_type not in ('line_section', 'line_note')):
            line_tax_included = any(tax.price_include for tax in line.tax_ids)
            tax_included = tax_included or line_tax_included
            tax_amount = round(line.price_total - line.price_subtotal, 2)
            if line_tax_included:
                unit_amount = (line.price_total - tax_amount) / line.quantity if line.quantity else 0.0
            else:
                unit_amount = line.price_unit
            line_item = {
                "Description":line.name or line.product_id.name,
                "Quantity": line.quantity,
                "UnitAmount": line.currency_id.round(unit_amount),
                # "ItemCode":line.product_id.default_code,
                "LineAmount":line.price_subtotal,
            }
            if invoice.move_type == 'out_invoice' and line.discount:
                line_item["DiscountRate"] = float(line.discount)
            line_item["TaxAmount"] = line.currency_id.round(tax_amount)
            account_id = line.account_id
            account_mapping = self.env['xero.account.map'].sudo().search(
                [('account_id', '=', account_id.id), ('xero_instance_id', '=', xero_instance.id)], limit=1)
            if not account_mapping:
                account_mapping = account_id.export_account_to_xero(account_id, xero_instance)
                if account_mapping:
                    invoice.message_post(
                        body=f"Charts Of Account Successfully exported with ID : {account_mapping.xero_account_id}")
                else:
                    msg = "Failed to export charts of account to xero"
                    log_id = self.env['xero.log.vts'].sudo().generate_xero_logs(
                        xero_operation_name="account", xero_operation_type="export",
                        instance=xero_instance.id,
                        xero_operation_message=f"failed to export charts of account tp xero.")
                    self.env['xero.log.vts.line'].sudo().generate_xero_process_line(xero_operation_name="account",
                                                                                    xero_operation_type="export",
                                                                                    instance=xero_instance.id,
                                                                                    xero_operation_message=msg,
                                                                                    log_id=log_id, fault_operation=True)
                    return
            line_item['AccountCode'] = account_mapping.xero_account_code

            analytic_distribution = line.analytic_distribution or {}
            analytic_ids = set()
            tracking_vals = []

            for key in analytic_distribution.keys():
                ids = [int(x) for x in key.split(',')]
                analytic_ids.update(ids)

            # analytic_accounts = False
            if analytic_ids:
                analytic_accounts = self.env['account.analytic.account'].browse(list(analytic_ids))
                if analytic_accounts:
                    for aa in analytic_accounts:
                        analytic_paln_id = aa.plan_id.id
                        tracking_map = self.env['xero.analytic.account.map'].sudo().search(
                            [('analytic_account_id', '=', aa.id), ('analytic_plan_id', '=', analytic_paln_id),
                             ('xero_instance_id', '=', xero_instance.id)], limit=1)
                        if tracking_map:
                            tracking_vals.append({
                                "TrackingCategoryID": tracking_map.xero_analytic_plan_id,
                                "Name": tracking_map.analytic_plan_id.name,
                                "Option": tracking_map.xero_analytic_acc_name,
                            })

            if tracking_vals:
                line_item['Tracking'] = tracking_vals[:2]

            if line.tax_ids:
                tax_map = self.env['xero.tax.map'].sudo().search([('xero_instance_id', '=', xero_instance.id),
                                                                  ('tax_id', 'in', line.tax_ids.ids), ], limit=1)
                if tax_map:
                    line_item["TaxType"] = tax_map.xero_tax_id
            line_items.append(line_item)
        move_type_map = {
            'out_invoice': 'ACCREC',
            'in_invoice': 'ACCPAY',
        }
        currency_rate = invoice.company_id.currency_id._convert(
            1.0, invoice.currency_id, invoice.company_id,
            invoice.invoice_date or fields.Date.context_today(invoice), round=False)
        move_type = move_type_map.get(invoice.move_type)
        invoice_payload = {
            "Date": invoice.invoice_date.strftime('%Y-%m-%d') if invoice.invoice_date else False,
            "DueDate": invoice.invoice_date_due.strftime('%Y-%m-%d') if invoice.invoice_date_due else False,
            "Type": move_type,
            "InvoiceNumber": invoice.name,
            "Status": {'draft': 'DRAFT', 'posted': 'AUTHORISED', 'cancel': 'VOIDED'}.get(invoice.state, 'DRAFT'),
            "Reference": invoice.ref,
            "Contact": {
                "ContactID": partner_map.xero_contact_id,
            },
            # "Total": float(invoice.amount_total),
            "LineItems": line_items,
            "CurrencyCode": invoice.currency_id.name if invoice.currency_id else False,
            'CurrencyRate': round(currency_rate, 5),
            "LineAmountTypes": "Inclusive" if tax_included else "Exclusive",
        }

        return invoice_payload

    def export_invoice_to_xero(self, invoice, xero_instance):
        """
        This method is used to export invoices to xero with request payload
        """
        if invoice.state != 'posted':
            return

        move_type = 'Invoice' if invoice.move_type == 'out_invoice' else 'Bill'

        if invoice.is_skip_transaction:
            invoice.message_post(
                body=f"{move_type} export was skipped because the 'Skip Invoice Export' option is enabled..")
            return

        if invoice.move_type in ('out_invoice', 'in_invoice') and invoice.xero_ref_id:
            move_type = 'Invoice' if invoice.move_type == 'out_invoice' else 'Bill'
            invoice.message_post(body=f"{move_type} has already been exported to Xero with ID: {invoice.xero_ref_id}.")
            return


        log_id = self.env['xero.log.vts'].sudo().generate_xero_logs(
            xero_operation_name="invoice", xero_operation_type="export",
            instance=xero_instance.id, xero_operation_message=f"Export process started for {move_type} {invoice.name}.")

        inv_partner = invoice.partner_id.parent_id if invoice.partner_id.parent_id else invoice.partner_id

        partner_map = self.env['xero.partner.map'].search(
            [('partner_id', '=', inv_partner.id), ('xero_instance_id', '=', xero_instance.id), ], limit=1)

        if not partner_map:
            inv_partner.export_partner_to_xero(xero_instance)

            partner_map = self.env['xero.partner.map'].search(
                [('partner_id', '=', inv_partner.id), ('xero_instance_id', '=', xero_instance.id), ], limit=1)

            if not partner_map:
                msg = f"Failed to export partner {inv_partner.name} to Xero"
                invoice.error_in_export = True
                self.env['xero.log.vts.line'].sudo().generate_xero_process_line(xero_operation_name="invoice",
                                                                                xero_operation_type="export",
                                                                                instance=xero_instance.id,
                                                                                xero_operation_message=msg,
                                                                                log_id=log_id, fault_operation=True)
                return

        invoice_payload = self.prepare_invoice_payload(invoice, partner_map, xero_instance)

        try:
            request_url = f"{xero_instance.xero_base_url}/Invoices"
            response_json, status_code = self.env['xero.api.vts'].xero_post_request(xero_instance.access_token,
                                                                                    xero_instance.tenant_id,
                                                                                    request_url,
                                                                                    invoice_payload)
            if status_code in (200, 201):
                inv_data = response_json.get('Invoices')[0]
                xr_invoice_id = inv_data.get('InvoiceID')
                invoice.xero_instance_id = xero_instance.id
                invoice.error_in_export = False
                invoice.xero_ref_id = xr_invoice_id
                invoice.xr_invoice_num = inv_data.get('InvoiceNumber', '')
                invoice.xr_move_type = inv_data.get('Type', 'ACCREC')
                invoice.is_inv_exported = True if invoice.move_type == 'out_invoice' else False
                invoice.is_bill_exported = True if invoice.move_type == 'in_invoice' else False
                # else:
                #     invoice.xero_ref_id = xr_invoice_id
                #     invoice.is_bill_exported = True

                invoice.message_post(body=f"Exported {move_type} {invoice.name} to Xero with ID: {xr_invoice_id}")
                self.env['xero.log.vts.line'].sudo().generate_xero_process_line(xero_operation_name="invoice",
                                                                                xero_operation_type="export",
                                                                                instance=xero_instance.id,
                                                                                xero_operation_message=f"Successfully exported {move_type} {invoice.name}",
                                                                                process_request_message=invoice_payload,
                                                                                process_response_message=response_json,
                                                                                log_id=log_id)
            else:
                res_error = response_json.get('Message', response_json)

                msg = f"Failed to export {move_type} {invoice.name} to Xero. Response: {res_error}"
                invoice.message_post(body=msg)
                invoice.error_in_export = True
                self.env['xero.log.vts.line'].sudo().generate_xero_process_line(xero_operation_name="invoice",
                                                                                xero_operation_type="export",
                                                                                instance=xero_instance.id,
                                                                                xero_operation_message=msg,
                                                                                process_request_message=invoice_payload,
                                                                                process_response_message=response_json,
                                                                                log_id=log_id, fault_operation=True)

        except Exception as e:
            invoice.message_post(body=f"Exception while exporting {move_type} {invoice.name} to Xero: {str(e)}")
            invoice.error_in_export = True
            self.env['xero.log.vts.line'].sudo().generate_xero_process_line(xero_operation_name="invoice",
                                                                            xero_operation_type="export",
                                                                            instance=xero_instance.id,
                                                                            xero_operation_message=f"Exception: {str(e)}",
                                                                            process_request_message=invoice_payload,
                                                                            process_response_message=str(e),
                                                                            log_id=log_id, fault_operation=True)
        return None

    def prepare_credit_note_payload(self, credit_note, map_partner, xero_instance):
        line_items = []
        tax_included = False
        for line in credit_note.invoice_line_ids.filtered(
                lambda l: l.display_type not in ('line_section', 'line_note')):
            line_tax_included = any(tax.price_include for tax in line.tax_ids)
            tax_included = tax_included or line_tax_included
            tax_amount = round(line.price_total - line.price_subtotal, 2)
            if line_tax_included:
                unit_amount = (line.price_total - tax_amount) / line.quantity if line.quantity else 0.0
            else:
                unit_amount = line.price_unit

            line_item = {
                "Description": line.name or line.product_id.name,
                "Quantity": line.quantity,
                "UnitAmount": line.currency_id.round(unit_amount),
                # "ItemCode": line.product_id.default_code,
                "LineAmount": line.price_subtotal,
            }
            if credit_note.move_type == 'out_refund' and line.discount:
                line_item["DiscountRate"] = float(line.discount)
            line_item["TaxAmount"] = line.currency_id.round(tax_amount)
            account_id = line.account_id
            account_mapping = self.env['xero.account.map'].sudo().search(
                [('account_id', '=', account_id.id), ('xero_instance_id', '=', xero_instance.id)], limit=1)
            if not account_mapping:
                account_mapping = account_id.export_account_to_xero(account_id, xero_instance)
                if account_mapping:
                    credit_note.message_post(
                        body=f"Charts Of Account Successfully exported with ID : {account_mapping.xero_account_id}")
                else:
                    msg = "Failed to export charts of account to xero"
                    log_id = self.env['xero.log.vts'].sudo().generate_xero_logs(xero_operation_name="account",
                                                                                xero_operation_type="export",
                                                                                instance=xero_instance.id,
                                                                                xero_operation_message=f"failed to export charts of account tp xero.")
                    self.env['xero.log.vts.line'].sudo().generate_xero_process_line(xero_operation_name="account",
                                                                                    xero_operation_type="export",
                                                                                    instance=xero_instance.id,
                                                                                    xero_operation_message=msg,
                                                                                    log_id=log_id, fault_operation=True)
                    return
            line_item['AccountCode'] = account_mapping.xero_account_code
            analytic_distribution = line.analytic_distribution or {}
            analytic_ids = set()
            tracking_vals = []

            for key in analytic_distribution.keys():
                ids = [int(x) for x in key.split(',')]
                analytic_ids.update(ids)

            # analytic_accounts = False
            if analytic_ids:
                analytic_accounts = self.env['account.analytic.account'].browse(list(analytic_ids))
                if analytic_accounts:
                    for aa in analytic_accounts:
                        analytic_paln_id = aa.plan_id.id
                        tracking_map = self.env['xero.analytic.account.map'].sudo().search(
                            [('analytic_account_id', '=', aa.id), ('analytic_plan_id', '=', analytic_paln_id),
                             ('xero_instance_id', '=', xero_instance.id)], limit=1)
                        if tracking_map:
                            tracking_vals.append({
                                "TrackingCategoryID": tracking_map.xero_analytic_plan_id,
                                "Name": tracking_map.analytic_plan_id.name,
                                "Option": tracking_map.xero_analytic_acc_name,
                            })

            if tracking_vals:
                line_item['Tracking'] = tracking_vals[:2]

            if line.tax_ids:
                tax_map = self.env['xero.tax.map'].sudo().search([('xero_instance_id', '=', xero_instance.id),
                                                                  ('tax_id', 'in', line.tax_ids.ids), ], limit=1)
                if tax_map:
                    line_item["TaxType"] = tax_map.xero_tax_id
            line_items.append(line_item)

        move_type_map = {
            'out_refund': 'ACCRECCREDIT',
            'in_refund': 'ACCPAYCREDIT',
        }
        currency_rate = credit_note.company_id.currency_id._convert(
            1.0, credit_note.currency_id, credit_note.company_id,
            credit_note.invoice_date or fields.Date.context_today(credit_note), round=False)
        move_type = move_type_map.get(credit_note.move_type)
        invoice_payload = {
            "Type": move_type,
            "CreditNoteNumber":credit_note.name,
            "Status": {'draft': 'DRAFT', 'posted': 'AUTHORISED', 'cancel': 'VOIDED'}.get(credit_note.state, 'DRAFT'),
            "Reference": credit_note.ref,
            "Contact": {
                "ContactID": map_partner.xero_contact_id,
            },
            "LineItems": line_items,
            "CurrencyCode": credit_note.currency_id.name if credit_note.currency_id else False,
            'CurrencyRate': round(currency_rate, 5),
            "LineAmountTypes": "Inclusive" if tax_included else "Exclusive",
        }
        if credit_note.reversed_entry_id:
            invoice_payload["Allocations"] = [{
                "Amount": float(credit_note.amount_total),
                "Invoice": {
                    "InvoiceID": (
                        credit_note.reversed_entry_id.xero_ref_id
                    )
                }
            }]
        return invoice_payload

    def export_credit_note_to_xero(self, credit_note, xero_instance):
        pass
        if credit_note.state != 'posted':
            return

        if credit_note.is_skip_transaction:
            credit_note.message_post(
                body="Credit Note export skipped because the 'Skip Invoice Export' flag is enabled.")
            return

        if credit_note.move_type in ('out_refund', 'in_refund') and credit_note.xero_ref_id:
            credit_note.message_post(
                body=f"This Credit Note has already been exported to Xero with ID: {credit_note.xero_ref_id}.")
            return

        log_id = self.env['xero.log.vts'].sudo().generate_xero_logs(
            xero_operation_name="credit_note", xero_operation_type="export",
            instance=xero_instance.id, xero_operation_message=f"Starting export for Credit Note {credit_note.name}.")

        inv_partner = credit_note.partner_id.parent_id if credit_note.partner_id.parent_id else credit_note.partner_id

        partner_map = self.env['xero.partner.map'].sudo().search(
            [('partner_id', '=', inv_partner.id), ('xero_instance_id', '=', xero_instance.id)], limit=1)

        if not partner_map:
            inv_partner.export_partner_to_xero(xero_instance)
            partner_map = self.env['xero.partner.map'].sudo().search(
                [('partner_id', '=', inv_partner.id), ('xero_instance_id', '=', xero_instance.id), ], limit=1)

            if not partner_map:
                msg = f"Failed to export partner {inv_partner.name} to Xero"
                credit_note.error_in_export = True
                self.env['xero.log.vts.line'].sudo().generate_xero_process_line(xero_operation_name="credit_note",
                                                                                xero_operation_type="export",
                                                                                instance=xero_instance.id,
                                                                                xero_operation_message=msg,
                                                                                log_id=log_id, fault_operation=True)
                return

        credit_note_payload = self.prepare_credit_note_payload(credit_note, partner_map, xero_instance)

        try:
            request_url = f"{xero_instance.xero_base_url}/CreditNotes"
            response_json, status_code = self.env['xero.api.vts'].xero_post_request(xero_instance.access_token,
                                                                                    xero_instance.tenant_id,
                                                                                    request_url, credit_note_payload)
            if status_code in (200, 201):
                credit_data = response_json.get('CreditNotes')[0]
                xr_credit_id = credit_data.get('CreditNoteID')
                credit_note.xero_instance_id = xero_instance.id
                credit_note.error_in_export = False
                credit_note.xero_ref_id = xr_credit_id
                credit_note.xr_invoice_num = credit_data.get('CreditNoteNumber', '')
                credit_note.xr_move_type = credit_data.get('Type', 'ACCRECCREDIT')
                credit_note.is_inv_exported = True

                credit_note.message_post(
                    body=f"Exported Credit Note {credit_note.name} to Xero with ID: {xr_credit_id}")
                self.env['xero.log.vts.line'].sudo().generate_xero_process_line(xero_operation_name="credit_note",
                                                                                xero_operation_type="export",
                                                                                instance=xero_instance.id,
                                                                                xero_operation_message=f"Successfully exported Credit Note {credit_note.name}",
                                                                                process_request_message=credit_note_payload,
                                                                                process_response_message=response_json,
                                                                                log_id=log_id)
            else:
                res_error = response_json.get('Message', response_json)
                msg = f"Failed to export Credit Note {credit_note.name} to Xero. Response: {res_error}"
                credit_note.message_post(body=msg)
                credit_note.error_in_export = True
                self.env['xero.log.vts.line'].sudo().generate_xero_process_line(xero_operation_name="credit_note",
                                                                                xero_operation_type="export",
                                                                                instance=xero_instance.id,
                                                                                xero_operation_message=msg,
                                                                                process_request_message=credit_note_payload,
                                                                                process_response_message=response_json,
                                                                                log_id=log_id, fault_operation=True)
        except Exception as e:
            credit_note.message_post(body=f"Exception while exporting Credit Note {credit_note.name} to Xero: {str(e)}")
            credit_note.error_in_export = True
            self.env['xero.log.vts.line'].sudo().generate_xero_process_line(xero_operation_name="credit_note",
                                                                            xero_operation_type="export",
                                                                            instance=xero_instance.id,
                                                                            xero_operation_message=f"Exception: {str(e)}",
                                                                            process_request_message=credit_note_payload,
                                                                            process_response_message=str(e),
                                                                            log_id=log_id, fault_operation=True)
        return None

    def create_consolidated_invoice_payload(self, invoices, partner_map, xero_instance):
        """
        invoices: recordset of account.move (same customer)
        """
        invoices = invoices.sorted('invoice_date')
        first_invoice = invoices[0]

        line_items = []
        tax_included = False
        total_amount = 0.0

        for invoice in invoices:
            for line in invoice.invoice_line_ids.filtered(
                    lambda l: l.display_type not in ('line_section', 'line_note')):

                if any(tax.price_include for tax in line.tax_ids):
                    tax_included = True

                tax_amount = round(line.price_total - line.price_subtotal, 2)

                if tax_included:
                    if line.quantity:
                        unit_amount = (line.price_total - tax_amount) / line.quantity
                    else:
                        unit_amount = 0.0
                else:
                    unit_amount = line.price_unit

                unit_amount = round(unit_amount, 2)

                line_item = {
                    "Description": line.name,
                    "Quantity": abs(line.quantity),
                    "UnitAmount": unit_amount,
                    "TaxAmount": round(tax_amount, 2),
                }

                account_id = line.account_id
                account_mapping = self.env['xero.account.map'].sudo().search(
                    [('account_id', '=', account_id.id), ('xero_instance_id', '=', xero_instance.id)], limit=1)
                if not account_mapping:
                    account_mapping = account_id.export_account_to_xero(account_id, xero_instance)
                    if account_mapping:
                        invoice.message_post(
                            body=f"Charts Of Account Successfully exported with ID : {account_mapping.xero_account_id}")
                    else:
                        msg = "Failed to export charts of account to xero"
                        log_id = self.env['xero.log.vts'].sudo().generate_xero_logs(xero_operation_name="account",
                                                                                    xero_operation_type="export",
                                                                                    instance=xero_instance.id,
                                                                                    xero_operation_message=f"failed to export charts of account tp xero.")
                        self.env['xero.log.vts.line'].sudo().generate_xero_process_line(xero_operation_name="account",
                                                                                        xero_operation_type="export",
                                                                                        instance=xero_instance.id,
                                                                                        xero_operation_message=msg,
                                                                                        log_id=log_id,
                                                                                        fault_operation=True)
                        return

                line_item['AccountCode'] = account_mapping.xero_account_code
                if line.discount:
                    line_item["DiscountRate"] = line.discount

                if line.tax_ids:
                    tax_map = self.env['xero.tax.map'].sudo().search([('xero_instance_id', '=', xero_instance.id),
                                                                      ('tax_id', 'in', line.tax_ids.ids)], limit=1)

                    if tax_map:
                        line_item["TaxType"] = tax_map.xero_tax_id

                analytic_distribution = line.analytic_distribution or {}
                analytic_ids = set()
                tracking_vals = []

                for key in analytic_distribution.keys():
                    ids = [int(x) for x in key.split(',')]
                    analytic_ids.update(ids)

                if analytic_ids:
                    analytic_accounts = self.env['account.analytic.account'].browse(list(analytic_ids))
                    for aa in analytic_accounts:
                        tracking_map = self.env['xero.analytic.account.map'].sudo().search([
                            ('analytic_account_id', '=', aa.id), ('analytic_plan_id', '=', aa.plan_id.id),
                            ('xero_instance_id', '=', xero_instance.id)], limit=1)

                        if tracking_map:
                            tracking_vals.append({
                                "TrackingCategoryID": tracking_map.xero_analytic_plan_id,
                                "Name": tracking_map.analytic_plan_id.name,
                                "Option": tracking_map.xero_analytic_acc_name,
                            })

                if tracking_vals:
                    line_item["Tracking"] = tracking_vals[:2]

                line_total = (unit_amount * line.quantity) + tax_amount

                if line.discount:
                    discount_amt = (unit_amount * line.quantity) * (line.discount / 100)
                    line_total -= discount_amt

                total_amount += round(line_total, 2)

                line_items.append(line_item)

        invoice_total = round(sum(invoices.mapped('amount_total')), 2)

        if round(total_amount, 2) != invoice_total:
            rounding_diff = round(invoice_total - total_amount, 2)
            line_items.append({
                "Description": f"Rounding adjustment: document total {invoice_total}",
                "Quantity": 1,
                "UnitAmount": rounding_diff,
                "AccountCode": "860",
            })

        currency_rate = first_invoice.company_id.currency_id._convert(
            1.0, first_invoice.currency_id, first_invoice.company_id,
            first_invoice.invoice_date or fields.Date.context_today(first_invoice), round=False)

        invoice_payload = {
            "Date": first_invoice.invoice_date.strftime('%Y-%m-%d') if first_invoice.invoice_date else False,
            "DueDate": first_invoice.invoice_date_due.strftime('%Y-%m-%d') if first_invoice.invoice_date_due else False,
            "Type": "ACCREC",
            "InvoiceNumber": self.env['ir.sequence'].sudo().next_by_code('xero.consolidated.invoice'),
            "Reference": ", ".join(invoices.mapped('name')),
            "Contact": {
                "ContactID": partner_map.xero_contact_id,
            },
            "LineItems": line_items,
            "LineAmountTypes": "Inclusive" if tax_included else "Exclusive",
            "CurrencyCode": first_invoice.currency_id.name,
            "CurrencyRate": round(currency_rate, 5),
        }

        return invoice_payload

    def export_consolidated_invoices_to_xero(self, invoices, xero_instance):
        """
        invoices: recordset of selected invoices
        """
        log_id = self.env['xero.log.vts'].sudo().generate_xero_logs(xero_operation_name="invoice",
                                                                    xero_operation_type="export",
                                                                    instance=xero_instance.id,
                                                                    xero_operation_message="Starting export for Consolidated Invoices.")

        consolidated_partner = xero_instance.partner_id

        partner_map = self.env['xero.partner.map'].sudo().search([('partner_id', '=', consolidated_partner.id),
                                                                  ('xero_instance_id', '=', xero_instance.id)], limit=1)

        if not partner_map:
            consolidated_partner.export_partner_to_xero(xero_instance)
            partner_map = self.env['xero.partner.map'].sudo().search([('partner_id', '=', consolidated_partner.id),
                                                                      ('xero_instance_id', '=', xero_instance.id)],
                                                                     limit=1)

            if not partner_map:
                msg = f"Failed to export partner {consolidated_partner.name} to Xero"
                self.env['xero.log.vts.line'].sudo().generate_xero_process_line(xero_operation_name="invoice",
                                                                                xero_operation_type="export",
                                                                                instance=xero_instance.id,
                                                                                xero_operation_message=msg,
                                                                                log_id=log_id, fault_operation=True)
                return

        invoices = invoices.filtered(lambda inv: inv.state == 'posted' and inv.payment_state in ('paid', 'in_payment')
                                                 and not inv.xero_ref_id and inv.is_skip_transaction == False
                                                 and (
                                                         inv.partner_id.parent_id or inv.partner_id) == consolidated_partner)

        if not invoices:
            for inv in invoices:
                inv.message_post('Invoice does not match with the applied filter of State')
            return

        invoice_payload = self.create_consolidated_invoice_payload(invoices, partner_map, xero_instance)
        try:

            request_url = f"{xero_instance.xero_base_url}/Invoices"
            response_json, status_code = self.env['xero.api.vts'].xero_post_request(xero_instance.access_token,
                                                                                    xero_instance.tenant_id,
                                                                                    request_url, invoice_payload)

            if status_code in (200, 201):
                xr_invoice_id = response_json.get('Invoices')[0].get('InvoiceID')

                for inv in invoices:
                    inv.xero_instance_id = xero_instance.id
                    inv.xero_ref_id = xr_invoice_id
                    inv.is_inv_exported = True
                    inv.is_consolidated_invoice = True
                    inv.error_in_export = False
                    inv.message_post(body=f"Exported consolidated invoice to Xero with ID: {xr_invoice_id}")
                    self.env['xero.log.vts.line'].sudo().generate_xero_process_line(xero_operation_name="invoice",
                                                                                    xero_operation_type="export",
                                                                                    instance=xero_instance.id,
                                                                                    xero_operation_message=f"Successfully exported Consolidated Invoice {inv.name}",
                                                                                    process_request_message=invoice_payload,
                                                                                    process_response_message=response_json,
                                                                                    log_id=log_id)
            else:
                for inv in invoices:
                    res_error = response_json.get('Message', response_json)
                    msg = f"Failed to export Invoice {inv.name} to Xero. Response: {res_error}"
                    invoices.message_post(body=msg)
                    invoices.error_in_export = True
                    self.env['xero.log.vts.line'].sudo().generate_xero_process_line(xero_operation_name="invoice",
                                                                                    xero_operation_type="export",
                                                                                    instance=xero_instance.id,
                                                                                    xero_operation_message=msg,
                                                                                    process_request_message=invoice_payload,
                                                                                    process_response_message=response_json,
                                                                                    log_id=log_id, fault_operation=True)

        except Exception as e:
            invoices.message_post(body=f"Exception while exporting Invoice {invoices.name} to Xero: {str(e)}")
            invoices.error_in_export = True
            self.env['xero.log.vts.line'].sudo().generate_xero_process_line(xero_operation_name="invoice",
                                                                            xero_operation_type="export",
                                                                            instance=xero_instance.id,
                                                                            xero_operation_message=f"Exception: {str(e)}",
                                                                            process_request_message=invoice_payload,
                                                                            process_response_message=str(e),
                                                                            log_id=log_id, fault_operation=True)
        return True

    def export_invoice_bill_to_xero(self, instance):
        for move in self:
            if move.move_type in ('out_invoice', 'in_invoice'):
                self.export_invoice_to_xero(move, instance)
            if move.move_type in ('in_refund', 'out_refund'):
                self.export_credit_note_to_xero(move, instance)

    def export_consolidated_invoice_to_xero(self, instance):
        if instance.consolidated_invoice:
            self.export_consolidated_invoices_to_xero(self, instance)
