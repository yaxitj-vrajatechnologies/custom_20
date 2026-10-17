from odoo import models
import pprint


class Account(models.Model):
    _inherit = "account.account"

    def write(self, vals):

        trigger_update = any(field in vals for field in ['name', 'code', 'account_type', 'tax_ids'])

        res = super(Account, self).write(vals)

        if not trigger_update:
            return res

        xero_instances = self.env['xero.connect'].search([('state', '=', 'connected')])

        for account in self:
            for xero_instance in xero_instances:
                if hasattr(account, 'company_ids') and xero_instance.company_id not in account.company_ids:
                    continue

                account_mapping = self.env['xero.account.map'].sudo().search(
                    [('xero_instance_id', '=', xero_instance.id), ('account_id', '=', account.id)], limit=1)

                if not account_mapping:
                    continue

                account_payload = self._prepare_xero_account_vals(account)
                account_payload['AccountID'] = account_mapping.xero_account_id

                try:
                    account_url = f"{xero_instance.xero_base_url}/Accounts/{account_mapping.xero_account_id}"

                    response_json, status_code = self.env['xero.api.vts'].sudo().xero_post_request(
                        xero_instance.access_token,
                        xero_instance.tenant_id, account_url, account_payload)

                    if status_code == 200:
                        account.message_post(
                            body=f"Updated Charts of Account {account.name} in Xero, ID: {account_mapping.xero_account_id}")
                    else:
                        account.message_post(
                            body=f"Failed to update Account {account.name} in Xero. Response: {response_json}")

                except Exception as e:
                    account.message_post(
                        body=f"Exception while updating Charts of Account {account.name} in Xero: {str(e)}")

        return res

    def action_xero_instance_for_accounts(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Xero Instance Wizard',
            'res_model': 'xero.instance.wizard',
            'view_mode': 'form',
            'target': 'new',
        }

    def _prepare_xero_account_vals(self, account):
        account_type_map = {
            'asset_cash': 'BANK',
            'asset_current': 'CURRENT',
            'asset_fixed': 'FIXED',
            'asset_non_current': 'NONCURRENT',
            'asset_prepayments': 'PREPAYMENT',
            'asset_receivable': 'CURRENT',
            'liability_payable': 'CURRLIAB',
            'liability_current': 'CURRLIAB',
            'liability_non_current': 'TERMLIAB',
            'liability_credit_card': 'CURRLIAB',
            'equity': 'EQUITY',
            'equity_unaffected': 'EQUITY',
            'income': 'REVENUE',
            'income_other': 'OTHERINCOME',
            'expense': 'EXPENSE',
            'expense_direct_cost': 'DIRECTCOSTS',
            'expense_depreciation': 'DEPRECIATN',
        }

        odoo_account_type = account_type_map.get(account.account_type)
        account_payload = {
            "Name": account.name,
            "Type": odoo_account_type,
            "Code": account.code,
        }

        if odoo_account_type == "BANK":
            bank_account_number = account.company_ids[:1].partner_id.bank_ids[:1].account_number
            if bank_account_number:
                account_payload["BankAccountNumber"] = bank_account_number
            else:
                account.message_post(body="No bank account number found for this BANK account while exporting to Xero.")
                return None
        if account.tax_ids:
            tax = account.tax_ids[0]
            tax_mapping = self.env['xero.tax.map'].sudo().search(
                [('tax_id', '=', tax.id), ('xero_tax_id', '!=', False)], limit=1)
            if tax_mapping:
                account_payload["TaxType"] = tax_mapping.xero_tax_id

        return account_payload

    def export_account_to_xero(self, account, xero_instance):
        account_mapping = self.env['xero.account.map'].sudo().search(
            [('xero_instance_id', '=', xero_instance.id), ('account_id', '=', account.id)], limit=1)
        if account_mapping:
            account.message_post(body=f"Account already exported to Xero.")
            return

        log_id = self.env['xero.log.vts'].sudo().generate_xero_logs(
            xero_operation_name="account", xero_operation_type="export",
            instance=xero_instance.id, xero_operation_message=f"Starting export for Charts of Account {account.name}")

        account_payload = self._prepare_xero_account_vals(account)
        if not account_payload:
            return None

        try:
            account_url = f"{xero_instance.xero_base_url}/Accounts"

            response_json, status_code = self.env['xero.api.vts'].sudo().xero_put_request(
                xero_instance.access_token, xero_instance.tenant_id, account_url, account_payload)
            if status_code == 200:
                account_data = response_json.get("Accounts", {})
                xero_account_id = account_data[0].get('AccountID')
                account_mapping_val = {
                    'xero_instance_id': xero_instance.id,
                    'xero_account_id': xero_account_id,
                    'xero_account_name': account.name,
                    'account_id': account.id,
                    'xero_account_code': account.code,
                    'xero_response': pprint.pformat(response_json)
                }
                account_mapping = self.env['xero.account.map'].sudo().create(account_mapping_val)
                account.message_post(body=f"Exported Charts of Account {account.name} to Xero, ID: {xero_account_id}")
                self.env['xero.log.vts.line'].sudo().generate_xero_process_line(
                    xero_operation_name="account", xero_operation_type="export",
                    instance=xero_instance.id, xero_operation_message=f"Successfully exported Accounts {account.name}",
                    process_request_message=account_payload, process_response_message=response_json,
                    log_id=log_id)
                return account_mapping
            else:
                res_error = response_json.get('Message', response_json)
                msg = f"Failed to export Charts Of Account {account.name} to Xero. Response: {res_error}"
                account.message_post(body=msg)
                self.env['xero.log.vts.line'].sudo().generate_xero_process_line(
                    xero_operation_name="account", xero_operation_type="export",
                    instance=xero_instance.id, xero_operation_message=msg,
                    process_request_message=account_payload, process_response_message=response_json,
                    log_id=log_id, fault_operation=True)
                return None
        except Exception as e:
            account.message_post(body=f"Exception while exporting Charts Of Account {account.name} to Xero: {str(e)}")
            self.env['xero.log.vts.line'].sudo().generate_xero_process_line(
                xero_operation_name="account", xero_operation_type="export",
                instance=xero_instance.id, xero_operation_message=f"Exception: {str(e)}",
                process_request_message=account_payload, process_response_message=str(e),
                log_id=log_id, fault_operation=True)
        return None

    def export_charts_of_account_to_xero(self, xero_instance):
        for account in self:
            account.export_account_to_xero(account, xero_instance)
