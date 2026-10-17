# -*- coding: utf-8 -*-
from odoo import models, fields
import pprint


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    error_in_export = fields.Boolean(string="Error In Export", copy=False)

    def action_xero_instance_for_product(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Xero Instance Wizard',
            'res_model': 'xero.instance.wizard',
            'view_mode': 'form',
            'target': 'new',
        }

    def _prepare_product_payload(self, xero_instance):
        """
        this method is used to create a payload of product to export it in to xero
        """
        product_payload = {
            "Code": self.default_code,
            "Name": self.name,
            "Description": self.description_sale,
            "IsSold": 'true' if self.sale_ok else 'false',
            "IsPurchased": 'true' if self.purchase_ok else 'false'
        }
        income_account_code = (
                    self.property_account_income_id.code or self.categ_id.property_account_income_categ_id.code)
        expense_account_code = (
                    self.property_account_expense_id.code or self.categ_id.property_account_expense_categ_id.code)
        # Sales Details
        if self.sale_ok:
            account_mapping = self.env['xero.account.map'].sudo().search(
                [('xero_account_code', '=', income_account_code), ('xero_instance_id', '=', xero_instance.id)], limit=1)
            income_account = account_mapping.xero_account_code if account_mapping else "200"

            tax_mapping = self.env['xero.tax.map'].sudo().search(
                [('tax_id', 'in', self.taxes_id.ids), ('xero_instance_id', '=', xero_instance.id)], limit=1)

            product_payload["SalesDetails"] = {
                "UnitPrice": float(self.list_price or 0.0),
                "AccountCode": income_account,
            }
            if tax_mapping:
                product_payload["SalesDetails"]["TaxType"] = tax_mapping.xero_tax_id

        # Purchase Details
        if self.purchase_ok:
            account_mapping = self.env['xero.account.map'].sudo().search(
                [('xero_account_code', '=', expense_account_code), ('xero_instance_id', '=', xero_instance.id)],
                limit=1)
            expense_account = account_mapping.xero_account_code if account_mapping else "310"
            tax_mapping = self.env['xero.tax.map'].sudo().search(
                [('tax_id', 'in', self.supplier_taxes_id.ids), ('xero_instance_id', '=', xero_instance.id)], limit=1)

            product_payload["PurchaseDetails"] = {
                "UnitPrice": float(self.standard_price or 0.0),
                "AccountCode": expense_account,
            }
            if tax_mapping:
                product_payload["PurchaseDetails"]["TaxType"] = tax_mapping.xero_tax_id

        # Check if item should be tracked in Xero
        if self.type == "consu":
            product_payload.update({
                "IsTrackedAsInventory": 'true' if self.is_storable else 'false',
            })

        return product_payload

    def export_product_to_xr(self, instance):
        """
        This method is used to export payload to Xero with request payload
        """

        self.ensure_one()
        log_id = self.env['xero.log.vts'].sudo().generate_xero_logs(
            xero_operation_name="product", xero_operation_type="export",
            instance=instance.id, xero_operation_message=f"Export process started for product {self.name}.")

        existing_map = self.env['xero.product.map'].search([
            ('product_id', '=', self.id),
            ('xero_instance_id', '=', instance.id), ], limit=1)
        if existing_map:
            self.env['xero.log.vts.line'].sudo().generate_xero_process_line(
                xero_operation_name="product",
                xero_operation_type="export",
                instance=instance.id,
                xero_operation_message=f"Skipping Already exported Product: {self.name}",
                log_id=log_id)
            return

        company = self.company_id.id or self.env.company.id

        xero_instance = instance

        if not xero_instance:
            msg = f"Xero is not configured for the company {company}."
            self.message_post(body=msg)
            return msg

        product_payload = self._prepare_product_payload(instance)

        try:
            request_url = f"{xero_instance.xero_base_url}/Items"
            response_json, status_code = self.env['xero.api.vts'].xero_post_request(xero_instance.access_token,
                                                                                    xero_instance.tenant_id,
                                                                                    request_url, product_payload)

            if status_code in (200, 201):
                product_data = response_json.get("Items", {})

                xr_product_id = product_data[0].get('ItemID')
                xr_product_name = product_data[0].get('Name')
                product_map_obj = self.env['xero.product.map'].sudo()
                map_val = {
                    'xero_instance_id': instance.id,
                    'xero_product_id': xr_product_id,
                    'xero_product_name': xr_product_name,
                    'product_id': self.id,
                    'xero_response': pprint.pformat(response_json)
                }
                product_map_obj.create(map_val)

                self.message_post(body=f"Product {self.name} exported to Xero with ID: {xr_product_id}.")
                log_line = self.env['xero.log.vts.line'].sudo().generate_xero_process_line(
                    xero_operation_name="product",
                    xero_operation_type="export", instance=xero_instance.id,
                    xero_operation_message=f"Successfully exported Product {self.name}",
                    process_request_message=product_payload, process_response_message=response_json, log_id=log_id)
            else:
                res_error = response_json.get('Message', response_json)
                msg = f"Failed to export Product {self.name} to Xero. Response: {res_error}"
                self.message_post(body=msg)

                log_line = self.env['xero.log.vts.line'].sudo().generate_xero_process_line(
                    xero_operation_name="product",
                    xero_operation_type="export", instance=xero_instance.id,
                    xero_operation_message=msg, process_request_message=product_payload,
                    process_response_message=response_json, log_id=log_id,
                    fault_operation=True)

        except Exception as e:
            msg = f"Failed to export product {self.name} to Xero: {str(e)}"
            self.message_post(body=msg)
            log_line = self.env['xero.log.vts.line'].sudo().generate_xero_process_line(
                xero_operation_name='payment',
                xero_operation_type='export', instance=xero_instance.id,
                xero_operation_message=msg, process_response_message=f"Exception: {str(e)}",
                process_request_message=pprint.pformat(product_payload), log_id=log_id, fault_operation=True)
            return msg

    def export_product_to_xero(self, instance):
        for product in self:
            product.export_product_to_xr(instance)
