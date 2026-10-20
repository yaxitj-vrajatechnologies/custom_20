# -*- coding: utf-8 -*-
import pprint
from odoo import models, fields


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    qkca_product_type = fields.Char(string="Quickbook Product Type ID")
    

    def action_qkca_instance_for_product(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Quickbook Canada Instance Wizard',
            'res_model': 'quickbook.instance.wizard',
            'view_mode': 'form',
            'target': 'new',
        }


    def _prepare_qkca_product_payload(self):
        income_account_id = (self.property_account_income_id or self.categ_id.property_account_income_categ_id)
        expense_account_id = (self.property_account_expense_id or self.categ_id.property_account_expense_categ_id)

        income_account = False
        expense_account = False

        if income_account_id:
            income_account = self.env['qbo.account.vts'].sudo().search([('account_id', '=', income_account_id.id)],limit=1)
        if expense_account_id:
            expense_account = self.env['qbo.account.vts'].sudo().search([('account_id', '=', expense_account_id.id)],limit=1)

        product_payload = {
            "Name": self.name,
            "ExpenseAccountRef": {
                "value": str(expense_account.quickbook_account_id) if expense_account else "84",
                "name": expense_account.quickbook_account_name if expense_account else "Cost of Goods Sold"
            }
        }

        income_account_ref = {
            "value": str(income_account.quickbook_account_id) if income_account else "67",
            "name": income_account.quickbook_account_name if income_account else "Sales of Product Income"
        }

        if self.type == "service":
            product_payload.update({
                "Type": "Service",
                "IncomeAccountRef": income_account_ref,
            })
    
        elif self.is_storable:
            product_payload.update({
                "Type": "Inventory",
                "TrackQtyOnHand": True,
                "QtyOnHand": max(1.0, float(self.qty_available) if self.qty_available else 1.0),
                "IncomeAccountRef": income_account_ref,
                "AssetAccountRef": {"value": "85", "name": "Inventory Asset"},
                "InvStartDate": fields.Date.today().strftime("%Y-%m-%d")})
    
        else:
            product_payload["Type"] = "NonInventory"

        return product_payload


    def export_product_to_qkca(self,quickbook_instance):
        self.ensure_one()
        product_mapping = self.env['qbo.product.ca.map.vts'].search([('product_id', '=', self.id), ('quickbook_product_id', '!=', False),('quickbook_instance_id', '=', quickbook_instance.id)], limit=1)

        if product_mapping:
            self.message_post(body=f"Product already exported to QuickBooks with ID {product_mapping.quickbook_product_id}.")
            return
    
        company = self.company_id.id or self.env.company.id
        if not quickbook_instance:
            msg = f"No QuickBooks instance configured for {company} company."
            self.message_post(body=msg)
            return msg

        log_id = self.env['quickbooks.log.vts'].sudo().generate_quickbooks_logs(quickbooks_operation_name="product",
                                                                                quickbooks_operation_type="export",
                                                                                instance=quickbook_instance.id,
                                                                                quickbooks_operation_message=f"Starting export for Product {self.name}")

        payload = self._prepare_qkca_product_payload()
        qb_api = self.env['quickbooks.api.vts'].sudo()
        qb_log = self.env['quickbooks.log.vts.line'].sudo()

        try:
            pro_url = f"{quickbook_instance.quickbook_base_url}/{quickbook_instance.realm_id}/item"
            response_json, status_code = qb_api.qb_post_request(quickbook_instance.access_token, pro_url, payload)

            if status_code in (200, 201):
                product_data = response_json.get("Item", {})
                qkca_product_ID = product_data.get("Id")

                self.message_post(body=f"Exported Product {self.name} to QuickBooks, ID: {qkca_product_ID}")
                product_mapping_vals = {
                    'quickbook_instance_id': quickbook_instance.id,
                    'quickbook_product_id': qkca_product_ID,
                    'quickbook_product_name': product_data.get('Name'),
                    'product_id': self.id,
                    'company_id': quickbook_instance.company_id.id if quickbook_instance.company_id else self.env.company.id,
                    'qbo_response': pprint.pformat(product_data),
                }
                product_mapping = self.env['qbo.product.ca.map.vts'].sudo().create(product_mapping_vals)

                qb_log.generate_quickbooks_process_line(quickbooks_operation_name="product",
                                                        quickbooks_operation_type="export", instance=quickbook_instance.id,
                                                        quickbooks_operation_message=f"Successfully exported Product {self.name}",
                                                        process_request_message=payload,
                                                        process_response_message=response_json,
                                                        log_id=log_id)
                return qkca_product_ID
            else:
                msg = f"Failed to export Product {self.name} to QuickBooks. Response: {response_json}"
                self.message_post(body=msg)

                qb_log.generate_quickbooks_process_line(quickbooks_operation_name="product",
                                                        quickbooks_operation_type="export", instance=quickbook_instance.id,
                                                        quickbooks_operation_message=msg, process_request_message=payload,
                                                        process_response_message=response_json, log_id=log_id,
                                                        fault_operation=True)
                return msg

        except Exception as e:
            msg = f"Exception while exporting product {self.name} to QuickBooks: {str(e)}"
            self.message_post(body=msg)
            qb_log.generate_quickbooks_process_line(quickbooks_operation_name="product", quickbooks_operation_type="export",
                                                    instance=quickbook_instance.id,
                                                    quickbooks_operation_message=f"Exception: {str(e)}",
                                                        process_request_message=payload, process_response_message=str(e),
                                                    log_id=log_id, fault_operation=True)
            return msg


    def export_product_to_quickbooks_ca(self,quickbook_instance):
        for product in self:
            product.export_product_to_qkca(quickbook_instance)


class ProductProduct(models.Model):
    _inherit = 'product.product'

    qkca_product_type = fields.Char(string="Quickbook Product Type ID",
                                    related='product_tmpl_id.qkca_product_type', store=True)
