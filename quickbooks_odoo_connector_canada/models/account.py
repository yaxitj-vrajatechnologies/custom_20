# -*- coding: utf-8 *-*
from odoo import models, fields

class Account(models.Model):
    _inherit = "account.account"

    is_export_error = fields.Boolean("Error in QuickBooks Export", default=False)
    is_account_qbca_exported = fields.Boolean(string="Exported Chart of Account", default=False)


    def action_qkca_instance_for_accounts(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Quickbook Canada Instance Wizard',
            'res_model': 'quickbook.instance.wizard',
            'view_mode': 'form',
            'target': 'new',
        }
    def _prepare_qkca_account_vals(self,account):
        account_type_map = {
            'asset_cash': 'Bank',
            'asset_current': 'Other Current Asset',
            'asset_fixed': 'Fixed Asset',
            'asset_receivable': 'Accounts Receivable',
            'equity': 'Equity',
            'expense': 'Expense',
            'expense_direct_cost': 'Cost of Goods Sold',
            'liability_payable': 'Accounts Payable',
            'liability_credit_card': 'Credit Card',
            'liability_non_current': 'Long Term Liability',
            'liability_current': 'Other Current Liability',
            'income': 'Income',
            'income_other': 'Other Income',
        }
        odoo_account_type = account_type_map.get(account.account_type)
        account_payload ={
            "Name": account.name,
            "AccountType": odoo_account_type,
            "AcctNum": account.code,
            "CurrencyRef": {"value": account.company_ids.currency_id.name}
        }

        if account.tax_ids:
            tax = account.tax_ids[0]
            tax_mapping = self.env['qbo.taxes.vts'].sudo().search([('tax_id','=',tax.id),('quickbook_tax_id','!=',False)],limit=1)
            if tax_mapping:
                account_payload["TaxCodeRef"] = {"value": tax_mapping.quickbook_tax_id,"name": tax_mapping.quickbook_tax_name}

        return account_payload, 'account'


    def export_account_to_qbk(self,account,quickbook_instance):
            if account.is_account_qbca_exported:
                account.message_post(body=f"Account already exported to QuickBooks.")
                return

            company = account.company_ids.id if account.company_ids else False

            if not quickbook_instance:
                account.message_post(body=f"No QuickBooks instance configured for {company} company.")
                return

            log_id = self.env['quickbooks.log.vts'].sudo().generate_quickbooks_logs(
                quickbooks_operation_name="chart_of_account", quickbooks_operation_type="export",
                instance=quickbook_instance.id,quickbooks_operation_message=f"Starting export for Charts of Account {account.name}"
            )

            account_payload, endpoint = self._prepare_qkca_account_vals(account)

            try:
                account_url = f"{quickbook_instance.quickbook_base_url}/{quickbook_instance.realm_id}/{endpoint}"

                response_json, status_code = self.env['quickbooks.api.vts'].sudo().qb_post_request(
                    quickbook_instance.access_token, account_url, account_payload)

                if status_code == 200:
                    account_data = response_json.get("Account", {})
                    qk_account_id = account_data.get("Id")
                    account.qk_classification = account_data.get("Classification", '')
                    account.qk_accountsubType = account_data.get("AccountSubType", '')
                    account.is_export_error = False
                    account.is_account_qbca_exported = True
                    account.message_post(body=f"Exported Charts of Account {account.name} to QuickBooks, ID: {qk_account_id}")
                    self.env['quickbooks.log.vts.line'].sudo().generate_quickbooks_process_line(
                        quickbooks_operation_name="chart_of_account", quickbooks_operation_type="export",
                        instance=quickbook_instance.id,
                        quickbooks_operation_message=f"Successfully exported Accounts {account.name}",
                        process_request_message=account_payload, process_response_message=response_json,
                        log_id=log_id)
                    return response_json
                else:
                    msg = f"Failed to export Account {account.name} to QuickBooks. Response: {response_json}"
                    account.message_post(body=msg)
                    account.is_export_error = True
                    self.env['quickbooks.log.vts.line'].sudo().generate_quickbooks_process_line(
                        quickbooks_operation_name="chart_of_account", quickbooks_operation_type="export",
                        instance=quickbook_instance.id, quickbooks_operation_message=msg,
                        process_request_message=account_payload, process_response_message=response_json,
                        log_id=log_id, fault_operation=True)
                    return None

            except Exception as e:
                account.message_post(body=f"Exception while exporting Charts Of Account {account.name} to QuickBooks: {str(e)}")
                account.is_export_error = True
                self.env['quickbooks.log.vts.line'].sudo().generate_quickbooks_process_line(
                    quickbooks_operation_name="chart_of_account", quickbooks_operation_type="export",
                    instance=quickbook_instance.id, quickbooks_operation_message=f"Exception: {str(e)}",
                    process_request_message=account_payload, process_response_message=str(e),
                    log_id=log_id, fault_operation=True)
            return None

    def export_account_to_quickbook_ca(self,quickbook_instance):
        for account in self:
            account.export_account_to_qbk(account,quickbook_instance)




