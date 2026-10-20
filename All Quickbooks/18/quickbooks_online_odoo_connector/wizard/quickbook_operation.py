from odoo import models, fields, api
from datetime import timedelta, datetime
import pprint

class QuickbooksWizardInherit(models.TransientModel):
    _inherit = "quickbooks.operations"

    import_operations = fields.Selection(selection_add=[("import_vendor","Import Vendor")])

    def qk_product_creation(self, product):
        product_type = product.get('Type')

        type_mapping = {
            'Inventory': (True, 'consu'),
            'NonInventory': (False, 'consu'),
            'Service': (False, 'service'),
            'Assembly': (False, 'combo'),
        }
        is_storable, qk_product_type = type_mapping.get(product_type, (False, 'consu'))

        def find_account(ref):
            return (self.env['qbo.account.vts'].sudo().search([('quickbook_account_id', '=', ref.get('value'))], limit=1) if ref else False)

        income_account = find_account(product.get('IncomeAccountRef'))
        expense_account = find_account(product.get('ExpenseAccountRef'))

        vendor_product = product.get('ExpenseAccountRef')

        product_val = {
            'name': product.get('Name', ''),
            'description_sale': product.get('Description', ''),
            'list_price': product.get('UnitPrice', 0.0),
            'standard_price': product.get('PurchaseCost', 0.0),
            'is_storable': is_storable,
            'type': qk_product_type,
            'qck_product_type': product_type,
            'quickbook_vendor_product': True if vendor_product else False,
            'property_account_income_id': income_account.account_id.id if income_account and income_account.account_id else False,
            'property_account_expense_id': expense_account.account_id.id if expense_account and expense_account.account_id else False,
        }

        product_detail = self.env['product.template'].sudo().create(product_val)

        return product_detail

    def get_product_from_quickbooks(self, product_info, product_status):

        if product_status == 200 and product_info and 'QueryResponse' in product_info:
            product_item = product_info.get('QueryResponse').get('Item')
            company = self.quickbook_instance_id.company_id.id if self.quickbook_instance_id.company_id else False

            log_id = self.env['quickbooks.log.vts'].sudo().generate_quickbooks_logs(
                quickbooks_operation_name='product',
                quickbooks_operation_type='import',
                instance=self.quickbook_instance_id.id if self.quickbook_instance_id else False,
                quickbooks_operation_message='Quickbooks to fetch Items')
            quickbook_map_product = []
            quickbook_map_product_log_ln = []
            product_mapped = False
            for product in product_item:

                if product.get('Type') == 'Category':
                    continue  

                qkb_product_name = product.get('Name', '').strip()
                qkb_product_id = product.get('Id', '')

                product_detail = False
                if qkb_product_name:
                    product_detail = self.env['product.template'].sudo().search([('name', '=', qkb_product_name),('company_id','=', company)], limit=1)

                pr_created = False
                if not product_detail and self.quickbook_instance_id.product_creation:
                    product_detail = self.qk_product_creation(product)
                    pr_created = True

                product_mapping = self.env['qbo.product.vts'].sudo().search([('quickbook_product_id', '=', qkb_product_id),('quickbook_instance_id', '=', self.quickbook_instance_id.id)],limit=1)

                def build_product_log(message, fault=False):
                    return {
                        'quickbooks_operation_name': 'product',
                        'quickbooks_operation_type': 'import',
                        'qkb_instance_id': self.quickbook_instance_id.id if self.quickbook_instance_id else False,
                        'quickbooks_operation_message': message,
                        'process_response_message': pprint.pformat(product),
                        'quickbooks_operation_id': log_id.id if log_id else False,
                        'fault_operation': fault
                    }

                if not product_mapping:
                    mapping_vals = {
                        'quickbook_instance_id': self.quickbook_instance_id.id if self.quickbook_instance_id else False,
                        'quickbook_product_id': qkb_product_id,
                        'quickbook_product_name': qkb_product_name,
                        'product_id': product_detail.id if product_detail else False,
                        'company_id': self.quickbook_instance_id.company_id.id if self.quickbook_instance_id.company_id else False,
                        'qbo_response': pprint.pformat(product),
                    }
                    quickbook_map_product.append(mapping_vals)
                    if not product_detail:
                        msg = f"Product doesn't match with QuickBooks Product: {qkb_product_name}"
                        quickbook_map_product_log_ln.append(build_product_log(msg, fault=True))

                    elif product_detail:
                        if pr_created:
                            msg = f"Product successfully created and mapped with QuickBooks product: {qkb_product_name}"
                        else:
                            msg = f"Product successfully mapped with QuickBooks product: {qkb_product_name}"

                        quickbook_map_product_log_ln.append(build_product_log(msg))
                else:
                    mapping_vals = {'qbo_response': pprint.pformat(product)}
                    product_mapping.sudo().write(mapping_vals)
                    msg = f"Product updated with QuickBooks product: {qkb_product_name}"
                    quickbook_map_product_log_ln.append(build_product_log(msg))

            if quickbook_map_product:
                product_mapped = self.env['qbo.product.vts'].sudo().create(quickbook_map_product)
            if quickbook_map_product_log_ln:
                product_map_logger = self.env['quickbooks.log.vts.line'].sudo().create(quickbook_map_product_log_ln)
            return product_mapped
        else:
            log_id = self.env['quickbooks.log.vts'].sudo().generate_quickbooks_logs(quickbooks_operation_name='product',
                quickbooks_operation_type='import',instance=self.quickbook_instance_id.id if self.quickbook_instance_id else False,
                quickbooks_operation_message='Failed to fetch Products'
            )
            log_line = self.env['quickbooks.log.vts.line'].sudo().generate_quickbooks_process_line(quickbooks_operation_name='product',
                quickbooks_operation_type='import',instance=self.quickbook_instance_id.id if self.quickbook_instance_id else False,
                quickbooks_operation_message='Error during products import process',
                process_response_message=pprint.pformat(product_info),log_id=log_id,fault_operation=True)

    ''' Vendor Creation Vals '''
    def qbk_vendor_creation(self, vendor):

        bill_addr = vendor.get('BillAddr', {})

        country_name = bill_addr.get('Country')
        country = self.env['res.country'].search([('name', '=', country_name)], limit=1)

        state_code = bill_addr.get('CountrySubDivisionCode')
        state = self.env['res.country.state'].search([('code', '=', state_code)], limit=1)

        parent_vendor = False
        is_company = True
        if vendor.get('ParentRef') and vendor.get('ParentRef').get('value'):
            parent_qk_id = vendor['ParentRef']['value']
            parent_vendor = self.env['qbo.vendor.map.vts'].sudo().search([('qbk_vendor_id', '=', parent_qk_id),('quickbook_instance_id','=',self.quickbook_instance_id.id)], limit=1)
            if not parent_vendor:
               parent_vendor = self.get_customer_vendor_from_qk(parent_qk_id, 'Vendor')
            is_company = False

        vendor_vals = {
            'name': vendor.get('DisplayName', '').strip() or vendor.get('CompanyName', '').strip(),
            'street': bill_addr.get('Line1', ''),
            'street2': bill_addr.get('Line2', ''),
            'state_id': state.id if state else False,
            'zip': bill_addr.get('PostalCode', ''),
            'country_id': country.id if country else False,
            'city': bill_addr.get('City', ''),
            'mobile': vendor.get('PrimaryPhone', {}).get('FreeFormNumber', ''),
            'email': vendor.get('PrimaryEmailAddr', {}).get('Address', ''),
            'is_company': is_company,
            'parent_id': parent_vendor.vendor_id.id if parent_vendor and parent_vendor.vendor_id else False,
        }
        vendor_detail = self.env['res.partner'].create(vendor_vals)
        return vendor_detail

    ''' Importing Vendor From Quickbooks '''
    def get_vendor_from_quickbooks(self, vendor_info, vendor_status):

        if vendor_status == 200 and vendor_info and 'QueryResponse' in vendor_info:
            vendor_details = vendor_info.get('QueryResponse').get('Vendor')

            log_id = self.env['quickbooks.log.vts'].sudo().generate_quickbooks_logs(
                quickbooks_operation_name='vendor', quickbooks_operation_type='import',
                instance=self.quickbook_instance_id.id if self.quickbook_instance_id else False,
                quickbooks_operation_message='Quickbooks to fetch Vendors')

            quickbook_map_vendor = []
            quickbook_map_vendor_log_ln = []

            for vendor in vendor_details:
                qkb_vendor_name = vendor.get('DisplayName').strip()
                qkb_vendor_id = vendor.get('Id', '')
                qkb_vnd_email = vendor.get('PrimaryEmailAddr', {}).get('Address', '')

                vendor_detail = False

                if qkb_vendor_name:
                    vendor_detail = self.env['res.partner'].sudo().search([('name', '=', qkb_vendor_name)], limit=1)
                if vendor_detail and vendor_detail.email and qkb_vnd_email:
                    partner_email = vendor_detail.email.strip()
                    qbk_email = qkb_vnd_email.strip()
                    if partner_email == qbk_email:
                        vendor_detail = vendor_detail
                    else:
                        vendor_detail = False


                vendor_created = False
                if not vendor_detail and self.quickbook_instance_id.vendor_creation:
                    vendor_detail = self.qbk_vendor_creation(vendor)
                    vendor_created = True

                vendor_mapping = self.env['qbo.vendor.map.vts'].sudo().search(
                    [('qbk_vendor_id', '=', qkb_vendor_id),('quickbook_instance_id', '=', self.quickbook_instance_id.id)], limit=1)

                def build_vendor_log(message, fault=False):
                    return {
                        'quickbooks_operation_name': 'vendor',
                        'quickbooks_operation_type': 'import',
                        'qkb_instance_id': self.quickbook_instance_id.id if self.quickbook_instance_id else False,
                        'quickbooks_operation_message': message,
                        'process_response_message': pprint.pformat(vendor),
                        'quickbooks_operation_id': log_id.id if log_id else False,
                        'fault_operation': fault
                    }

                if not vendor_mapping:
                    mapping_vals = {
                        'qbk_vendor_name': qkb_vendor_name,
                        'qbk_vendor_id': qkb_vendor_id,
                        'quickbook_instance_id': self.quickbook_instance_id.id if self.quickbook_instance_id else False,
                        'vendor_id': vendor_detail.id if vendor_detail else False,
                        'company_id': self.quickbook_instance_id.company_id.id if self.quickbook_instance_id.company_id else self.env.company.id,
                        'qbo_response': pprint.pformat(vendor),
                    }
                    quickbook_map_vendor.append(mapping_vals)
                    if not vendor_detail:
                        msg = f"Vendor doesn't match with QuickBooks Vendor: {qkb_vendor_name}"
                        quickbook_map_vendor_log_ln.append(build_vendor_log(msg, fault=True))

                    elif vendor_detail:
                        if vendor_created:
                            msg = f"Vendor successfully created and mapped with QuickBooks vendor: {qkb_vendor_name}"
                        else:
                            msg = f"Vendor successfully mapped with QuickBooks Vendor: {qkb_vendor_name}"

                        quickbook_map_vendor_log_ln.append(build_vendor_log(msg))
                else:
                    mapping_vals = {'qbo_response': pprint.pformat(vendor)}
                    vendor_mapping.sudo().write(mapping_vals)
                    msg = f"Vendor updated with QuickBooks Vendor: {qkb_vendor_name}"
                    quickbook_map_vendor_log_ln.append(build_vendor_log(msg))

            if quickbook_map_vendor:
                vendor_mapped = self.env['qbo.vendor.map.vts'].sudo().create(quickbook_map_vendor)
            if quickbook_map_vendor_log_ln:
                vendor_map_logger = self.env['quickbooks.log.vts.line'].sudo().create(quickbook_map_vendor_log_ln)
            return vendor_mapped
        else:
            log_id = self.env['quickbooks.log.vts'].sudo().generate_quickbooks_logs(
                quickbooks_operation_name='vendor',
                quickbooks_operation_type='import',
                instance=self.quickbook_instance_id.id if self.quickbook_instance_id else False,
                quickbooks_operation_message='Failed to fetch Vendor'
            )
            log_line = self.env['quickbooks.log.vts.line'].sudo().generate_quickbooks_process_line(
                quickbooks_operation_name='vendor',
                quickbooks_operation_type='import',
                instance=self.quickbook_instance_id.id if self.quickbook_instance_id else False,
                quickbooks_operation_message='Error during vendor import process',
                process_response_message=pprint.pformat(vendor_info), log_id=log_id, fault_operation=True)
