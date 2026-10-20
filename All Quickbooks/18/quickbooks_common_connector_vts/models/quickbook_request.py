# -*- coding: utf-8 -*-
from odoo import models
from odoo.exceptions import UserError
import requests


class QuickbooksAPIVts(models.AbstractModel):
    _name = "quickbooks.api.vts"
    _description = "QuickBooks API"

    def _get_quick_book_header(self, token):
        return {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "Content-Type": "application/json"
        }

    def qb_get_request(self, token, endpoint):
        try:
            response = requests.get(endpoint, headers=self._get_quick_book_header(token), timeout=10)
            response.raise_for_status()
            return response.json(), response.status_code
        except requests.exceptions.ConnectionError:
            raise UserError("Connection Error: Please check your internet connection or QuickBooks API endpoint.")
        except requests.exceptions.Timeout:
            raise UserError("Timeout Error: The request to QuickBooks API took too long. Please try again later.")
        except requests.exceptions.HTTPError as e:
            raise UserError(f"HTTP Error: {str(e)}")
        except requests.exceptions.RequestException as e:
            raise UserError(f"Request Error: {str(e)}")

    def qb_post_request(self, token, endpoint, payload):
        try:
            response = requests.post(endpoint, headers=self._get_quick_book_header(token), json=payload, timeout=10)
            response.raise_for_status()
            return response.json(), response.status_code
        except requests.exceptions.ConnectionError:
            raise UserError("Connection Error: Please check your internet connection or QuickBooks API endpoint.")
        except requests.exceptions.Timeout:
            raise UserError("Timeout Error: The request to QuickBooks API took too long. Please try again later.")
        except requests.exceptions.HTTPError as e:
            raise UserError(f"HTTP Error: {str(e)}")
        except requests.exceptions.RequestException as e:
            raise UserError(f"Request Error: {str(e)}")

    def get_tax_rates(self, qck_url, company_id, token):
        query = "SELECT * FROM TaxRate"
        endpoint = f"{company_id}/query"
        url = f"{qck_url}/{endpoint}?query={query}"

        tax_rate_response, status = self.qb_get_request(token, url)
        tax_rates = tax_rate_response.get('QueryResponse', {}).get('TaxRate', [])
        
        return {
            tr['Id']: {"name": tr.get('Name'),
                        "rateValue": tr.get('RateValue'),
                        "agency": tr.get('AgencyRef', {}).get('value')} for tr in tax_rates}

    def get_customer_types(self, qck_url, company_id, token):
        query = "SELECT * FROM CustomerType"
        endpoint = f"{company_id}/query"
        url = f"{qck_url}/{endpoint}?query={query}"

        customer_types_response, status = self.qb_get_request(token, url)
        customer_types = customer_types_response.get('QueryResponse', {}).get('CustomerType', [])
        return {ct['Id']: ct['Name'] for ct in customer_types}

    def _get_operation_map(self):
        operation_map = {
            'import_customers': 'Customer',
            'import_payment_terms': 'TERM',
            'import_taxes': 'TaxCode',
            'import_account': 'Account',
            'import_product': 'Item',
            'import_payment_method':'paymentmethod',
            'import_vendor':'Vendor'}
            
        return operation_map

    def get_data_from_quickbooks(self, qck_url, company_id, token, operation, from_date=None, to_date=None):
        
        operation_map = self._get_operation_map()

        entity = operation_map.get(operation)

        start = 1
        page_size = 1000

        if not entity:
            raise UserError(f"Unsupported operation: {operation}")

        query = f"SELECT * FROM {entity}"

        if operation == "import_pro_category":
            query += " WHERE Type = 'Category'"
            if from_date and to_date:
                query += f" AND MetaData.CreateTime >= '{from_date}' AND MetaData.CreateTime <= '{to_date}'"
        else:
            if from_date and to_date:
                query += f" WHERE MetaData.CreateTime >= '{from_date}' AND MetaData.CreateTime <= '{to_date}'"


        query += f" startposition {start} maxresults {page_size}"
        endpoint = f"{company_id}/query"
        request_url = f"{qck_url}/{endpoint}?query={query}"

        response_info, response_status = self.qb_get_request(token, request_url)

        return response_info, response_status
