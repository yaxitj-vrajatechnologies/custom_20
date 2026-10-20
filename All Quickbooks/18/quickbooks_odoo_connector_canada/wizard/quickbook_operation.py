from odoo import models, fields, api, _
import pprint
import requests
from odoo.exceptions import UserError


class QuickbooksWizardInherit(models.TransientModel):
    _inherit = "quickbooks.operations"

    import_operations = fields.Selection(
        selection_add=[("import_invoice", "Import Invoice (Canada)"),
                       ('import_vendor_bill', 'Import Bills (Canada)'), ('import_customer_payment', 'Import Customer Payment (Canada)'),
                       ('import_billpayment', 'Import Bill Payment (Canada)')])

    def _prepare_product_creation(self, product):
        product_type = product.get('Type')

        type_mapping = {
            'Inventory': (True, 'consu'),
            'NonInventory': (False, 'consu'),
            'Service': (False, 'service'),
            'Assembly': (False, 'combo'),
        }

        is_storable, qk_product_type = type_mapping.get(product_type, (False, 'consu'))

        def find_account(ref):
            return (self.env['qbo.account.vts'].sudo().search([('quickbook_account_id', '=', ref.get('value')),('quickbook_instance_id', '=', self.quickbook_instance_id.id),
                                                        ('company_id', '=', self.quickbook_instance_id.company_id.id)],limit=1) if ref else False)

        income_account = find_account(product.get('IncomeAccountRef'))
        expense_account = find_account(product.get('ExpenseAccountRef'))
        vendor_product = product.get('ExpenseAccountRef')
        parent_ref = product.get('ParentRef')
        category=False
        if parent_ref:
            category = self.env['product.category'].sudo().search([('qkca_category_ID', '=',parent_ref.get('value'))],limit=1)
            if not category:
                type = "Category"
                item_ref = parent_ref.get('value')
                category = self._get_product_from_quickbooks(item_ref, type)

        product_val = {
            'name': product.get('Name', ''),
            'description_sale': product.get('Description', ''),
            'list_price': product.get('UnitPrice', 0.0),
            'standard_price': product.get('PurchaseCost', 0.0),
            'is_storable': is_storable,
            'type': qk_product_type,
            'qkca_product_type': product_type,
            'quickbook_vendor_product': True if vendor_product else False,
            'property_account_income_id': (income_account.account_id.id if income_account and income_account.account_id else False),
            'property_account_expense_id': (expense_account.account_id.id if expense_account and expense_account.account_id else False),
            'categ_id': category.id if category else self.env['product.category'].search([], limit=1).id,
        }

        product_detail = self.env['product.template'].sudo().create(product_val)

        return product_detail

    def get_ca_product_from_quickbooks(self, product_info, product_status):

        if product_status == 200 and product_info and 'QueryResponse' in product_info:
            product_item = product_info.get('QueryResponse').get('Item')
            company = self.quickbook_instance_id.company_id.id if self.quickbook_instance_id.company_id else False

            log_id = self.env['quickbooks.log.vts'].sudo().generate_quickbooks_logs(
                quickbooks_operation_name='product', quickbooks_operation_type='import',
                instance=self.quickbook_instance_id.id if self.quickbook_instance_id else False,
                quickbooks_operation_message='Quickbooks to fetch Items')

            quickbook_map_product = []
            quickbook_map_product_log_ln = []
            for product in product_item:

                if product.get('Type') == 'Category':
                    continue

                qkb_product_name = product.get('Name', '').strip()
                qkb_product_id = product.get('Id', '')

                product_detail = False
                if qkb_product_name:
                    product_detail = self.env['product.template'].sudo().search([('name', '=', qkb_product_name), ('company_id', '=', company)], limit=1)

                pr_created = False
                if not product_detail and self.quickbook_instance_id.qkca_product_creation:
                        product_detail = self._prepare_product_creation(product)
                        pr_created = True

                product_mapping = self.env['qbo.product.ca.map.vts'].sudo().search(
                    [('quickbook_product_id', '=', qkb_product_id),('quickbook_instance_id', '=', self.quickbook_instance_id.id),('company_id', '=', company)], limit=1)

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
                        'company_id': self.quickbook_instance_id.company_id.id if self.quickbook_instance_id.company_id else self.env.company.id,
                        'qbo_response': pprint.pformat(product),
                    }
                    quickbook_map_product.append(mapping_vals)
                    if not product_detail:
                        msg =  f"Product doesn't match with QuickBooks Product : {qkb_product_name}"
                        quickbook_map_product_log_ln.append(build_product_log(msg, fault=True))

                    elif product_detail:
                        opr_message = f"Product successfully mapped with QuickBooks product: {qkb_product_name}"
                        if pr_created:
                            opr_message = f"Product successfully created and mapped with QuickBooks product: {qkb_product_name}"
                        quickbook_map_product_log_ln.append(build_product_log(opr_message, fault=False))
                else:
                    mapping_vals = {
                        'product_id': product_detail.id if product_detail else False,
                        'qbo_response': pprint.pformat(product),
                    }
                    product_mapping.sudo().write(mapping_vals)
                    opr_message=f"Product updated with QuickBooks product: {qkb_product_name}"
                    quickbook_map_product_log_ln.append(build_product_log(opr_message, fault=False))

            if quickbook_map_product:
                product_mapped = self.env['qbo.product.ca.map.vts'].sudo().create(quickbook_map_product)
            if quickbook_map_product_log_ln:
                product_map_logger = self.env['quickbooks.log.vts.line'].sudo().create(quickbook_map_product_log_ln)
            return qkb_product_id
        else:
            log_id = self.env['quickbooks.log.vts'].sudo().generate_quickbooks_logs(quickbooks_operation_name='product',
                quickbooks_operation_type='import',instance=self.quickbook_instance_id.id if self.quickbook_instance_id else False,
                quickbooks_operation_message='Failed to fetch Products')
            log_line = self.env['quickbooks.log.vts.line'].sudo().generate_quickbooks_process_line(
                quickbooks_operation_name='product',quickbooks_operation_type='import',
                instance=self.quickbook_instance_id.id if self.quickbook_instance_id else False,
                quickbooks_operation_message='Error during products import process',
                process_response_message=pprint.pformat(product_info), log_id=log_id, fault_operation=True)

    def qbk_ca_vendor_creation(self, vendor):

        bill_addr = vendor.get('BillAddr', {})

        country_name = bill_addr.get('Country')
        country = self.env['res.country'].search([('name', '=', country_name)], limit=1)

        state_code = bill_addr.get('CountrySubDivisionCode')
        state = self.env['res.country.state'].search([('code', '=', state_code)], limit=1)

        parent_vendor = False
        is_company = True
        if vendor.get('ParentRef') and vendor.get('ParentRef').get('value'):
            parent_qk_id = vendor['ParentRef']['value']
            parent_vendor = self.env['qbo.vendor.ca.map.vts'].sudo().search([('quickbook_vendor_id', '=', parent_qk_id),('quickbook_instance_id','=',self.quickbook_instance_id.id)], limit=1)
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

    def get_vendor_from_quickbooks_ca(self, vendor_info, vendor_status):

        if vendor_status == 200 and vendor_info and 'QueryResponse' in vendor_info:
            vendor_details = vendor_info.get('QueryResponse').get('Vendor')
            # company = self.quickbook_instance_id.company_id.id if self.quickbook_instance_id.company_id else False

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
                    vendor_detail = self.env['res.partner'].sudo().search(
                        [('name', '=', qkb_vendor_name)], limit=1)
                if vendor_detail and vendor_detail.email:
                    partner_email = vendor_detail.email.strip() if vendor_detail.email else ''
                    qbk_email = qkb_vnd_email.strip() if qkb_vnd_email else ''
                    if partner_email == qbk_email:
                        vendor_detail = vendor_detail
                    else:
                        vendor_detail = False

                vendor_created = False
                if not vendor_detail and self.quickbook_instance_id.qkca_vendor_creation:
                    vendor_detail = self.qbk_ca_vendor_creation(vendor)
                    vendor_created = True

                vendor_mapping = self.env['qbo.vendor.ca.map.vts'].sudo().search(
                    [('quickbook_vendor_id', '=', qkb_vendor_id),('quickbook_instance_id', '=', self.quickbook_instance_id.id)], limit=1)

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
                        'quickbook_vendor_name': qkb_vendor_name,
                        'quickbook_vendor_id': qkb_vendor_id,
                        'quickbook_instance_id': self.quickbook_instance_id.id if self.quickbook_instance_id else False,
                        'vendor_id': vendor_detail.id if vendor_detail else False,
                        'company_id': self.quickbook_instance_id.company_id.id if self.quickbook_instance_id.company_id else self.env.company.id,
                        'qbo_response': pprint.pformat(vendor),
                    }
                    quickbook_map_vendor.append(mapping_vals)
                    if not vendor_detail:
                        msg= f"Vendor doesn't match with QuickBooks Vendor: {qkb_vendor_name}"
                        quickbook_map_vendor_log_ln.append(build_vendor_log(msg, fault=True))

                    elif vendor_detail:

                        if vendor_created:
                            vc_message = f"Vendor successfully created and mapped with QuickBooks vendor: {qkb_vendor_name}"
                        else:
                            vc_message = f"Vendor successfully mapped with QuickBooks Vendor: {qkb_vendor_name}"
                        quickbook_map_vendor_log_ln.append(build_vendor_log(vc_message))
                else:
                    mapping_vals = {
                        'vendor_id': vendor_detail.id if vendor_detail else False,
                        'qbo_response': pprint.pformat(vendor),
                    }
                    vendor_mapping.sudo().write(mapping_vals)
                    msg=f"Vendor updated with QuickBooks Vendor: {qkb_vendor_name}"
                    quickbook_map_vendor_log_ln.append(build_vendor_log(msg))

            if quickbook_map_vendor:
                vendor_mapped = self.env['qbo.vendor.ca.map.vts'].sudo().create(quickbook_map_vendor)
            if quickbook_map_vendor_log_ln:
                vendor_map_logger = self.env['quickbooks.log.vts.line'].sudo().create(quickbook_map_vendor_log_ln)
            return qkb_vendor_id
        else:
            log_id = self.env['quickbooks.log.vts'].sudo().generate_quickbooks_logs(
                quickbooks_operation_name='vendor',quickbooks_operation_type='import',
                instance=self.quickbook_instance_id.id if self.quickbook_instance_id else False,
                quickbooks_operation_message='Failed to fetch Vendor'
            )
            log_line = self.env['quickbooks.log.vts.line'].sudo().generate_quickbooks_process_line(
                quickbooks_operation_name='vendor',
                quickbooks_operation_type='import',
                instance=self.quickbook_instance_id.id if self.quickbook_instance_id else False,
                quickbooks_operation_message='Error during vendor import process',
                process_response_message=pprint.pformat(vendor_info), log_id=log_id, fault_operation=True)

    def _prepare_category_creation(self, category_data):

        ProductCategory = self.env['product.category'].sudo()

        qkb_category_id = category_data.get('Id')
        qkb_category_name = category_data.get('Name', '').strip()

        category = ProductCategory.search(
            ['|', ('name', '=', qkb_category_name), ('qkca_category_ID', '=', qkb_category_id)], limit=1)
        if category:
            return category

        parent_category = False
        parent_ref = category_data.get('ParentRef')
        if parent_ref:
            parent_category = ProductCategory.search([('qkca_category_ID', '=', parent_ref.get('value'))], limit=1)
            if not parent_category:
                parent_category = self._prepare_category_creation({'Id': parent_ref.get('value'),
                                                                   'Name': parent_ref.get('name'), })

        category_vals = {
            'name': qkb_category_name,
            'qkca_category_ID': qkb_category_id,
            'parent_id': parent_category.id if parent_category else False,
            'qck_instance_id': self.quickbook_instance_id.id if self.quickbook_instance_id else False,
        }
        category = ProductCategory.create(category_vals)

        return category

    def get_category_from_quickbooks(self, category_info, category_status):

        if category_status == 200 and category_info and 'QueryResponse' in category_info:
            category_items = category_info['QueryResponse'].get('Item', [])

            for category in category_items:
                qkb_category_name = (category.get('Name') or '').strip()
                qkb_category_id = category.get('Id')

                category_detail = False
                if qkb_category_name:
                    category_detail = self.env['product.category'].sudo().search([
                        '|', ('name', '=', qkb_category_name), ('qkca_category_ID', '=', qkb_category_id),('qck_instance_id','=',self.quickbook_instance_id.id)
                    ], limit=1)

                if not category_detail:
                    category_detail = self._prepare_category_creation(category)

            return category_detail

        else:
            log_id = self.env['quickbooks.log.vts'].sudo().generate_quickbooks_logs(
                quickbooks_operation_name='product_category', quickbooks_operation_type='import',
                instance=self.quickbook_instance_id.id if self.quickbook_instance_id else False,
                quickbooks_operation_message='Failed to fetch Categories')

            self.env['quickbooks.log.vts.line'].sudo().generate_quickbooks_process_line(
                quickbooks_operation_name='product_category', quickbooks_operation_type='import',
                instance=self.quickbook_instance_id.id if self.quickbook_instance_id else False,
                quickbooks_operation_message='Error during categories import process',
                process_response_message=pprint.pformat(category_info), log_id=log_id, fault_operation=True)

    def _get_taxes_from_quickbooks(self, line):
        tax_ids = []
        tax_ref = line.get('SalesItemLineDetail', {}).get('TaxCodeRef', {}).get('value')
        if tax_ref:
            tax = self.env['qbo.taxes.vts'].sudo().search([('quickbook_tax_id', '=', tax_ref),('quickbook_instance_id', '=', self.quickbook_instance_id.id)], limit=1)
            if tax and tax.tax_id.id:
                tax_ids.append(tax.tax_id.id)
        return tax_ids

    def _prepare_invoice_creation(self, invoice, customer):

        invoice_lines = []
        for line in invoice.get('Line', []):
            if line.get('DetailType') == 'SalesItemLineDetail':
                item_ref = line['SalesItemLineDetail'].get('ItemRef', {}).get('value')
                product = self.env['qbo.product.ca.map.vts'].sudo().search([('quickbook_product_id', '=', item_ref),('quickbook_instance_id','=',self.quickbook_instance_id.id)], limit=1)
                if not product:
                    type="Product"
                    qkb_product_id = self._get_product_from_quickbooks(item_ref, type)
                    product = self.env['qbo.product.ca.map.vts'].sudo().search([('quickbook_product_id', '=', qkb_product_id),('quickbook_instance_id', '=',self.quickbook_instance_id.id)],limit=1)

                invoice_lines.append((0, 0, {
                    'product_id': product.product_id.id,
                    'name': line.get('Description', product.product_id.name),
                    'quantity': line['SalesItemLineDetail'].get('Qty', 1),
                    'price_unit': line['SalesItemLineDetail'].get('UnitPrice', 0),
                    'tax_ids': [(6, 0, self._get_taxes_from_quickbooks(line))]
                }))

        currency = None
        currency_code = invoice.get('CurrencyRef', {}).get('value')
        if currency_code:
            currency = self.env['res.currency'].sudo().search([('name', '=', currency_code)], limit=1)

        payment_term = None
        term_ref = invoice.get('SalesTermRef', {}).get('value')
        if term_ref:
            payment_term = self.env['qbo.payment.terms.vts'].sudo().search([('quickbook_payment_id', '=', term_ref),('quickbook_instance_id', '=', self.quickbook_instance_id.id)],limit=1)

        vals = {
            'qck_instance_id': self.quickbook_instance_id.id if self.quickbook_instance_id else False,
            'move_type': 'out_invoice',
            'partner_id': customer.partner_id.id if customer and customer.partner_id else False,
            'invoice_date': invoice.get('TxnDate'),
            'invoice_date_due': invoice.get('DueDate'),
            'ref': invoice.get('DocNumber'),
            'invoice_line_ids': invoice_lines,
            'narration': invoice.get('CustomerMemo', {}).get('value'),
            'qkca_invoice_ID': invoice.get('Id'),
            'qck_invoice_doc': invoice.get('DocNumber'),
            'company_id':self.quickbook_instance_id.company_id.id if self.quickbook_instance_id.company_id else False
        }

        if currency:
            vals['currency_id'] = currency.id
        if payment_term:
            vals['invoice_payment_term_id'] = payment_term.payment_id.id

        invoice_detail = self.env['account.move'].with_context(skip_update=True).sudo().create(vals)

        return invoice_detail

    def get_invoice_from_quickbooks(self, invoice_info, invoice_status):
        if invoice_status == 200 and invoice_info and 'QueryResponse' in invoice_info:
            invoice_items = invoice_info['QueryResponse'].get('Invoice', [])
            instance_id = getattr(self.quickbook_instance_id, 'id', False)
            company_id = self.quickbook_instance_id.company_id.id if self.quickbook_instance_id.company_id else self.env.company.id

            log_id = self.env['quickbooks.log.vts'].sudo().generate_quickbooks_logs(
                quickbooks_operation_name='invoice', quickbooks_operation_type='import',
                instance=instance_id, quickbooks_operation_message='QuickBooks to fetch invoices')

            quickbook_map_invoice, quickbook_map_invoice_log_ln = [], []

            for invoice in invoice_items:
                qkb_invoice_id = invoice.get('Id')
                qkb_invoice_number = invoice.get('DocNumber')
                qkb_customer_ref = invoice.get('CustomerRef', {}).get('value')

                invoice_detail = False
                if qkb_invoice_id:
                    invoice_detail = self.env['account.move'].sudo().search([('move_type', '=', 'out_invoice'),('qkca_invoice_ID', '=', qkb_invoice_id), ('qck_instance_id','=', self.quickbook_instance_id.id)], limit=1)

                customer = False
                if qkb_customer_ref:
                    customer = self.env['qbo.partner.map.vts'].sudo().search([('quickbook_id', '=', qkb_customer_ref),('quickbook_instance_id','=',self.quickbook_instance_id.id)], limit=1)

                if not customer:
                    cust_type = "Customer"
                    customer_id = self._get_customer_or_vendor_from_qkca(qkb_customer_ref,cust_type)
                    customer = self.env['qbo.partner.map.vts'].sudo().search([('quickbook_id', '=', customer_id),('quickbook_instance_id','=',self.quickbook_instance_id.id)], limit=1)
                    quickbook_map_invoice_log_ln.append({
                        'quickbooks_operation_name': 'customer', 'quickbooks_operation_type': 'import',
                        'qkb_instance_id': instance_id,
                        'quickbooks_operation_message': "Customer Successfully Imported from Quickbook.",
                        'process_response_message': pprint.pformat(invoice),
                        'quickbooks_operation_id': log_id.id if log_id else False,})

                inv_created = False
                if not invoice_detail and self.quickbook_instance_id.qkca_invoice_creation and customer:
                    invoice_detail = self._prepare_invoice_creation(invoice, customer)
                    inv_created = True

                invoice_mapping = self.env['qbo.invoice.map.vts'].sudo().search([('qbk_invoice_id', '=', qkb_invoice_id),('quickbook_instance_id','=', self.quickbook_instance_id.id)], limit=1)

                def build_invoice_log(message, fault=False):
                    return {
                        'quickbooks_operation_name': 'invoice',
                        'quickbooks_operation_type': 'import',
                        'qkb_instance_id': self.quickbook_instance_id.id if self.quickbook_instance_id else False,
                        'quickbooks_operation_message': message,
                        'process_response_message': pprint.pformat(invoice),
                        'quickbooks_operation_id': log_id.id if log_id else False,
                        'fault_operation': fault
                    }

                if not invoice_mapping:
                    invoice_vals = {
                        'quickbook_instance_id': instance_id,
                        'qbk_invoice_id': qkb_invoice_id,
                        'quickbook_invoice_number': qkb_invoice_number,
                        'customer_id': customer.partner_id.id if customer and customer.partner_id else False,
                        'invoice_id': invoice_detail.id if invoice_detail else False,
                        'company_id': company_id,
                        'qbo_response': pprint.pformat(invoice)
                    }
                    quickbook_map_invoice.append(invoice_vals)

                    if invoice_detail:
                        log_message = (
                            f"Invoice successfully {'created and ' if inv_created else ''}"
                            f"mapped with QuickBooks invoice: {qkb_invoice_number}"
                        )
                        fault = False
                    else:
                        log_message = (
                            f"Invoice {'creation failed for' if inv_created else 'not found or mismatched with'} "
                            f"QuickBooks invoice: {qkb_invoice_number}"
                        )
                        fault = True
                    quickbook_map_invoice_log_ln.append(build_invoice_log(log_message,fault))

                else:
                    invoice_mapping.sudo().write({
                        'qbo_response': pprint.pformat(invoice),
                        'invoice_id': getattr(invoice_detail, 'id',False)
                    })
                    msg= f"Invoice {qkb_invoice_number} mapping updated.",
                    quickbook_map_invoice_log_ln.append(build_invoice_log(msg))

            if quickbook_map_invoice:
                self.env['qbo.invoice.map.vts'].sudo().create(quickbook_map_invoice)
            if quickbook_map_invoice_log_ln:
                self.env['quickbooks.log.vts.line'].sudo().create(quickbook_map_invoice_log_ln)

        else:
            log_id = self.env['quickbooks.log.vts'].sudo().generate_quickbooks_logs(
                quickbooks_operation_name='invoice', quickbooks_operation_type='import',
                instance=self.quickbook_instance_id.id if self.quickbook_instance_id else False,
                quickbooks_operation_message='Failed to fetch invoices')

            self.env['quickbooks.log.vts.line'].sudo().generate_quickbooks_process_line(
                quickbooks_operation_name='invoice', quickbooks_operation_type='import',
                instance=self.quickbook_instance_id.id if self.quickbook_instance_id else False,
                quickbooks_operation_message='Error during invoice import process',
                process_response_message=pprint.pformat(invoice_info),
                log_id=log_id, fault_operation=True)

    def _prepare_bill_creation(self, bill, vendor):
        line_vals = []
        for line in bill.get('Line', []):
            detail_type = line.get('DetailType')
            detail = line.get(detail_type, {})
            tax_ref = detail.get('TaxCodeRef', {}).get('value')
            tax = self.env['qbo.taxes.vts'].search([('quickbook_tax_id', '=', tax_ref),('quickbook_instance_id', '=', self.quickbook_instance_id.id)], limit=1) if tax_ref else False

            if detail_type == 'ItemBasedExpenseLineDetail':
                item_ref = detail.get('ItemRef', {}).get('value')
                product = self.env['qbo.product.ca.map.vts'].sudo().search([('quickbook_product_id', '=', item_ref),('quickbook_instance_id','=',self.quickbook_instance_id.id)], limit=1)
                if not product:
                    type = "Product"
                    qkb_product_id = self._get_product_from_quickbooks(item_ref, type)
                    product = self.env['qbo.product.ca.map.vts'].sudo().search([('quickbook_product_id', '=', qkb_product_id),('quickbook_instance_id', '=',self.quickbook_instance_id.id)],limit=1)

                account_id = product.product_id.property_account_expense_id.id if product.product_id.property_account_expense_id else False
                if not account_id and product.product_id.categ_id.property_account_expense_categ_id:
                    account_id = product.product_id.categ_id.property_account_expense_categ_id.id

                line_vals.append((0, 0, {
                        'name': line.get('Description', ''),
                        'product_id': product.product_id.id,
                        'account_id': account_id,
                        'quantity': detail.get('Qty', 1),
                        'price_unit': line.get('Amount', 0.0),
                        'tax_ids': [(6, 0, [tax.tax_id.id])] if tax else False,
                }))

            elif detail_type == 'AccountBasedExpenseLineDetail':
                account_ref = detail.get('AccountRef', {}).get('value')
                account = self.env['qbo.account.vts'].sudo().search([('quickbook_account_id', '=', account_ref),('quickbook_instance_id', '=', self.quickbook_instance_id.id),('company_id','=',self.quickbook_instance_id.company_id.id)], limit=1)
                if account:
                    line_vals.append((0, 0, {
                        'account_id': account.account_id.id,
                        'name': line.get('Description', ''),
                        'quantity': 1,
                        'price_unit': line.get('Amount', 0.0),
                        'tax_ids': [(6, 0, [tax.tax_id.id])] if tax else False,
                    }))
        vals = {
            'qck_instance_id': self.quickbook_instance_id.id if self.quickbook_instance_id else False,
            'qkca_bill_ID': bill.get('Id'),
            'qck_bill_doc': bill.get('DocNumber'),
            'move_type': 'in_invoice',
            'partner_id': vendor.vendor_id.id if vendor and vendor.vendor_id else False,
            'invoice_date': bill.get('TxnDate'),
            'invoice_date_due': bill.get('DueDate'),
            'ref': bill.get('DocNumber'),
            'invoice_line_ids': line_vals,
            'company_id': self.quickbook_instance_id.company_id.id if self.quickbook_instance_id.company_id else False
        }

        company_currency = self.env.user.company_id.currency_id
        currency_code = bill.get('CurrencyRef', {}).get('value')
        currency = self.env['res.currency'].sudo().search([('name', '=', currency_code),('active', '=', True)], limit=1) if currency_code else company_currency

        if not currency:
            currency = company_currency

        vals['currency_id'] = currency.id
        bill_detail = self.env['account.move'].with_context(skip_update=True).sudo().create(vals)

        return bill_detail

    def get_bill_from_quickbooks(self, bill_info, bill_status):

        if bill_status == 200 and bill_info and 'QueryResponse' in bill_info:
            instance_id = getattr(self.quickbook_instance_id, 'id', False)
            bill_items = bill_info.get('QueryResponse', {}).get('Bill', [])

            log_id = self.env['quickbooks.log.vts'].sudo().generate_quickbooks_logs(
                quickbooks_operation_name='bill', quickbooks_operation_type='import',
                instance=self.quickbook_instance_id.id if self.quickbook_instance_id else False,
                quickbooks_operation_message='Quickbooks to fetch Bills')

            quickbook_map_bill, quickbook_map_bill_log_ln = [], []

            for bill in bill_items:
                qkb_vendor_ref = bill.get('VendorRef').get('value')
                qkb_bill_id = bill.get('Id', '')

                bill_detail = False
                if qkb_bill_id:
                    bill_detail = self.env['account.move'].sudo().search([('move_type', '=', 'in_invoice'), ('qkca_bill_ID', '=', qkb_bill_id),('qck_instance_id','=',instance_id)], limit=1)

                vendor = False
                if qkb_vendor_ref:
                    vendor = self.env['qbo.vendor.ca.map.vts'].sudo().search([('quickbook_vendor_id', '=', qkb_vendor_ref),('quickbook_instance_id','=',self.quickbook_instance_id.id)], limit=1)

                if not vendor:
                    cust_type = "Vendor"
                    vendor_id = self._get_customer_or_vendor_from_qkca(qkb_vendor_ref, cust_type)
                    vendor = self.env['qbo.vendor.ca.map.vts'].sudo().search([('quickbook_vendor_id', '=', vendor_id),('quickbook_instance_id','=',self.quickbook_instance_id.id)], limit=1)
                    quickbook_map_bill_log_ln.append({
                        'quickbooks_operation_name': 'bill', 'quickbooks_operation_type': 'import',
                        'qkb_instance_id': instance_id,
                        'quickbooks_operation_message': "Vendor Successfully imported from Quickbook.",
                        'process_response_message': pprint.pformat(bill),
                        'quickbooks_operation_id': log_id.id if log_id else False,
                        'fault_operation': False})

                bill_created = False
                if not bill_detail and self.quickbook_instance_id.qkca_bill_creation and vendor:
                    bill_detail = self._prepare_bill_creation(bill, vendor)
                    bill_created = True


                bill_mapping = self.env['qbo.bill.ca.map.vts'].sudo().search([('quickbook_bill_id', '=', qkb_bill_id),('quickbook_instance_id', '=', self.quickbook_instance_id.id)], limit=1)

                def build_bill_log(message, fault=False):
                    return {
                        'quickbooks_operation_name': 'bill',
                        'quickbooks_operation_type': 'import',
                        'qkb_instance_id': self.quickbook_instance_id.id if self.quickbook_instance_id else False,
                        'quickbooks_operation_message': message,
                        'process_response_message': pprint.pformat(bill),
                        'quickbooks_operation_id': log_id.id if log_id else False,
                        'fault_operation': fault
                    }

                if not bill_mapping:
                    mapping_vals = {
                        'quickbook_bill_number': bill.get('DocNumber'),
                        'quickbook_bill_id': qkb_bill_id,
                        'partner_id': vendor.vendor_id.id if vendor and vendor.vendor_id else False,
                        'quickbook_instance_id': instance_id,
                        'bill_id': bill_detail.id if bill_detail else False,
                        'company_id': self.quickbook_instance_id.company_id.id if self.quickbook_instance_id.company_id else self.env.company.id,
                        'qbo_response': pprint.pformat(bill),
                    }
                    quickbook_map_bill.append(mapping_vals)

                    if not bill_detail:
                        log_message = (
                            f"Bill {'creation failed for' if bill_created else 'not found or mismatched with'} "
                            f"QuickBooks Bill: {qkb_bill_id}"
                        )
                        quickbook_map_bill_log_ln.append(build_bill_log(log_message, fault=True))

                    else:
                        bill_detail.write({
                            'qck_instance_id': self.quickbook_instance_id.id if self.quickbook_instance_id else False,
                            'qkca_bill_ID': qkb_bill_id})
                        if bill_created:
                            log_message = (f"Bill successfully created and mapped with QuickBooks Bill: {qkb_bill_id}")
                        else:
                            log_message = (f"Bill successfully mapped with QuickBooks Bill: {qkb_bill_id}")

                        quickbook_map_bill_log_ln.append(build_bill_log(log_message))

                else:
                    mapping_vals = {
                        'bill_id': bill_detail.id if bill_detail else False,
                        'qbo_response': pprint.pformat(bill),
                    }
                    if bill_detail and qkb_bill_id:
                        bill_detail.qkca_bill_ID = qkb_bill_id
                        bill_detail.qck_instance_id = instance_id
                    bill_mapping.sudo().write(mapping_vals)
                    msg=f"Vendor bill updated with QuickBooks bill: {qkb_bill_id}",
                    quickbook_map_bill_log_ln.append(build_bill_log(msg))

            if quickbook_map_bill:
                bill_mapped = self.env['qbo.bill.ca.map.vts'].sudo().create(quickbook_map_bill)
            if quickbook_map_bill_log_ln:
                vendor_map_logger = self.env['quickbooks.log.vts.line'].sudo().create(quickbook_map_bill_log_ln)
        else:
            log_id = self.env['quickbooks.log.vts'].sudo().generate_quickbooks_logs(
                quickbooks_operation_name='bill', quickbooks_operation_type='import',
                instance=self.quickbook_instance_id.id if self.quickbook_instance_id else False,
                quickbooks_operation_message='Failed to fetch Vendor Bill')
            log_line = self.env['quickbooks.log.vts.line'].sudo().generate_quickbooks_process_line(
                quickbooks_operation_name='bill', quickbooks_operation_type='import',
                instance=self.quickbook_instance_id.id if self.quickbook_instance_id else False,
                quickbooks_operation_message='Error during vendor bill import process',
                process_response_message=pprint.pformat(bill_info), log_id=log_id, fault_operation=True)

    def _prepare_payment_creation(self, payment, customer):
        company = self.quickbook_instance_id.company_id.id if self.quickbook_instance_id.company_id else False

        payment_vals = {
            'qck_instance_id': self.quickbook_instance_id.id if self.quickbook_instance_id else False,
            'qkca_payment_ID': payment.get('Id'),
            'partner_id': customer.partner_id.id if customer and customer.partner_id else False,
            'amount': payment.get('TotalAmt'),
            'date': payment.get('TxnDate'),
            'payment_type': 'inbound',
            'partner_type': 'customer',
            'company_id': company,

        }

        invoice_ids = []
        payment_line = payment.get('Line')
        for txn in payment_line:
            linked_inv = txn.get('LinkedTxn')
            for inv in linked_inv:
                if inv.get('TxnType') == 'Invoice':
                    invoice = self.env['account.move'].search([('qkca_invoice_ID', '=', inv.get('TxnId'))], limit=1)
                    if invoice:
                        invoice_ids.append(invoice.id)

        currency_code = payment.get('CurrencyRef', {}).get('value')
        if currency_code:
            currency = self.env['res.currency'].sudo().search([('name', '=', currency_code)], limit=1)
            payment_vals['currency_id'] = currency.id

        if invoice_ids:
            payment_vals['invoice_ids'] = [(6, 0, invoice_ids)]
        payment_detail = self.env['account.payment'].with_context(skip_update=True).sudo().create(payment_vals)
        return payment_detail

    def get_customer_payment_from_quickbooks(self, payment_info, payment_status):

        if payment_status == 200 and payment_info and 'QueryResponse' in payment_info:

            payment_items = payment_info.get('QueryResponse', {}).get('Payment', [])

            log_id = self.env['quickbooks.log.vts'].sudo().generate_quickbooks_logs(
                quickbooks_operation_name='customer_payment', quickbooks_operation_type='import',
                instance=self.quickbook_instance_id.id if self.quickbook_instance_id else False,
                quickbooks_operation_message='Quickbooks to fetch Customer Payment')

            quickbook_map_payment, quickbook_map_payment_log_ln = [], []

            for payment in payment_items:
                qkb_customer_ref = payment.get('CustomerRef').get('value')
                qkb_payment_id = payment.get('Id', '')

                payment_detail = False
                if qkb_payment_id:
                    payment_detail = self.env['account.payment'].sudo().search([('qkca_payment_ID', '=', qkb_payment_id),('qck_instance_id','=',self.quickbook_instance_id.id)], limit=1)

                customer = False
                if qkb_customer_ref:
                    customer = self.env['qbo.partner.map.vts'].sudo().search([('quickbook_id', '=', qkb_customer_ref),('quickbook_instance_id','=',self.quickbook_instance_id.id)], limit=1)

                if not customer:
                    cust_type = "Customer"
                    customer_id = self._get_customer_or_vendor_from_qkca(qkb_customer_ref, cust_type)
                    customer = self.env['qbo.partner.map.vts'].sudo().search([('quickbook_id', '=', customer_id),('quickbook_instance_id','=',self.quickbook_instance_id.id)], limit=1)
                    quickbook_map_payment_log_ln.append({
                        'quickbooks_operation_name': 'customer_payment', 'quickbooks_operation_type': 'import',
                        'qkb_instance_id': self.quickbook_instance_id.id,
                        'quickbooks_operation_message': "Customer Successfully Imported from Quickbooks.",
                        'process_response_message': pprint.pformat(payment),
                        'quickbooks_operation_id': log_id.id if log_id else False,
                        'fault_operation': False})

                payment_created = False
                if not payment_detail and self.quickbook_instance_id.qkca_payment_creation and customer:
                    payment_detail  = self._prepare_payment_creation(payment, customer)
                    payment_created = True


                payment_mapping = self.env['qbo.payment.ca.map.vts'].sudo().search([('quickbook_cust_payment_id', '=', qkb_payment_id),('quickbook_instance_id', '=', self.quickbook_instance_id.id)],limit=1)

                def build_payment_log(message, fault=False):
                    return {
                        'quickbooks_operation_name': 'customer_payment',
                        'quickbooks_operation_type': 'import',
                        'qkb_instance_id': self.quickbook_instance_id.id if self.quickbook_instance_id else False,
                        'quickbooks_operation_message': message,
                        'process_response_message': pprint.pformat(payment),
                        'quickbooks_operation_id': log_id.id if log_id else False,
                        'fault_operation': fault
                    }

                if not payment_mapping:
                    mapping_vals = {
                        'quickbook_instance_id': self.quickbook_instance_id.id if self.quickbook_instance_id else False,
                        'quickbook_cust_payment_id': qkb_payment_id,
                        'payment_id': payment_detail.id if payment_detail else False,
                        'partner_id': customer.partner_id.id if customer and customer.partner_id else False,
                        'company_id': self.quickbook_instance_id.company_id.id if self.quickbook_instance_id.company_id else self.env.company.id,
                        'qbo_response': pprint.pformat(payment),
                    }
                    quickbook_map_payment.append(mapping_vals)
                    if not payment_detail:
                        log_message = (
                            f"Payment {'creation failed for' if payment_created else 'not found or mismatched'} "
                            f"QuickBooks Payment: {qkb_payment_id}")
                        quickbook_map_payment_log_ln.append(build_payment_log(log_message, fault=True))
                    elif payment_detail:
                        payment_detail.write({
                            'qck_instance_id': self.quickbook_instance_id.id if self.quickbook_instance_id else False,
                            'qkca_payment_ID': qkb_payment_id
                        })
                        if payment_created:
                            log_message = (f"Customer Payment successfully created and mapped with QuickBooks Payment: {qkb_payment_id}")
                        else:
                            log_message = (f"Customer Payment successfully mapped with QuickBooks Payment: {qkb_payment_id}")
                        quickbook_map_payment_log_ln.append(build_payment_log(log_message))
                else:
                    mapping_vals = {'qbo_response': pprint.pformat(payment),}
                    payment_mapping.sudo().write(mapping_vals)
                    msg="Customer Payment updated with QuickBooks Payment"
                    quickbook_map_payment_log_ln.append(build_payment_log(msg))

            if quickbook_map_payment:
                payment_mapped = self.env['qbo.payment.ca.map.vts'].sudo().create(quickbook_map_payment)
            if quickbook_map_payment_log_ln:
                customer_map_logger = self.env['quickbooks.log.vts.line'].sudo().create(quickbook_map_payment_log_ln)
        else:
            log_id = self.env['quickbooks.log.vts'].sudo().generate_quickbooks_logs(
                quickbooks_operation_name='customer_payment', quickbooks_operation_type='import',
                instance=self.quickbook_instance_id.id if self.quickbook_instance_id else False,
                quickbooks_operation_message='Failed to fetch Customer Payment')
            log_line = self.env['quickbooks.log.vts.line'].sudo().generate_quickbooks_process_line(
                quickbooks_operation_name='bill', quickbooks_operation_type='import',
                instance=self.quickbook_instance_id.id if self.quickbook_instance_id else False,
                quickbooks_operation_message='Error during customer payment import process',
                process_response_message=pprint.pformat(payment_info), log_id=log_id, fault_operation=True)


    def _prepare_billpayment_creation(self, bill, vendor):
        company = self.quickbook_instance_id.company_id.id if self.quickbook_instance_id.company_id else False

        bill_vals = {
            'qck_instance_id': self.quickbook_instance_id.id if self.quickbook_instance_id else False,
            'qkca_billpay_ID': bill.get('Id'),
            'partner_id': vendor.vendor_id.id if vendor and vendor.vendor_id else False,
            'amount': bill.get('TotalAmt'),
            'date': bill.get('TxnDate'),
            'payment_type': 'outbound',
            'partner_type': 'supplier',
            'company_id': company,
        }
        bill_ids = []
        bill_line = bill.get('Line')
        for line in bill_line:
            linked_bill = line.get('LinkedTxn')
            for txn in linked_bill:
                if txn.get('TxnType') == 'Bill':
                    vendor_payment = self.env['account.move'].search([('qkca_bill_ID', '=', txn.get('TxnId'))], limit=1)
                    if vendor_payment:
                        bill_ids.append(vendor_payment.id)

        if bill_ids:
            bill_vals['invoice_ids'] = [(6, 0, bill_ids)]

        quickbooks_pay_type = bill.get('PayType')
        payment_method = self.env['account.payment.method'].search([('name', '=', quickbooks_pay_type) ], limit=1)
        if payment_method:
            bill_vals['payment_method_id'] = payment_method.id

        currency_code = bill.get('CurrencyRef', {}).get('value')
        if currency_code:
            currency = self.env['res.currency'].sudo().search([('name', '=', currency_code)], limit=1)
            bill_vals['currency_id'] = currency.id

        billpayment_detail = self.env['account.payment'].with_context(skip_update=True).sudo().create(bill_vals)
        return billpayment_detail

    def get_billpayment_from_quickbooks(self, billpayment_info, billpayment_status):

        if billpayment_status == 200 and billpayment_info and 'QueryResponse' in billpayment_info:
            billpayment_items = billpayment_info.get('QueryResponse').get('BillPayment', [])

            log_id = self.env['quickbooks.log.vts'].sudo().generate_quickbooks_logs(
                quickbooks_operation_name='billpayment', quickbooks_operation_type='import',
                instance=self.quickbook_instance_id.id if self.quickbook_instance_id else False,
                quickbooks_operation_message='Quickbooks to fetch Vendor Bill Payment')

            quickbook_map_billpayment, quickbook_map_billpayment_log_ln = [], []

            for bill in billpayment_items:

                qbk_vendor_ref = bill.get('VendorRef').get('value')
                qbk_bill_id = bill.get('Id', '')

                billpayment_detail = False
                if qbk_bill_id:
                    billpayment_detail = self.env['account.payment'].sudo().search([('qkca_billpay_ID', '=', qbk_bill_id),('qck_instance_id','=',self.quickbook_instance_id.id)], limit=1)

                vendor = False
                if qbk_vendor_ref:
                    vendor = self.env['qbo.vendor.ca.map.vts'].sudo().search([('quickbook_vendor_id', '=', qbk_vendor_ref),('quickbook_instance_id','=',self.quickbook_instance_id.id)], limit=1)

                if not vendor:
                    cust_type = "Vendor"
                    vendor_id = self._get_customer_or_vendor_from_qkca(qbk_vendor_ref, cust_type)
                    vendor = self.env['qbo.vendor.ca.map.vts'].sudo().search([('quickbook_vendor_id', '=', vendor_id),('quickbook_instance_id','=',self.quickbook_instance_id.id)], limit=1)
                    quickbook_map_billpayment_log_ln.append({
                        'quickbooks_operation_name': 'billpayment', 'quickbooks_operation_type': 'import',
                        'qkb_instance_id': self.quickbook_instance_id.id if self.quickbook_instance_id else False,
                        'quickbooks_operation_message': "Vendor Successfully Imported from Quickbooks.",
                        'process_response_message': pprint.pformat(bill),
                        'quickbooks_operation_id': log_id.id if log_id else False,
                        'fault_operation': False})

                billpayment_created = False
                if not billpayment_detail and self.quickbook_instance_id.qkca_bill_payment_creation and vendor:
                    billpayment_detail = self._prepare_billpayment_creation(bill, vendor)
                    billpayment_created = True


                billpayment_mapping = self.env['qbo.bill.payment.ca.map.vts'].sudo().search(
                    [('quickbook_bill_payment_id', '=', qbk_bill_id),('quickbook_instance_id', '=', self.quickbook_instance_id.id)], limit=1)

                def build_bill_log(message, fault=False):
                    return {
                        'quickbooks_operation_name': 'account',
                        'quickbooks_operation_type': 'import',
                        'qkb_instance_id': self.quickbook_instance_id.id if self.quickbook_instance_id else False,
                        'quickbooks_operation_message': message,
                        'process_response_message': pprint.pformat(bill),
                        'quickbooks_operation_id': log_id.id if log_id else False,
                        'fault_operation': fault
                    }

                if not billpayment_mapping:
                    mapping_vals = {
                        'quickbook_bill_payment_number': bill.get('DocNumber'),
                        'quickbook_bill_payment_id': qbk_bill_id,
                        'partner_id': vendor.vendor_id.id if vendor and vendor.vendor_id  else False,
                        'quickbook_instance_id': self.quickbook_instance_id.id if self.quickbook_instance_id else False,
                        'payment_id': billpayment_detail.id if billpayment_detail else False,
                        'company_id': self.quickbook_instance_id.company_id.id if self.quickbook_instance_id.company_id else self.env.company.id,
                        'qbo_response': pprint.pformat(bill),
                    }
                    quickbook_map_billpayment.append(mapping_vals)

                    if not billpayment_detail:
                        log_message = (
                            f"Bill Payment {'creation failed for' if billpayment_created else 'not found or mismatched with'} "
                            f"QuickBooks Bill Payment: {bill.get('DocNumber')}"
                        )
                        fault = True

                    elif billpayment_detail:
                        billpayment_detail.write({
                            'qck_instance_id': self.quickbook_instance_id.id if self.quickbook_instance_id else False,
                            'qkca_billpay_ID': qbk_bill_id
                        })
                        if billpayment_created:
                            log_message = (
                                f"Bill Payment successfully created and mapped with QuickBooks Payment: {qbk_bill_id}")
                            fault = False
                        else:
                            log_message = (
                                f"Bill Payment successfully mapped with QuickBooks Payment: {qbk_bill_id}")
                            fault = False
                    quickbook_map_billpayment_log_ln.append(build_bill_log(log_message,fault))
                else:
                    mapping_vals = {'qbo_response': pprint.pformat(bill),}
                    billpayment_mapping.sudo().write(mapping_vals)
                    msg= f"Vendor bill payment updated with QuickBooks bill: {bill.get('DocNumber')}"
                    quickbook_map_billpayment_log_ln.append(build_bill_log(msg))

            if quickbook_map_billpayment:
                bill_payment_mapped = self.env['qbo.bill.payment.ca.map.vts'].sudo().create(quickbook_map_billpayment)
            if quickbook_map_billpayment_log_ln:
                bill_payment_map_logger = self.env['quickbooks.log.vts.line'].sudo().create(quickbook_map_billpayment_log_ln)
        else:
            log_id = self.env['quickbooks.log.vts'].sudo().generate_quickbooks_logs(
                quickbooks_operation_name='billpayment', quickbooks_operation_type='import',
                instance=self.quickbook_instance_id.id if self.quickbook_instance_id else False,
                quickbooks_operation_message='Failed to fetch Vendor Bill Payment')
            log_line = self.env['quickbooks.log.vts.line'].sudo().generate_quickbooks_process_line(
                quickbooks_operation_name='billpayment', quickbooks_operation_type='import',
                instance=self.quickbook_instance_id.id if self.quickbook_instance_id else False,
                quickbooks_operation_message='Error during vendor bill payment import process',
                process_response_message=pprint.pformat(billpayment_info), log_id=log_id, fault_operation=True)



    def execute_process_of_quickbooks(self):
        res = super(QuickbooksWizardInherit, self).execute_process_of_quickbooks()
        if self.quickbook_instance_id and self.quickbook_instance_id.access_token:
            qck_url = self.quickbook_instance_id.quickbook_base_url
            company_id = self.quickbook_instance_id.realm_id
            token = self.quickbook_instance_id.access_token
            from_date = self.from_date.strftime('%Y-%m-%dT%H:%M:%S-07:00') if self.from_date else None
            to_date = self.to_date.strftime('%Y-%m-%dT%H:%M:%S-07:00') if self.to_date else None

            # if self.import_operations == 'import_vendor':
            #     if not self.quickbook_instance_id.qkca_is_company_canada:
            #         raise UserError(_("This import feature is only supported for Canadian QuickBooks company instances."))
            #
            #     vendor_info, vendor_status = self.env['quickbooks.api.vts'].sudo().get_data_from_quickbooks(
            #         qck_url,company_id,token,self.import_operations,from_date=from_date,to_date=to_date)
            #
            #     qk_vendor_details = self.get_vendor_from_quickbooks_ca(vendor_info, vendor_status)

            if self.import_operations == 'import_pro_category':
                if not self.quickbook_instance_id.qkca_is_company_canada:
                    raise UserError(_("This import feature is only supported for Canadian QuickBooks company instances."))

                category_info, category_status = self.env['quickbooks.api.vts'].sudo().get_data_from_quickbooks(
                    qck_url,company_id,token,self.import_operations,from_date=from_date,to_date=to_date)

                qk_category_details = self.get_category_from_quickbooks(category_info, category_status)

            elif self.import_operations == 'import_invoice':
                if not self.quickbook_instance_id.qkca_is_company_canada:
                    raise UserError(_("This import feature is only supported for Canadian QuickBooks company instances."))

                invoice_info, invoice_status = self.env['quickbooks.api.vts'].sudo().get_data_from_quickbooks(
                    qck_url,company_id,token,self.import_operations,from_date=from_date,to_date=to_date)

                qk_invoice_details = self.get_invoice_from_quickbooks(invoice_info, invoice_status)

            elif self.import_operations == 'import_vendor_bill':
                if not self.quickbook_instance_id.qkca_is_company_canada:
                    raise UserError(_("This import feature is only supported for Canadian QuickBooks company instances."))

                bill_info, bill_status = self.env['quickbooks.api.vts'].sudo().get_data_from_quickbooks(
                    qck_url,company_id,token,self.import_operations,from_date=from_date,to_date=to_date)

                qk_bill_details = self.get_bill_from_quickbooks(bill_info, bill_status)

            elif self.import_operations == 'import_customer_payment':
                if not self.quickbook_instance_id.qkca_is_company_canada:
                    raise UserError(_("This import feature is only supported for Canadian QuickBooks company instances."))

                cust_payment_info, cust_payment_status = self.env['quickbooks.api.vts'].sudo().get_data_from_quickbooks(
                    qck_url,company_id, token, self.import_operations, from_date=from_date, to_date=to_date)

                qk_customer_payment_details = self.get_customer_payment_from_quickbooks(cust_payment_info,cust_payment_status)

            elif self.import_operations == 'import_billpayment':
                if not self.quickbook_instance_id.qkca_is_company_canada:
                    raise UserError(_("This import feature is only supported for Canadian QuickBooks company instances."))

                billpayment_info, billpayment_status = self.env['quickbooks.api.vts'].sudo().get_data_from_quickbooks(
                    qck_url,company_id, token, self.import_operations, from_date=from_date, to_date=to_date)

                qk_bill_payment_detail = self.get_billpayment_from_quickbooks(billpayment_info, billpayment_status)

        return res

    def _get_customer_or_vendor_from_qkca(self,customer_ref,cust_type):
        qkca_partner_creation = False
        if self.quickbook_instance_id and self.quickbook_instance_id.access_token:
            qck_url = self.quickbook_instance_id.quickbook_base_url
            company_id = self.quickbook_instance_id.realm_id
            token = self.quickbook_instance_id.access_token

            header = self.env['quickbooks.api.vts'].sudo()._get_quick_book_header(token)
            query = f"SELECT * FROM {cust_type} WHERE Id = '{customer_ref}'"
            endpoint = f"{company_id}/query"
            request_url = f"{qck_url}/{endpoint}?query={query}"

            response = requests.get(request_url,headers=header)
            partner_info = response.json()
            partner_status = response.status_code
            if cust_type == "Customer":
                qkca_partner_creation = self.get_customer_from_quickbooks(partner_info, partner_status, qck_url, company_id, token)
            if cust_type == "Vendor":
                qkca_partner_creation = self.get_vendor_from_quickbooks_ca(partner_info, partner_status)
        return qkca_partner_creation

    def _get_product_from_quickbooks(self,item_ref, type):
        qkca_products_creation = False
        if self.quickbook_instance_id and self.quickbook_instance_id.access_token:
            qck_url = self.quickbook_instance_id.quickbook_base_url
            company_id = self.quickbook_instance_id.realm_id
            token = self.quickbook_instance_id.access_token

            header = self.env['quickbooks.api.vts'].sudo()._get_quick_book_header(token)
            query=f"SELECT * FROM Item WHERE Id = '{item_ref}'"
            endpoint = f"{company_id}/query"
            request_url = f"{qck_url}/{endpoint}?query={query}"

            response = requests.get(request_url,headers=header)
            product_info = response.json()
            product_status = response.status_code
            if type == "Product":
                qkca_products_creation = self.get_ca_product_from_quickbooks(product_info,product_status)
            elif type == "Category":
                qkca_products_creation = self.get_category_from_quickbooks(product_info,product_status)
        return qkca_products_creation
