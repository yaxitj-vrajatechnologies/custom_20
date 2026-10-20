# -*- coding: utf-8 -*-
from odoo import models, fields
import requests
import logging
import pprint

_logger = logging.getLogger(__name__)

class ResPartner(models.Model):
    _inherit = 'res.partner'
    

    def action_instance_wizard_partner(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Quickbook Instance Wizard',
            'res_model': 'instance.wizard',
            'view_mode': 'form',
            'target': 'new',
        }

    def export_customer_to_quickbooks(self, quickbook_instance=None):
        for partner in self:
            roles = []
            if partner.customer_rank > 0:
                roles.append(("customer", "qbo.partner.map.vts", "partner_id", "quickbook_id"))
            if partner.supplier_rank > 0:
                roles.append(("vendor", "qbo.vendor.map.vts", "vendor_id", "qbk_vendor_id"))

            if not roles:
                partner.message_post(body=f"{partner.name} is neither customer nor vendor.")
                continue

            for endpoint, model, partner_field, qb_field in roles:
                mapping = self.env[model].search([(partner_field, '=', partner.id),(qb_field, '!=', False),('quickbook_instance_id', '=', quickbook_instance.id)], limit=1)

                if mapping:
                    msg_body = (f"{partner.name} already exists in QuickBooks as {endpoint} with ID: {getattr(mapping, qb_field)}.")
                    partner.message_post(body=msg_body)
                    continue

                self._export_to_quickbooks(partner, endpoint, qb_field, quickbook_instance)

    def _export_to_quickbooks(self, partner, endpoint, qbk_field, quickbook_instance=None):
        company = partner.company_id.id if partner.company_id else self.env.company.id

        if quickbook_instance:
            log_id = self.env['quickbooks.log.vts'].sudo().generate_quickbooks_logs(quickbooks_operation_name=endpoint,
                quickbooks_operation_type="export",instance=quickbook_instance.id,
                quickbooks_operation_message=f"Starting export for {partner.name}")

            duplicate_partner = False
            if endpoint == 'customer':
                duplicate_partner = self.env['qbo.partner.map.vts'].sudo().search([('quick_name', '=', partner.name),('partner_id','=',partner.id),('quickbook_id', '!=', False)], limit=1)
            elif endpoint == 'vendor':
                duplicate_partner = self.env['qbo.vendor.map.vts'].sudo().search([('qbk_vendor_name', '=', partner.name),('vendor_id', '=', partner.id),('qbk_vendor_id', '!=', False)], limit=1)

            if duplicate_partner or self.env.context.get('duplicate_partner'):
                display_name = f"{partner.name} ({self.env['ir.sequence'].sudo().next_by_code('qbk.res.partner')})"
            else:
                display_name = f"{partner.name} ({endpoint.capitalize()})"

            bill_addr = {
                "Line1": partner.street,
                "Line2": partner.street2,
                "City": partner.city,
                "CountrySubDivisionCode": partner.state_id.code if partner.state_id else '',
                "PostalCode": partner.zip,
                "Country": partner.country_id.code if partner.country_id else ''}

            url = f"{quickbook_instance.quickbook_base_url}/{quickbook_instance.realm_id}/{endpoint}"
            headers = {
                        "Authorization": f"Bearer {quickbook_instance.access_token}",
                        "Accept": "application/xml",
                        "Content-Type": "application/json",
                        "Accept-Encoding": "identity"
                    }
            data = {
                "DisplayName": display_name,
                "GivenName": partner.name,
                "CompanyName": partner.parent_id.name or '',
                "PrimaryPhone": {"FreeFormNumber": partner.phone or ""},
                "PrimaryEmailAddr": {"Address": partner.email or ""},
                "Mobile": {"FreeFormNumber": partner.mobile or ""},
                "BillAddr": bill_addr,
            }

            try:
                response = requests.post(url, json=data, headers=headers)

                response_json = quickbook_instance.convert_xmltodict(response.text)
                
                if response.status_code == 200:
                    result = response_json
                    customer_data = result.get("IntuitResponse", {}).get(endpoint.capitalize(), {})
                    qbk_id = customer_data.get("Id")

                    if qbk_field == 'quickbook_id':
                        partner_mappings_vals = {
                            'quickbook_instance_id': quickbook_instance.id,
                            'quickbook_id': qbk_id,
                            'quick_name': customer_data.get('DisplayName'),
                            'partner_id': partner.id,
                            'company_id': quickbook_instance.company_id.id if quickbook_instance.company_id else self.env.company.id,
                            'qbo_response': pprint.pformat(customer_data),
                        }
                        partner_mapping = self.env['qbo.partner.map.vts'].sudo().create(partner_mappings_vals)
                    elif qbk_field == 'qbk_vendor_id':
                        vendor_mapping_vals={
                            'quickbook_instance_id':quickbook_instance.id,
                            'qbk_vendor_id':qbk_id,
                            'qbk_vendor_name':customer_data.get('DisplayName'),
                            'vendor_id': partner.id,
                            'company_id': quickbook_instance.company_id.id if quickbook_instance.company_id else self.env.company.id,
                            'qbo_response': pprint.pformat(customer_data),
                        }
                        vendor_mapping = self.env['qbo.vendor.map.vts'].sudo().create(vendor_mapping_vals)
                    partner.message_post(body=f"Exported {partner.name} to QuickBooks as {endpoint}, ID: {qbk_id}")
                    self.env['quickbooks.log.vts.line'].sudo().generate_quickbooks_process_line(quickbooks_operation_name=endpoint,
                    quickbooks_operation_type="export",instance=quickbook_instance.id,
                    quickbooks_operation_message=f"Successfully Exported {partner.name}",process_request_message=data,
                    process_response_message=response_json,log_id=log_id)
                    self._cr.commit()
                    return qbk_id
                else:
                    error = response_json.get("IntuitResponse", {}).get("Fault", {}).get("Error", {})
                    error_msg = error.get("Message", "")
                    if "Duplicate Name Exists Error" in error_msg and "6240" in error.get('@code'):
                        return self.with_context(duplicate_partner=True)._export_to_quickbooks(partner, endpoint,
                                                                                                 qbk_field,quickbook_instance)
                    error_msg = response_json
                    if response_json.get('IntuitResponse'):
                        error_msg = response_json['IntuitResponse']['Fault']['Error']['Message']
                    partner.message_post(body=f"Failed to export {partner.name} to QuickBooks ({endpoint}). Response: {error_msg}")
                    self.env['quickbooks.log.vts.line'].sudo().generate_quickbooks_process_line(quickbooks_operation_name=endpoint,
                    quickbooks_operation_type="export",instance=quickbook_instance.id,
                    quickbooks_operation_message=f"Export {partner.name} Failed",process_request_message=data,
                    process_response_message=response_json,log_id=log_id,fault_operation=True)
                    self._cr.commit()
                    return f"Failed to export {partner.name} to QuickBooks ({endpoint}). Response: {error_msg}"
            except Exception as e:
                partner.message_post(body=f"Exception while exporting {partner.name} to QuickBooks: {str(e)}")
                self.env['quickbooks.log.vts.line'].sudo().generate_quickbooks_process_line(quickbooks_operation_name=endpoint,quickbooks_operation_type="export",
                    instance=quickbook_instance.id,quickbooks_operation_message=f"Exception in {partner.name}",
                    process_request_message=data,process_response_message=str(e),
                    log_id=log_id,fault_operation=True)
                self._cr.commit()
                return f"Exception while exporting {partner.name} to QuickBooks: {str(e)}"

        else:
            partner.message_post(body=f"No QuickBooks instance configured for {company} company.")
            self._cr.commit()
