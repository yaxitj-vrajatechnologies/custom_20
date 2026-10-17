# -*- coding: utf-8 -*-
from odoo import models
from odoo.exceptions import UserError
import requests


class XeroAPIVts(models.AbstractModel):
    _name = "xero.api.vts"
    _description = "Xero API Request"

    def get_xero_header(self, token, tenant_id):
        return {
            "Authorization": f"Bearer {token}",
            "Xero-tenant-id": tenant_id,
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def xero_get_request(self, token, company_id, endpoint):
        try:
            response = requests.get(endpoint, headers=self.get_xero_header(token, company_id), timeout=10)
            return response.json(), response.status_code
        except requests.exceptions.ConnectionError:
            raise UserError("Connection Error: Please check your internet connection or Xero API endpoint.")
        except requests.exceptions.Timeout:
            raise UserError("Timeout Error: The request to Xero API took too long. Please try again later.")
        except requests.exceptions.HTTPError as e:
            raise UserError(f"HTTP Error: {str(e)}")
        except requests.exceptions.RequestException as e:
            raise UserError(f"Request Error: {str(e)}")

    def xero_post_request(self, token,company_id, endpoint, payload):
        try:
            response = requests.post(endpoint, headers=self.get_xero_header(token,company_id), json=payload, timeout=10)
            return response.json(), response.status_code
        except requests.exceptions.ConnectionError:
            raise UserError("Connection Error: Please check your internet connection or Xero API endpoint.")
        except requests.exceptions.Timeout:
            raise UserError("Timeout Error: The request to Xero API took too long. Please try again later.")
        except requests.exceptions.HTTPError as e:
            raise UserError(f"HTTP Error: {str(e)}")
        except requests.exceptions.RequestException as e:
            raise UserError(f"Request Error: {str(e)}")

    def xero_put_request(self, token,company_id,endpoint,payload):
        try:
            response = requests.put(endpoint, headers=self.get_xero_header(token,company_id), json=payload, timeout=10)
            return response.json(), response.status_code
        except requests.exceptions.ConnectionError:
            raise UserError("Connection Error: Please check your internet connection or Xero API endpoint.")
        except requests.exceptions.Timeout:
            raise UserError("Timeout Error: The request to Xero API took too long. Please try again later.")
        except requests.exceptions.HTTPError as e:
            raise UserError(f"HTTP Error: {str(e)}")
        except requests.exceptions.RequestException as e:
            raise UserError(f"Request Error: {str(e)}")

    def _get_import_operation_map(self):
        operation_map = {
            'import_customers':'Contacts',
            'import_accounts':'Accounts',
            'import_products':'Items',
            'import_taxes':'TaxRates',
            'import_invoice':'Invoices',
            'import_payment':'Payments',
            'import_creditnote':'CreditNotes',
            'import_analytic_account':'TrackingCategories',
            'import_contact_groups':'ContactGroups',
            'import_purchase_order':'PurchaseOrders',
            'import_prepayment': 'Prepayments',
            'import_overpayment':'Overpayments',
        }
        return operation_map

    def _get_xero_entity_filters(self):
        return {
            'Contacts': 'where=ContactStatus=="ACTIVE"',
            'Invoices': 'where=Status!="DELETED" AND Status!="VOIDED"',
            'Payments': 'where=Status!="DELETED"',
            'Prepayments': 'where=Status!="DELETED"' ,
            'Overpayments': 'where=Status!="DELETED"',
        }

    def get_data_from_xero(self, xero_url, company_id, token, operation, from_date=False, to_date=False):

        operation_map = self._get_import_operation_map()
        filter_map = self._get_xero_entity_filters()

        entity = operation_map.get(operation)
        query = filter_map.get(entity)
        date_filter = False
        if entity == 'Contacts':
            if from_date and to_date:
                date_filter = (
                    'UpdatedDateUTC >= DateTime({}) AND UpdatedDateUTC <= DateTime({})'
                ).format(from_date.strftime('%Y, %m, %d, %H, %M, %S'),to_date.strftime('%Y, %m, %d, %H, %M, %S'),)

            elif from_date:
                date_filter = 'UpdatedDateUTC >= DateTime({})'.format(
                    from_date.strftime('%Y, %m, %d, %H, %M, %S'))

            elif to_date:
                date_filter = 'UpdatedDateUTC <= DateTime({})'.format(
                    to_date.strftime('%Y, %m, %d, %H, %M, %S'))

        if date_filter:
            if query:
                query = f"{query} AND {date_filter}"
            else:
                query = f"where={date_filter}"

        if not entity:
            raise UserError(f"Unsupported operation: {operation}")

        endpoint = f"{entity}"
        request_url = f"{xero_url}/{endpoint}"

        if query:
            request_url = f"{request_url}?{query}"

        response_info, response_status = self.xero_get_request(token,company_id, request_url)

        return response_info, response_status
