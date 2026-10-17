# -*- coding: utf-8 *-*
import pprint
import requests
from odoo import models
from odoo.exceptions import ValidationError


class Partner(models.Model):
    _inherit = "res.partner"

    def action_instance_wizard(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Xero Instance Wizard',
            'res_model': 'xero.instance.wizard',
            'view_mode': 'form',
            'target': 'new',
        }

    def _prepare_xero_contact_persons(self, partner):
        contact_persons = []

        for child in partner.child_ids.filtered(lambda c: c.type in  ('contact','invoice')):
            first_name = child.name or ''
            last_name = ''
            if child.name and ' ' in child.name:
                first_name, last_name = child.name.split(' ', 1)

            contact_persons.append({
                "FirstName": first_name,
                "LastName": last_name,
                "EmailAddress": child.email or '',
                "IncludeInEmails": True,
            })

        return contact_persons

    def _prepare_xero_partner_payload(self, partner, log_id=False, instance=False):


        addresses = []
        addresses.append({
            "AddressType": "POBOX",
            "AddressLine1": partner.street or '',
            "AddressLine2": partner.street2 or '',
            "City": partner.city or '',
            "Region": partner.state_id.name if partner.state_id else '',
            "PostalCode": partner.zip or '',
            "Country": partner.country_id.code if partner.country_id else '',
            })

        for child in partner.child_ids:
            if child.type == 'delivery':
                addresses.append({
                    "AddressType": "STREET",
                    "AddressLine1": child.street or '',
                    "AddressLine2": child.street2 or '',
                    "City": child.city or '',
                    "Region": child.state_id.name if child.state_id else '',
                    "PostalCode": child.zip or '',
                    "Country": child.country_id.code if child.country_id else '',
                })

        phones = []
        if partner.phone:
            phones.append({
                "PhoneType": "DEFAULT",
                "PhoneNumber": partner.phone
            })

        child_contacts = partner.child_ids.filtered(
            lambda c: c.type in ('contact', 'invoice')
        )

        contact_persons = []
        if partner.email:
            contact_persons = self._prepare_xero_contact_persons(partner)
        if not partner.email and child_contacts:
            self.env['xero.log.vts.line'].sudo().generate_xero_process_line(
                xero_operation_name='partner',
                xero_operation_type='export',
                instance=instance.id if instance else False,
                xero_operation_message=(
                    f"Child Partner is not included in contact person as email is missing in partner: {partner.name}"),
                 log_id=log_id,
                fault_operation=False)

        payload = {
            "Name": partner.name,
            "EmailAddress": partner.email or '',
            "Addresses": addresses,
            "Phones": phones,
            "Website": partner.website or '',
            "TaxNumber": partner.vat or '',
        }

        if contact_persons:
            payload["ContactPersons"] = contact_persons

        return payload

    def export_partner_to_xero(self, instance):
        log_id = self.env['xero.log.vts'].sudo().generate_xero_logs(
            xero_operation_name='partner',
            xero_operation_type='export',
            instance=False,
            xero_operation_message=f'Export Process Started for Partner {self.name}'
        )

        for partner in self:
            #handle parent partner only from odoo as xero accepts parent and child partner in one contact
            if partner.parent_id:
                partner.message_post(body=f"Exporting Partner '{partner.parent_id.name}' with child partner '{partner.name}'")
                self.env['xero.log.vts.line'].sudo().generate_xero_process_line(
                    xero_operation_name='partner',
                    xero_operation_type='export',
                    instance=False,
                    xero_operation_message=(
                        f" Exporting Partner '{partner.parent_id.name}' with child partner '{partner.name}'"
                    ),
                    log_id=log_id,
                    fault_operation=False
                )
                partner = partner.parent_id

            #if partner is already exported then skip that partner
            existing_map = self.env['xero.partner.map'].search([
                ('partner_id', '=', partner.id),
                ('xero_instance_id', '=', instance.id),
            ], limit=1)

            if existing_map:
                partner.message_post(body=f"Skipping Already Exported Partner: {partner.name}")
                self.env['xero.log.vts.line'].sudo().generate_xero_process_line(
                    xero_operation_name='partner',
                    xero_operation_type='export',
                    instance=instance.id,
                    xero_operation_message=f"Skipping Already Exported Partner: {partner.name}",
                    log_id=log_id,
                    fault_operation=False)
                continue

            payload = self._prepare_xero_partner_payload(partner,log_id=log_id,instance=instance)

            url = f"{instance.xero_base_url}/Contacts"
            headers = {
                'Authorization': f'Bearer {instance.access_token}',
                'Xero-Tenant-Id': instance.tenant_id,
                'Content-Type': 'application/json',
                'Accept': 'application/json',
            }

            try:
                response = requests.post(url=url, headers=headers, json=payload)
            except Exception as e:
                raise ValidationError(f"Xero request failed: {e}")

            if response.status_code in (200, 201):
                data = response.json()
                contact = data.get('Contacts',[{}])[0]

                contact_id = contact.get("ContactID")
                contact_name = contact.get("Name")

                partner_map_obj=self.env['xero.partner.map']
                map_vals={
                    'xero_instance_id': instance.id,
                    'xero_contact_id': contact_id,
                    'xero_contact_name': contact_name,
                    'partner_id': partner.id,
                    'xero_response':pprint.pformat(data)
                }
                partner_map_obj.create(map_vals)

                partner.message_post(body=f"Partner {partner.name} successfully exported into xero")
                self.env['xero.log.vts.line'].sudo().generate_xero_process_line(
                xero_operation_name='partner',xero_operation_type='export',instance=instance.id,
                xero_operation_message=f"Partner {partner.name} successfully exported into xero",
                log_id=log_id,process_request_message= payload, process_response_message= response ,fault_operation=False)
            else:
                res_error = response.get('Message', response)
                msg = f"Failed to export Partner to Xero. Response: {res_error}"
                partner.message_post(body=msg)
                self.env['xero.log.vts.line'].sudo().generate_xero_process_line(xero_operation_name='partner',
                    xero_operation_type='export',instance=instance.id,xero_operation_message=response.text,
                    log_id=log_id,fault_operation=True)

