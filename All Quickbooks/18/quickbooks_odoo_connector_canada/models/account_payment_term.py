# -*- coding: utf-8 *-*
from odoo import models, fields


class AccountPayment(models.Model):
    _inherit = "account.payment.term"

    is_export_error = fields.Boolean("Error in QuickBooks Export", default=False)
    is_payment_term_qbca_exported = fields.Boolean(string="Exported Payment Term", default=False)

    def action_qkca_instance_for_payment_term(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Quickbook Canada Instance Wizard',
            'res_model': 'quickbook.instance.wizard',
            'view_mode': 'form',
            'target': 'new',
        }

    def _prepare_qkca_payment_term_vals(self, payment_term):
        payment_term_payload={
                "DueDays": payment_term.line_ids[0].nb_days if payment_term.line_ids else 0,
                "Name": payment_term.name,
                "DiscountPercent" :payment_term.line_ids[0].value_amount if payment_term.line_ids else 0
        }

        return payment_term_payload, 'term'


    def export_term_to_quickbooks_ca(self,payment_term,quickbook_instance):
        if payment_term.is_payment_term_qbca_exported:
            return

        company = payment_term.company_id.id if payment_term.company_id else False
        # quickbook_instance = self.env['quickbooks.connect'].sudo().search([('state', '=', 'connected'),('company_id', '=', company)], limit=1)

        if quickbook_instance:
            log_id = self.env['quickbooks.log.vts'].sudo().generate_quickbooks_logs(
                quickbooks_operation_name="payment_term", quickbooks_operation_type="export",
                instance=quickbook_instance.id,
                quickbooks_operation_message=f"Starting export for Payment Term {payment_term.name}"
            )

            payment_term_payload, endpoint = self._prepare_qkca_payment_term_vals(payment_term)

            try:
                payment_term_url = f"{quickbook_instance.quickbook_base_url}/{quickbook_instance.realm_id}/{endpoint}"

                response_json, status_code = self.env['quickbooks.api.vts'].sudo().qb_post_request(
                    quickbook_instance.access_token, payment_term_url, payment_term_payload)

                if status_code == 200:
                    payment_data = response_json.get("Term", {})
                    qk_payment_term_id = payment_data.get("Id")
                    payment_term.is_export_error = False
                    payment_term.is_payment_term_qbca_exported = True
                    self.env['quickbooks.log.vts.line'].sudo().generate_quickbooks_process_line(
                        quickbooks_operation_name="payment_term", quickbooks_operation_type="export",
                        instance=quickbook_instance.id,
                        quickbooks_operation_message=f"Successfully exported Payment term {payment_term.name} with Id.{qk_payment_term_id}",
                        process_request_message=payment_term_payload, process_response_message=response_json,
                        log_id=log_id)
                    return response_json
                else:
                    msg = f"Failed to export Payment Term {payment_term.name} to QuickBooks. Response: {response_json}"
                    payment_term.is_export_error = True
                    self.env['quickbooks.log.vts.line'].sudo().generate_quickbooks_process_line(
                        quickbooks_operation_name="payment_term", quickbooks_operation_type="export",
                        instance=quickbook_instance.id, quickbooks_operation_message=msg,
                        process_request_message=payment_term_payload, process_response_message=response_json,
                        log_id=log_id, fault_operation=True)
                    return None

            except Exception as e:
                payment_term.is_export_error = True
                self.env['quickbooks.log.vts.line'].sudo().generate_quickbooks_process_line(
                    quickbooks_operation_name="payment_term", quickbooks_operation_type="export",
                    instance=quickbook_instance.id, quickbooks_operation_message=f"Exception: {str(e)}",
                    process_request_message=payment_term_payload, process_response_message=str(e),
                    log_id=log_id, fault_operation=True)
                return None
        else:
            payment_term.is_export_error = True
            log_id = self.env['quickbooks.log.vts'].sudo().generate_quickbooks_logs(
                quickbooks_operation_name="payment_term", quickbooks_operation_type="export",
                quickbooks_operation_message=f"Starting export for Payment Term {payment_term.name}")
            self.env['quickbooks.log.vts.line'].sudo().generate_quickbooks_process_line(
                    quickbooks_operation_name="payment_term", quickbooks_operation_type="export",
                    quickbooks_operation_message=f"No QuickBooks instance configured for {company} company.",
                    log_id=log_id, fault_operation=True)


    def export_payment_term_to_qkca(self,quickbook_instance):
        for payment_term in self:
            payment_term.export_term_to_quickbooks_ca(payment_term,quickbook_instance)
