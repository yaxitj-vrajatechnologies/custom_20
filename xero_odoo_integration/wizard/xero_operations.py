from odoo import models, fields, _
import requests
import pprint
from datetime import datetime, timezone
import re


class XeroOperations(models.TransientModel):
	_name = 'xero.operations'
	_inherit = ['mail.activity.mixin']
	_description = 'Xero Import Export Operations'

	xero_instance_id = fields.Many2one(comodel_name='xero.connect', string='Xero Connection', default=lambda self: self.env.context.get('active_id'))
	xero_operations = fields.Selection([('import', 'Import')], string='Xero Operations', default='import')
	import_operations = fields.Selection(
		selection=[("import_customers", "Import Customers / Vendors, Contact Groups"), ("import_accounts", "Import Accounts, Analytic Account, Taxes"),('import_products', "Import Products"),
				   ('import_invoice', 'Import Invoices / Bills'), ('import_creditnote', 'Import CreditNote'),('import_purchase_order', 'Import Purchase Order'),
					('import_payment', 'Import Payment'), ('import_prepayment', 'Import Prepayments'),('import_overpayment', 'Import Overpayments')],
		string='Import Operations', default='import_customers')
	import_from_date = fields.Datetime(string='From Date')
	import_to_date = fields.Datetime(string='To Date')
	
	def _create_import_failure_activity(self, message, log_id):
		"""
		Create a failure activity .
		"""
		instance = self.xero_instance_id
		if not instance or not instance.user_id:
			return

		activity_type = self.env.ref('mail.mail_activity_data_todo')

		self.env['mail.activity'].create({
			'activity_type_id': activity_type.id,
			'res_model_id': self.env['ir.model']._get('xero.log.vts').id,
			'res_id': log_id.id,
			'user_id': instance.user_id.id,
			'summary': 'Xero Import Process Failed',
			'note': message,
			'date_deadline': fields.Date.today(),
		})

	def build_xero_log(self, entity_name, message, instance_id, entity_data=None, log_id=None, fault=False):
		"""
		Method Used for generating log details for import operation
		"""
		return {
			'xero_operation_name': entity_name,
			'xero_operation_type': 'import',
			'xero_instance_id': instance_id,
			'xero_operation_message': message,
			'process_response_message': pprint.pformat(entity_data),
			'xero_operation_id': log_id.id if log_id else False,
			'fault_operation': fault
		}

	def _xero_partner_creation(self, partner):
		"""
		This method creates a Partner Payload to create xero partner in odoo
		"""

		addresses = partner.get('Addresses')
		addr = next((a for a in addresses if a.get('AddressType') == 'POBOX'), addresses[0] if addresses else {})
		country_name = addr.get('Country')
		country = self.env['res.country'].search([('code', '=', country_name)], limit=1)
		state_code = addr.get('Region')
		state = self.env['res.country.state'].search([('name', 'ilike', state_code), ('country_id', '=', country.id)],limit=1)
		phones = partner.get('Phones', [])
		phone = next((p['PhoneNumber'] for p in phones if p.get('PhoneType') == 'DEFAULT' and p.get('PhoneNumber')),False)
		# mobile = next((p['PhoneNumber'] for p in phones if p.get('PhoneType') == 'MOBILE' and p.get('PhoneNumber')),False)
		street_addr = next((a for a in addresses if a.get('AddressType') == 'STREET'), None)

		# contact_id = partner.get('ContactID')
		# customer_id = False
		# vendor_id = False

		# if partner.get('IsCustomer'):
		#     customer_id = contact_id
		# if partner.get('IsSupplier'):
		#     vendor_id = contact_id
		# else:
		#     customer_id = contact_id

		partner_vals = {
			'name': partner.get('Name').strip(),
			'street': f"{addr.get('AddressLine1', '')} {addr.get('AddressLine2', '')}".strip(),
			'street2': f"{addr.get('AddressLine3', '')} {addr.get('AddressLine4', '')}".strip(),
			'state_id': state.id if state else False,
			'zip': addr.get('PostalCode', ''),
			'country_id': country.id if country else False,
			'city': addr.get('City', ''),
			'phone': phone,
			# 'mobile': mobile,
			'email': partner.get('EmailAddress', ''),
			'vat': partner.get('TaxNumber'),
			'website': partner.get('Website'),
			'supplier_rank': 1 if partner.get('IsSupplier') else 0,
			'customer_rank': 1 if partner.get('IsCustomer') else 0,
			'company_id': self.xero_instance_id.company_id.id if self.xero_instance_id.company_id else False,
		}
		partner = self.env['res.partner'].create(partner_vals)

		# Delivery Address
		if partner and street_addr and any(street_addr.get(k) for k in ('AddressLine1', 'AddressLine2', 'AddressLine3', 'AddressLine4','City', 'PostalCode', 'Country', )):
			country = self.env['res.country'].search([('code', '=', street_addr.get('Country'))], limit=1)
			state = self.env['res.country.state'].search([('name', 'ilike', street_addr.get('Region')),('country_id', '=', country.id if country else False)],limit=1)

			delivery_partner = self.env['res.partner'].create({
				'parent_id': partner.id,
				'type': 'delivery',
				'street': f"{street_addr.get('AddressLine1', '')} {street_addr.get('AddressLine2', '')}".strip(),
				'street2': f"{street_addr.get('AddressLine3', '')} {street_addr.get('AddressLine4', '')}".strip(),
				'city': street_addr.get('City', ''),
				'zip': street_addr.get('PostalCode', ''),
				'state_id': state.id if state else False,
				'country_id': country.id if country else False,
				'phone': phone,
				# 'mobile': mobile,
				# 'email': partner.get('EmailAddress', ''),
			})

		return partner

	def get_customer_from_xero(self, customer_info, customer_status):
		"""
		Fetching Customer from Xero
		"""
		instance_id = self.xero_instance_id.id if self.xero_instance_id else False
		company = self.xero_instance_id.company_id.id if self.xero_instance_id.company_id else False

		if customer_status == 200 and customer_info and 'Contacts' in customer_info:
			contacts = customer_info.get('Contacts')

			log_id = self.env['xero.log.vts'].sudo().generate_xero_logs(xero_operation_name='partner',xero_operation_type='import',
																		instance=instance_id,xero_operation_message='Fetch Partner From Xero')
			xero_map_partner_log_ln = []
			xero_map_partner=[]
			partner_id = False
			for partner in contacts:
				xero_partner_name = partner.get('Name', '').strip()
				xero_partner_email = partner.get('EmailAddress')
				xero_partner_id = partner.get('ContactID', '')

				if xero_partner_name:
					partner_id = self.env['res.partner'].sudo().search([('name', '=', xero_partner_name)], limit=1)

				if partner_id and partner_id.email and xero_partner_email:
					if partner_id.email.strip().lower() != xero_partner_email.strip().lower():
						partner_id = False

				partner_created = False
				if not partner_id and self.xero_instance_id.xero_customer_creation:
					partner_id = self._xero_partner_creation(partner)
					if partner_id:
						partner_created = True

				partner_mapping = self.env['xero.partner.map'].sudo().search([('xero_instance_id', '=', instance_id),('xero_contact_id', '=',xero_partner_id )], limit=1)

				if not partner_mapping:
					mapping_vals = {
						'xero_instance_id': instance_id,
						'xero_contact_id': xero_partner_id,
						'xero_contact_name': xero_partner_name,
						'partner_id': partner_id.id if partner_id else False,
						'xero_response': pprint.pformat(partner),
					}
					xero_map_partner.append(mapping_vals)

					if not partner_id:
						msg = f"Failed to create Xero partner in Odoo : {xero_partner_name}"
						activity = self._create_import_failure_activity(msg, log_id)
						xero_map_partner_log_ln.append(
							self.build_xero_log(entity_name='partner', message=msg, instance_id=instance_id,
												entity_data=partner, log_id=log_id, fault=True))
					elif partner_id:
						if partner_created:
							opr_msg = f"Xero Partner successfully created: {xero_partner_name}"
						else:
							opr_msg = f"Partner successfully updated with Xero Partner: {xero_partner_name}"
						xero_map_partner_log_ln.append(
							self.build_xero_log(entity_name='partner', message=opr_msg, instance_id=instance_id,
												entity_data=partner, log_id=log_id, fault=False))
				else:
					mapping_vals = {'partner_id':partner_id.id if partner_id else False,'xero_response': pprint.pformat(partner)}
					partner_mapping.sudo().write(mapping_vals)
					opr_msg=f"Partner updated with Xero Partner : {xero_partner_name}"
					xero_map_partner_log_ln.append(self.build_xero_log(entity_name='partner', message=opr_msg, instance_id=instance_id,
										entity_data=partner, log_id=log_id, fault=False))

			if xero_map_partner:
				partner_map = self.env['xero.partner.map'].sudo().create(xero_map_partner)
			if xero_map_partner_log_ln:
				partner_log_line = self.env['xero.log.vts.line'].sudo().create(xero_map_partner_log_ln)
			return partner_id
		else:
			log_id = self.env['xero.log.vts'].sudo().generate_xero_logs(xero_operation_name='partner',
				xero_operation_type='import', instance=instance_id,xero_operation_message="Error during customer import process")
			log_line = self.env['xero.log.vts.line'].sudo().generate_xero_process_line(xero_operation_name='partner',
				xero_operation_type='import', instance=instance_id,xero_operation_message="Error during customer import process",
				process_response_message=pprint.pformat(customer_info), log_id=log_id, fault_operation=True)

	def _xero_account_creation(self, account):
		"""
		This method creates account payload to create accounts in odoo
		"""
		Account = self.env['account.account'].sudo()
		xr_account_name = account.get('Name')
		xr_account_type = account.get('Type')
		account_type_map = {
			'BANK': 'asset_cash',
			'CURRENT': 'asset_current',
			'FIXED': 'asset_fixed',
			'NONCURRENT': 'asset_non_current',
			'INVENTORY': 'asset_current',
			'PREPAYMENT': 'asset_prepayments',
			'RECEIVABLE': 'asset_receivable',
			'PAYABLE': 'liability_payable',
			'CURRENTLIABILITY': 'liability_current',
			'LIABILITY': 'liability_non_current',
			'CREDITCARD': 'liability_credit_card',
			'EQUITY': 'equity',
			'REVENUE': 'income',
			'SALES': 'income',
			'OTHERINCOME': 'income_other',
			'EXPENSE': 'expense',
			'OVERHEADS': 'expense',
			'DIRECTCOSTS': 'expense_direct_cost',
			'DEPRECIATION': 'expense_depreciation',
			'OTHEREXPENSE': 'expense',
		}
		odoo_account_type = account_type_map.get(xr_account_type, 'expense')
		code = account.get('Code')
		account_vals = {
			'name': xr_account_name,
			'code': code,
			'account_type': odoo_account_type,
			'company_ids': [
				(6, 0, [self.xero_instance_id.company_id.id])] if self.xero_instance_id.company_id else False,
			'note': account.get('Description'),
			# 'deprecated': True if account.get('Status') == 'ARCHIVED' else False,
		}

		account_detail = Account.create(account_vals)
		return account_detail

	def get_account_from_xero(self, account_info, account_status):
		"""
		Fetching Charts of Accounts from Xero
		"""
		instance_id = self.xero_instance_id.id if self.xero_instance_id else False
		company = self.xero_instance_id.company_id.id if self.xero_instance_id.company_id else False

		if account_status == 200 and account_info and 'Accounts' in account_info:
			accounts = account_info.get('Accounts')

			log_id = self.env['xero.log.vts'].sudo().generate_xero_logs(xero_operation_name='account',xero_operation_type='import',
																		instance=instance_id,xero_operation_message='Fetch Charts Of Account From Xero')
			xero_account_log_ln = []
			xero_map_account = []
			account_map=False
			for account in accounts:
				xero_account_name = account.get('Name', '').strip()
				xero_account_id = account.get('AccountID', '')
				xr_acc_code = account.get('Code')
						# continue
				accounts_detail = False
				if xero_account_name:
					accounts_detail = self.env['account.account'].sudo().search(
						[('name', '=', xero_account_name), ('code','=',account.get('Code')),('company_ids', 'in', company)], limit=1)

				account_created = False
				if not accounts_detail:
					existing_account_code = self.env['account.account'].sudo().search([('code', '=', xr_acc_code)],limit=1)
					if existing_account_code:
						msg = f"Failed to create Xero account {xero_account_name}: the account code {xr_acc_code} already exists for : {existing_account_code.name}"
						activity = self._create_import_failure_activity(msg, log_id)
						xero_account_log_ln.append(self.build_xero_log(entity_name='account', message=msg, instance_id=instance_id,
												entity_data=account, log_id=log_id, fault=True))
					if not existing_account_code and self.xero_instance_id.xero_account_creation:
						accounts_detail = self._xero_account_creation(account)
						if accounts_detail:
							account_created = True

				account_mapping=self.env['xero.account.map'].sudo().search([('xero_instance_id','=',instance_id),('xero_account_id','=',xero_account_id)], limit=1)
				if not account_mapping:
					mapping_vals={
						'xero_instance_id': instance_id,
						'xero_account_code':xr_acc_code,
						'xero_account_id': xero_account_id,
						'xero_account_name' : xero_account_name,
						'account_id' : accounts_detail.id if accounts_detail else False,
						'xero_response' : pprint.pformat(account)
					}
					xero_map_account.append(mapping_vals)
					if not accounts_detail:
						msg = f"Failed to create Xero Account in Odoo : {xero_account_name}"
						activity = self._create_import_failure_activity(msg, log_id)
						xero_account_log_ln.append(
							self.build_xero_log(entity_name='account', message=msg, instance_id=instance_id,
												entity_data=account, log_id=log_id, fault=True))
					elif accounts_detail:
						if account_created:
							opr_msg = f"Xero Accounts successfully created: {xero_account_name}"
						else:
							opr_msg = f"Accounts successfully updated with Xero Accounts: {xero_account_name}"
						xero_account_log_ln.append(
							self.build_xero_log(entity_name='account', message=opr_msg, instance_id=instance_id,
												entity_data=account, log_id=log_id, fault=False))
				else:
					mapping_vals = {'account_id':accounts_detail.id if accounts_detail else False,'xero_response': pprint.pformat(account)}
					account_mapping.sudo().write(mapping_vals)
					msg = f"Chart of Account updated with Xero Account: {xero_account_name}"
					xero_account_log_ln.append(
						self.build_xero_log(entity_name='account', message=msg, instance_id=instance_id,
												entity_data=account, log_id=log_id, fault=False))

			if xero_map_account:
				account_map = self.env['xero.account.map'].sudo().create(xero_map_account)
			if xero_account_log_ln:
				account_log_line = self.env['xero.log.vts.line'].sudo().create(xero_account_log_ln)
			return account_map
		else:
			log_id = self.env['xero.log.vts'].sudo().generate_xero_logs(
				xero_operation_name='account',xero_operation_type='import', instance=instance_id,
				xero_operation_message="Error during account import process"
			)
			log_line = self.env['xero.log.vts.line'].sudo().generate_xero_process_line(
				xero_operation_name='account',xero_operation_type='import', instance=instance_id,
				xero_operation_message="Error during account import process",
				process_response_message=pprint.pformat(account_info), log_id=log_id, fault_operation=True)

	def _xero_product_creation(self, product):
		"""
		This method creates product payload to create product in odoo
		"""

		sales_details = product.get('SalesDetails') or {}
		purchase_details = product.get('PurchaseDetails') or {}
		account_code = purchase_details.get('COGSAccountCode') or purchase_details.get('AccountCode')

		income_account = self.env['xero.account.map'].sudo().search([('xero_account_code', '=',sales_details.get('AccountCode'))], limit=1)
		expense_account = self.env['xero.account.map'].sudo().search([('xero_account_code', '=', account_code)], limit=1)

		def get_tax(tax_type, tax_use):
			if not tax_type:
				return False
			mapping = self.env['xero.tax.map'].sudo().search([('xero_instance_id', '=', self.xero_instance_id.id),('xero_tax_id', '=', tax_type)], limit=1)
			if not mapping:
				return False
			return mapping.tax_id.filtered(lambda t: t.type_tax_use == tax_use)

		sale_tax_id = get_tax(sales_details.get('TaxType'), 'sale')
		purchase_tax_id = get_tax(purchase_details.get('TaxType'), 'purchase')

		product_val = {
			'name': product.get('Name', ''),
			'list_price': sales_details.get('UnitPrice', 0.0),
			'taxes_id': [(6, 0, sale_tax_id.ids)] if sale_tax_id else False,
			'default_code': product.get('Code'),
			'description_sale': product.get('Description'),
			'type': 'consu' if product.get('IsTrackedAsInventory') else 'service',
			'is_storable': product.get('IsTrackedAsInventory', False),
			'standard_price':  purchase_details.get('UnitPrice', 0.0),
			'supplier_taxes_id': [(6, 0, purchase_tax_id.ids)] if purchase_tax_id else False,
			'property_account_income_id': income_account.account_id.id if income_account and income_account.account_id else False,
			'property_account_expense_id': expense_account.account_id.id if expense_account and expense_account.account_id else False,
			'company_id': self.xero_instance_id.company_id.id if self.xero_instance_id.company_id else False
		}
		product_detail = self.env['product.template'].sudo().create(product_val)
		return product_detail

	def get_product_from_xero(self, product_info, product_status):
		"""
		Fetching Products from Xero
		"""
		instance_id = self.xero_instance_id.id if self.xero_instance_id else False
		company = self.xero_instance_id.company_id.id if self.xero_instance_id.company_id else False
		if product_status == 200 and product_info and 'Items' in product_info:
			products = product_info.get('Items')

			log_id = self.env['xero.log.vts'].sudo().generate_xero_logs(xero_operation_name='product',xero_operation_type='import',
																		instance=instance_id,xero_operation_message='Fetch Products From Xero')
			xero_product_log_ln = []
			xero_map_product = []
			product_id = False
			for product in products:
				xr_product_name = product.get('Name', '').strip()
				xr_product_id = product.get('ItemID', '')

				if xr_product_name:
					product_id = self.env['product.template'].sudo().search([('name', '=', xr_product_name)], limit=1)
				if not product_id and product.get('Code'):
					product_id = self.env['product.template'].sudo().search([('default_code', '=', product.get('Code'))], limit=1)

				product_created = False
				if not product_id and self.xero_instance_id.xero_product_creation:
					product_id = self._xero_product_creation(product)
					if product_id:
						product_created = True

				product_mapping = self.env['xero.product.map'].sudo().search([('xero_instance_id', '=', instance_id),('xero_product_id', '=', xr_product_id)], limit=1)
				if not product_mapping:
					mapping_vals = {
						'xero_instance_id': instance_id,
						'xero_product_id': xr_product_id,
						'xero_product_name': xr_product_name,
						'product_id': product_id.id if product_id else False,
						'xero_response': pprint.pformat(product)
						}
					xero_map_product.append(mapping_vals)

					if not product_id:
						msg = f"Failed to create Xero Product in Odoo: {xr_product_name}"
						activity = self._create_import_failure_activity(msg, log_id)
						xero_product_log_ln.append(
							self.build_xero_log(entity_name='product', message=msg, instance_id=instance_id,
											entity_data=product, log_id=log_id, fault=True))
					elif product_id:
						if product_created:
							opr_msg = f"Xero Product successfully created: {xr_product_name}"
						else:
							opr_msg = f"Product successfully updated with Xero Product: {xr_product_name}"
						xero_product_log_ln.append(
							self.build_xero_log(entity_name='product', message=opr_msg, instance_id=instance_id,
											entity_data=product, log_id=log_id, fault=False))
				else:
					mapping_vals = {'product_id':product_id.id if product_id else False,'xero_response': pprint.pformat(product)}
					product_mapping.sudo().write(mapping_vals)
					opr_msg = f"Product updated with Xero Product : {xr_product_name}"
					xero_product_log_ln.append(self.build_xero_log(entity_name='product',message=opr_msg,instance_id=instance_id,
							entity_data=product,log_id=log_id,fault=False))
			if xero_map_product:
				product_map = self.env['xero.product.map'].sudo().create(xero_map_product)
			if xero_product_log_ln:
				product_log_line = self.env['xero.log.vts.line'].sudo().create(xero_product_log_ln)
			return product_id

		else:
			log_id = self.env['xero.log.vts'].sudo().generate_xero_logs(
				xero_operation_name='product',xero_operation_type='import', instance=instance_id,
				xero_operation_message="Error during product import process"
			)
			log_line = self.env['xero.log.vts.line'].sudo().generate_xero_process_line(
				xero_operation_name='product',xero_operation_type='import', instance=instance_id,
				xero_operation_message="Error during product import process",
				process_response_message=pprint.pformat(product_info), log_id=log_id, fault_operation=True)

	def xero_tax_creation(self, tax):
		"""
        Create missing sale/purchase taxes based on Xero tax applicability
        """
		taxes = self.env['account.tax']
		company_id = self.xero_instance_id.company_id.id
		tax_name = tax.get('Name')

		base_tax_vals = {
			'amount_type': 'percent',
			'amount': tax.get('EffectiveRate'),
			'company_id': company_id,
		}

		def _create_taxes(tax_use):
			existing_tax = self.env['account.tax'].sudo().search([
				('name', '=', tax_name),
				('type_tax_use', '=', tax_use),
				('company_id', '=', company_id),
			], limit=1)

			if existing_tax:
				return existing_tax

			vals = dict(base_tax_vals)
			vals.update({
				'name': tax_name,
				'type_tax_use': tax_use,
			})
			return self.env['account.tax'].sudo().create(vals)

		if tax.get('CanApplyToRevenue'):
			taxes |= _create_taxes('sale')

		if tax.get('CanApplyToExpenses'):
			taxes |= _create_taxes('purchase')

		if not tax.get('CanApplyToRevenue') and not tax.get('CanApplyToExpenses'):
			taxes |= _create_taxes('none')

		return taxes

	def get_tax_from_xero(self, tax_info, tax_status):
		"""
		Fetch Taxes from Xero
		"""
		instance_id = self.xero_instance_id.id if self.xero_instance_id else False
		# company = self.xero_instance_id.company_id.id if self.xero_instance_id.company_id else False

		if tax_status == 200 and tax_info and 'TaxRates' in tax_info:
			taxes = tax_info.get('TaxRates', {})

			log_id = self.env['xero.log.vts'].sudo().generate_xero_logs(xero_operation_name='taxes',xero_operation_type='import',
																		instance=instance_id,xero_operation_message='Fetch Taxes From Xero')
			xero_tax_log_ln = []
			xero_map_tax = []
			active_taxes = [tax for tax in taxes if tax.get('Status') == 'ACTIVE']
			for tax in active_taxes:
				xr_tax_name = tax.get('Name', '').strip()
				xr_tax_id = tax.get('TaxType', '')

				tax_id = False
				# if xr_tax_name:
				# 	tax_id = self.env['account.tax'].sudo().search([('name', '=', xr_tax_name),('company_id', '=', company)],limit=1)

				tax_created = False
				if self.xero_instance_id.xero_tax_creation:
					tax_id = self.xero_tax_creation(tax)
					if tax_id:
						tax_created = True

				tax_mapping = self.env['xero.tax.map'].search([('xero_instance_id', '=', instance_id),('xero_tax_id','=',xr_tax_id)],limit=1)
				if not tax_mapping:
					mapping_vals = {
						'xero_instance_id': instance_id,
						'xero_tax_id': xr_tax_id,
						'xero_tax_name': xr_tax_name,
						'tax_id': [(6, 0, tax_id.ids)] if tax_id else [],
						'xero_response': pprint.pformat(tax)
					}
					xero_map_tax.append(mapping_vals)

					if not tax_id:
						msg = f"Failed to create Xero Taxes in Odoo: {xr_tax_name}"
						activity = self._create_import_failure_activity(msg, log_id)
						xero_tax_log_ln.append(
							self.build_xero_log(entity_name='taxes', message=msg, instance_id=instance_id,
											entity_data=tax, log_id=log_id, fault=True))
					elif tax_id:
						if tax_created:
							opr_msg = f"Xero Tax successfully created: {xr_tax_name}"
						else:
							opr_msg = f"Tax successfully updated with xero tax: {xr_tax_name}"
						xero_tax_log_ln.append(
								self.build_xero_log(entity_name='taxes', message=opr_msg, instance_id=instance_id,
													entity_data=tax, log_id=log_id, fault=False))
				else:
					mapping_vals = {'tax_id':[(6, 0, tax_id.ids)] if tax_id else [],'xero_response': pprint.pformat(tax)}
					tax_mapping.sudo().write(mapping_vals)
					opr_msg = f"Tax successfully updated with Xero Tax: {xr_tax_name}"
					xero_tax_log_ln.append(
						self.build_xero_log(entity_name='taxes', message=opr_msg, instance_id=instance_id,
											entity_data=tax, log_id=log_id, fault=False))

			if xero_map_tax:
				tax_map = self.env['xero.tax.map'].sudo().create(xero_map_tax)
			if xero_tax_log_ln:
				tax_log_line = self.env['xero.log.vts.line'].sudo().create(xero_tax_log_ln)
		else:
			log_id = self.env['xero.log.vts'].sudo().generate_xero_logs(
				xero_operation_name='taxes',
				xero_operation_type='import', instance=instance_id,
				xero_operation_message="Error During Taxes Import Process"
			)
			log_line = self.env['xero.log.vts.line'].sudo().generate_xero_process_line(
				xero_operation_name='taxes',
				xero_operation_type='import', instance=instance_id,
				xero_operation_message="Error During Taxes Import Process",
				process_response_message=pprint.pformat(tax_info), log_id=log_id, fault_operation=True)

	def _prepare_invoice_creation(self,inv,partner):
		"""
		This method creates Invoice payload to create invoice in odoo
		"""
		invoice_lines = []
		for line in inv.get('LineItems', []):

			product_ref=False
			item = line.get('Item')
			if item:
				product_ref = item.get('ItemID')
			product_map = self.env['xero.product.map'].sudo().search([('xero_product_id', '=', product_ref),('xero_instance_id','=',self.xero_instance_id.id)], limit=1)
			product = product_map.product_id if product_map else False
			if not product and product_ref:
				product = self._get_data_from_xero_by_id(product_ref,'Items')
			
			account_id = line.get('AccountID')
			if not account_id:
				continue

			account_mapping = self.env['xero.account.map'].sudo().search([('xero_account_id','=',account_id),('account_id','!=',False),('xero_instance_id','=',self.xero_instance_id.id)], limit=1)
			if not account_mapping:
				account_mapping = self._get_data_from_xero_by_id(account_id,'Accounts')
				if account_mapping:
					inv.message_post(body=f"Charts Of Account Successfully exported with ID : {account_mapping.xero_account_id}")
				else:
					msg = "Failed to export charts of account to xero"
					log_id = self.env['xero.log.vts'].sudo().generate_xero_logs(
						xero_operation_name="account", xero_operation_type="export",
						instance=self.xero_instance_id.id,
						xero_operation_message=f"failed to export charts of account tp xero.")
					self.env['xero.log.vts.line'].sudo().generate_xero_process_line(xero_operation_name="account",
						xero_operation_type="export",instance=self.xero_instance_id.id,xero_operation_message=msg,
							log_id=log_id, fault_operation=True)
					return
			account = account_mapping.account_id

			analytic_distribution = {}
			tracking_vals = line.get('Tracking') or []
			for tracking in tracking_vals:

				analytic_map = self.env['xero.analytic.account.map'].sudo().search([('xero_analytic_acc_id', '=', tracking.get('TrackingOptionID')),('analytic_account_id','!=',False),
					('xero_instance_id', '=', self.xero_instance_id.id)], limit=1)
				if analytic_map:
					analytic_distribution[str(analytic_map.analytic_account_id.id)] = 100.0
			tax_id = False
			if line.get('TaxType'):
				tax_mapping = self.env['xero.tax.map'].search([('xero_instance_id', '=', self.xero_instance_id.id), ('xero_tax_id', '=', line.get('TaxType'))],limit=1)
				tax_ids = tax_mapping.tax_id
				for tax in tax_ids:
					if inv.get('Type') in ('ACCPAY', 'ACCPAYCREDIT') and tax.type_tax_use == 'purchase':
						tax_id = tax
					elif inv.get('Type') in ('ACCREC', 'ACCRECCREDIT') and tax.type_tax_use == 'sale':
						tax_id = tax

			invoice_lines.append((0,0,{
				'product_id':product.product_variant_id.id if product and product.product_variant_id else False,
				'name':line.get('Description'),
				'quantity':line.get('Quantity'),
				'tax_ids':[(6, 0, [tax_id.id])] if tax_id else False,
				'price_unit':line.get('UnitAmount'),
				'price_subtotal':line.get('LineAmount'),
				'account_id': account.id if account else False,
				'analytic_distribution': analytic_distribution,
			}))
		currency = None
		currency_code = inv.get('CurrencyCode',())
		if currency_code:
			currency = self.env['res.currency'].sudo().search([('name', '=', currency_code)], limit=1)

		xero_type = inv.get('Type', 'ACCREC')

		move_type_map = {
			'ACCREC': 'out_invoice',
			'ACCRECCREDIT': 'out_refund',
			'ACCPAY': 'in_invoice',
			'ACCPAYCREDIT': 'in_refund',
		}

		move_type = move_type_map.get(xero_type)

		# Determine Xero reference ID
		xero_ref_id = inv.get('InvoiceID', '') if xero_type in ('ACCREC', 'ACCPAY') else inv.get('CreditNoteID', '')

		# Determine document number (Invoice or Credit Note)
		xr_doc_number = inv.get('InvoiceNumber', '') if xero_type in ('ACCREC', 'ACCPAY') else inv.get('CreditNoteNumber', '')

		vals = {
			'move_type': move_type,
			'xero_instance_id':self.xero_instance_id.id,
			'xero_ref_id': xero_ref_id,
			'xr_invoice_num':xr_doc_number,
			'xr_move_type': xero_type,
			'partner_id':partner.id,
			'invoice_date': inv.get('DateString') and inv['DateString'][:10] or False,
			'invoice_date_due': inv.get('DueDateString') and inv['DueDateString'][:10] or False,
			'ref':inv.get('Reference'),
			'invoice_line_ids':invoice_lines,
			'company_id': self.xero_instance_id.company_id.id,
		}

		if currency:
			vals['currency_id'] = currency.id

		invoice_detail = self.env['account.move'].sudo().create(vals)
		if invoice_detail:
			invoice_detail.with_context(move_import_create=True).action_post()

		return invoice_detail

	def get_invoice_from_xero(self, all_invoices, log_id=False):
		"""
			Fetch Invoices from Xero
		"""
		instance_id = self.xero_instance_id.id if self.xero_instance_id else False
		company = self.xero_instance_id.company_id.id if self.xero_instance_id.company_id else False

		if not log_id:
			log_id = self.env['xero.log.vts'].sudo().generate_xero_logs(xero_operation_name='invoice',
				xero_operation_type='import',instance=instance_id,xero_operation_message='Fetch Invoices From Xero')

		xero_invoice_log_ln = []
		invoice_detail = False
		for inv in all_invoices:
			xr_invoice_number = inv.get('InvoiceNumber','')
			xr_move_id = inv.get('InvoiceID', '')
			xr_partner_ref = inv.get('Contact')

			if xr_move_id:
				invoice_detail = self.env['account.move'].sudo().search([ ('xero_ref_id', '=', xr_move_id),
					 ('xero_instance_id', '=', instance_id)], limit=1)

			if not invoice_detail and xr_invoice_number:
				invoice_detail = self.env['account.move'].sudo().search([('name','=',xr_invoice_number),('company_id', '=', company)], limit=1)

			partner = False
			if xr_partner_ref:
				partner_map = self.env['xero.partner.map'].sudo().search([
					('xero_instance_id', '=', instance_id),('xero_contact_id', '=', xr_partner_ref.get('ContactID'))], limit=1)
				partner = partner_map.partner_id if partner_map else False

			if not partner:
				partner = self._get_data_from_xero_by_id(xr_partner_ref.get('ContactID'),'Contacts')
				opr_msg = "Partner Successfully Imported from Xero"
				xero_invoice_log_ln.append(
						self.build_xero_log(entity_name='partner', message=opr_msg, instance_id=instance_id,
											entity_data=partner, log_id=log_id, fault=False))
			inv_created = False
			if not invoice_detail:
				invoice_detail = self._prepare_invoice_creation(inv, partner)
				inv_created = True

			if not invoice_detail:
				msg = f"Failed to create Xero Invoice in Odoo: {xr_invoice_number}"
				activity = self._create_import_failure_activity(msg, log_id)
				xero_invoice_log_ln.append(
					self.build_xero_log(entity_name='invoice', message=msg, instance_id=instance_id,
										entity_data=inv, log_id=log_id, fault=True))

			elif invoice_detail:
				invoice_detail.write({'xero_instance_id': instance_id,
									  'xero_ref_id':xr_move_id,
									  'xr_invoice_num':xr_invoice_number})
				if inv_created:
					opr_msg = f"Xero Invoice successfully created: {xr_invoice_number}"
				else:
					opr_msg = f"Invoice successfully updated with Xero Invoice: {xr_invoice_number}"
				xero_invoice_log_ln.append(
					self.build_xero_log(entity_name='invoice', message=opr_msg, instance_id=instance_id,
										entity_data=inv, log_id=log_id, fault=False))

		if xero_invoice_log_ln:
			inv_log_line = self.env['xero.log.vts.line'].sudo().create(xero_invoice_log_ln)
		return invoice_detail

	def _prepare_payment_creation(self,payment, partner):
		"""
		This method creates Payment payload to create Payment in odoo
		"""
		payment_type = payment.get('PaymentType')
		customer_payment  = payment_type =='ACCRECPAYMENT'
		vendor_payment = payment_type == 'ACCPAYPAYMENT'

		payment_vals = {
			'xero_instance_id':self.xero_instance_id.id,
			'xero_payment_id': payment.get('PaymentID'),
			'partner_id': partner.id if partner else False,
			'amount': payment.get('Amount'),
			'date': datetime.fromtimestamp(int(re.search(r'/Date\((\d+)', payment.get('Date', '') or '0').group(1)) / 1000,tz=timezone.utc).date(),
			'payment_type': 'inbound' if customer_payment else 'outbound',
			'partner_type': 'customer' if customer_payment else 'supplier',
			'company_id': self.xero_instance_id.company_id.id,
		}
		acc_move_id = payment.get('Invoice')
		invoice = False
		# for move in acc_move_id:
		if payment_type == 'ACCRECPAYMENT':
			invoice = self.env['account.move'].search([('xero_ref_id', '=',acc_move_id.get('InvoiceID')),('xero_instance_id','=',self.xero_instance_id.id)], limit=1)
		elif payment_type == 'ACCPAYPAYMENT':
			invoice = self.env['account.move'].search([('xero_ref_id', '=',acc_move_id.get('InvoiceID')),('xero_instance_id','=',self.xero_instance_id.id)], limit=1)

		if not invoice:
			return
		if invoice and sum(invoice.mapped('amount_residual')) <= 0.0:
			return

		payment_vals['invoice_ids'] = [(6, 0, invoice.ids)]
		payment_details = self.env['account.payment'].create(payment_vals)

		return payment_details

	def get_payments_from_xero(self,payment_info, payment_status):
		"""
		   Fetch payment from Xero
		"""
		instance_id = self.xero_instance_id.id if self.xero_instance_id else False
		company = self.xero_instance_id.company_id.id if self.xero_instance_id.company_id else False

		if payment_status == 200 and payment_info and 'Payments' in payment_info:
			payments = payment_info.get('Payments', {})

			log_id = self.env['xero.log.vts'].sudo().generate_xero_logs(xero_operation_name='payment',xero_operation_type='import',
																		instance=instance_id,xero_operation_message='Fetch Payment From Xero')
			xero_payment_log_ln = []
			for payment in payments:
				xr_partner_ref = payment.get('Invoice').get('Contact').get('ContactID')
				xero_payment_id = payment.get('PaymentID')

				payment_detail = False
				if xero_payment_id:
					payment_detail = self.env['account.payment'].sudo().search(
						[('xero_payment_id', '=',xero_payment_id),('xero_instance_id', '=',instance_id),('company_id','=',company)],limit=1)

				partner = False
				if xr_partner_ref:
					partner_map = self.env['xero.partner.map'].sudo().search([
						('xero_instance_id', '=', instance_id),
						('xero_contact_id', '=', xr_partner_ref )], limit=1)
					partner = partner_map.partner_id if partner_map else False

				if not partner:
					partner = self._get_data_from_xero_by_id(xr_partner_ref,'Contacts')
					opr_msg = "Partner Successfully Imported from Xero"
					xero_payment_log_ln.append(
						self.build_xero_log(entity_name='partner', message=opr_msg, instance_id=instance_id,
											entity_data=partner, log_id=log_id, fault=False))

				pay_created = False
				if not payment_detail:
					payment_detail = self._prepare_payment_creation(payment, partner)
					if payment_detail:
						pay_created =  True

				if not payment_detail:
					msg = f"Failed to create Xero Payment in Odoo: {xero_payment_id}"
					activity = self._create_import_failure_activity(msg, log_id)
					xero_payment_log_ln.append(
						self.build_xero_log(entity_name='payment', message=msg, instance_id=instance_id,
											entity_data=payment, log_id=log_id, fault=True))

				elif payment_detail:
					payment_detail.write({'xero_instance_id': instance_id,
										  'xero_payment_id': xero_payment_id,
										  'xero_payment_type': "ACCRECPAYMENT" if payment.get("Type") == "ACCRECPAYMENT" else "ACCPAYPAYMENT",
										  })

					if pay_created:
						opr_msg = "Xero Payment successfully Created"
					else:
						opr_msg = "Payment successfully Updated with Xero Payment"
					xero_payment_log_ln.append(
						self.build_xero_log(entity_name='payment', message=opr_msg, instance_id=instance_id,
											entity_data=payment, log_id=log_id, fault=False))
			if xero_payment_log_ln:
				payment_log_line = self.env['xero.log.vts.line'].sudo().create(xero_payment_log_ln)
		else:
			log_id = self.env['xero.log.vts'].sudo().generate_xero_logs(
				xero_operation_name='payment',
				xero_operation_type='import', instance=instance_id,
				xero_operation_message="Error During payment Import Process"
			)
			log_line = self.env['xero.log.vts.line'].sudo().generate_xero_process_line(
				xero_operation_name='payment',
				xero_operation_type='import', instance=instance_id,
				xero_operation_message="Error During Payment Import Process",
				process_response_message=pprint.pformat(payment_info), log_id=log_id, fault_operation=True)

	def get_analytic_account_from_xero(self,analytic_acc_info, analytic_acc_status):
		instance_id = self.xero_instance_id.id if self.xero_instance_id else False

		if analytic_acc_status == 200 and analytic_acc_info and 'TrackingCategories' in analytic_acc_info:
			tracking_categories = analytic_acc_info.get('TrackingCategories',{})

			log_id = self.env['xero.log.vts'].sudo().generate_xero_logs(xero_operation_name='tracking_category',xero_operation_type='import',
																		instance=instance_id,xero_operation_message='Fetch Tracking Category From Xero')
			tracking_categ_map = []
			xero_tracking_categ_log_ln =[]
			for tracking_categ in tracking_categories:
				xr_categ_name = tracking_categ.get('Name')

				analytic_plan = False
				if xr_categ_name:
					analytic_plan = self.env['account.analytic.plan'].search([('name', '=', xr_categ_name)], limit=1)

				if not analytic_plan and self.xero_instance_id.xero_analytic_creation:
					analytic_plan  = self.env['account.analytic.plan'].sudo().create({'name': tracking_categ.get('Name')})

				category_created = False
				tracking_option = tracking_categ.get('Options')
				for option in tracking_option:
					analytic_account = self.env['account.analytic.account'].sudo().search([('name', '=', option.get('Name')),('plan_id','=',analytic_plan.id)], limit=1)

					if not analytic_account and analytic_plan:
						analytic_account_vals = {
							'name': option.get('Name'),
							'plan_id': analytic_plan.id,
						}
						analytic_account = self.env['account.analytic.account'].sudo().create(analytic_account_vals)
						category_created = True

					tracking_category = self.env['xero.analytic.account.map'].search([('xero_analytic_acc_id', '=', option.get('TrackingOptionID')),
						 ('xero_analytic_acc_name', '=', option.get('Name'))], limit=1)

					if not tracking_category:
						mapping_vals = {
							'xero_instance_id': instance_id,
							'xero_analytic_acc_name':option.get('Name'),
							'xero_analytic_acc_id': option.get('TrackingOptionID'),
							'analytic_account_id':analytic_account.id if analytic_account else False,
							'xero_analytic_plan_id': tracking_categ.get('TrackingCategoryID'),
							'analytic_plan_id': analytic_account.plan_id.id if analytic_account and analytic_account.plan_id else False,
							'xero_response': pprint.pformat(option),
						}
						tracking_categ_map.append(mapping_vals)
						if not analytic_account:
							msg = f"Failed to create Xero Tracking Categories Option in Odoo : {option.get('Name')}"
							activity = self._create_import_failure_activity(msg, log_id)
							xero_tracking_categ_log_ln.append(
								self.build_xero_log(entity_name='tracking_category', message=msg, instance_id=instance_id,
													entity_data=tracking_option, log_id=log_id, fault=True))
						elif analytic_account:
							if category_created:
								opr_msg = f"Xero Tracking Category option successfully created: {option.get('Name')}"
							else:
								opr_msg = f"Tracking Category Option successfully updated with Xero Tracking Categories:{option.get('Name')}"
							xero_tracking_categ_log_ln.append(
								self.build_xero_log(entity_name='tracking_category', message=opr_msg, instance_id=instance_id,
													entity_data=tracking_option, log_id=log_id, fault=False))
					else:
						tracking_category.sudo().write({'analytic_account_id':analytic_account.id if analytic_account else False,'xero_response': pprint.pformat(option)})
						opr_msg = f"Tracking Category Option updated with Xero Tracking Categories Option : {option.get('Name')}"
						xero_tracking_categ_log_ln.append(
							self.build_xero_log(entity_name='tracking_category', message=opr_msg, instance_id=instance_id,
												entity_data=tracking_option, log_id=log_id, fault=False))
			if tracking_categ_map:
				analytic_account_map = self.env['xero.analytic.account.map'].sudo().create(tracking_categ_map)
			if xero_tracking_categ_log_ln:
				analytic_account_log_line = self.env['xero.log.vts.line'].sudo().create(xero_tracking_categ_log_ln)
		else:
			log_id = self.env['xero.log.vts'].sudo().generate_xero_logs(xero_operation_name='tracking_category',xero_operation_type='import',
																		instance=instance_id,xero_operation_message="Error during Tracking Category import process")
			log_line = self.env['xero.log.vts.line'].sudo().generate_xero_process_line(xero_operation_name='tracking_category',xero_operation_type='import',
				instance=instance_id,xero_operation_message="Error during Tracking Category import process",process_response_message=pprint.pformat(analytic_acc_info),
				log_id=log_id,fault_operation=True)

	def _prepare_contact_group_creation(self,group,log_id):

		category_id=self.env['res.partner.category'].sudo().create({'name':group.get('Name', '').strip()})

		contact = group.get('Contacts')
		for partner in contact:
			mapping_partner = self.env['xero.partner.map'].sudo().search([('xero_contact_id','=',partner.get('ContactID')),('partner_id','!=',False)],limit=1)
			if not mapping_partner:
				mapping_partner = self._get_data_from_xero_by_id(partner.get('ContactID'), 'Contacts')

			mapping_partner.partner_id.write({'category_id': [(4, category_id.id)]})
			self.build_xero_log(entity_name='partner', message=f"Tag successfully added in xero partner:{mapping_partner.xero_contact_name} ", instance_id=self.xero_instance_id.id,
							entity_data=partner, log_id=log_id, fault=False)

		return category_id

	def get_contact_group_from_xero(self,all_contact_group):
		"""
			Fetch Contact Groups from Xero
		"""
		instance_id = self.xero_instance_id.id if self.xero_instance_id else False

		log_id = self.env['xero.log.vts'].sudo().generate_xero_logs(xero_operation_name='contact_group',xero_operation_type='import',
																	instance=instance_id,xero_operation_message='Fetch Contact Group From Xero')
		xero_contact_group_log_ln = []
		xero_map_contact_group = []
		for group in all_contact_group:
			for gp in group:
				xr_group_name = gp.get('Name', '').strip()
				xr_contact_group_id = gp.get('ContactGroupID')

				contact_group= False
				if xr_group_name:
					contact_group = self.env['res.partner.category'].sudo().search([('name','=',xr_group_name)],limit=1)
				group_created =False
				if not contact_group and self.xero_instance_id.xero_contact_group_creation:
					contact_group = self._prepare_contact_group_creation(gp,log_id)
					group_created = True

				mapping_group = self.env['xero.contact.group.map'].sudo().search([('xero_group_name','=',xr_group_name),('xero_group_id','=',xr_contact_group_id)],limit=1)

				if not mapping_group:
					mapping_vals={
						'xero_instance_id':instance_id,
						'xero_group_id':xr_contact_group_id,
						'xero_group_name':xr_group_name,
						'category_id':contact_group.id if contact_group else False,
						'xero_response':pprint.pformat(gp)
					}
					xero_map_contact_group.append(mapping_vals)

					if not contact_group:
						msg = f"Failed to create Xero Contact Group in Odoo: {xr_group_name}"
						activity = self._create_import_failure_activity(msg, log_id)
						xero_contact_group_log_ln.append(
							self.build_xero_log(entity_name='contact_group', message=msg, instance_id=instance_id,
												entity_data=gp, log_id=log_id, fault=True))
					elif contact_group:
						if group_created:
							opr_msg = f"Xero Contact Group successfully created: {xr_group_name}"
						else:
							opr_msg = f"Contact Group successfully updated with Xero Contact Group: {xr_group_name}"
							xero_contact_group_log_ln.append(
								self.build_xero_log(entity_name='contact_group', message=opr_msg, instance_id=instance_id,
													entity_data=gp, log_id=log_id, fault=False))
				else:
					mapping_group.sudo().write({'category_id':contact_group.id if contact_group else False,'xero_response': pprint.pformat(gp)})
					opr_msg = f"Contact Group updated with Xero Tracking Categories Option : {xr_group_name}"
					xero_contact_group_log_ln.append(
						self.build_xero_log(entity_name='contact_group', message=opr_msg, instance_id=instance_id,
											entity_data=group, log_id=log_id, fault=False))
		if xero_map_contact_group:
			contact_group_map = self.env['xero.contact.group.map'].sudo().create(xero_map_contact_group)
		if xero_contact_group_log_ln:
			contact_group_log_line = self.env['xero.log.vts.line'].sudo().create(xero_contact_group_log_ln)

	def get_credit_note_from_xero(self, all_credit_note, log_id=False):
		"""
		  Fetch Credit note  from Xero
		"""
		instance_id = self.xero_instance_id.id if self.xero_instance_id else False

		if not log_id:
			log_id = self.env['xero.log.vts'].sudo().generate_xero_logs(xero_operation_name='credit_note',xero_operation_type='import',
																	instance=instance_id,xero_operation_message='Fetch Credit Note From Xero')
		xero_credit_note_log_ln = []
		credit_details = False
		for creditnote in all_credit_note:
			xr_credit_number = creditnote.get('CreditNoteNumber')
			xr_credit_note_id =creditnote.get('CreditNoteID')
			xr_contact_ref = creditnote.get('Contact').get('ContactID')

			if xr_credit_note_id:
				credit_details = self.env['account.move'].sudo().search(
					[('xero_ref_id', '=', xr_credit_note_id),('xero_instance_id', '=', instance_id)], limit=1)
			if not credit_details and xr_credit_number:
				credit_details = self.env['account.move'].sudo().search([('name','=',xr_credit_number), ('company_id', '=', self.xero_instance_id.company_id.id)], limit=1)

			partner = False
			if xr_contact_ref:
				partner_map = self.env['xero.partner.map'].sudo().search(
					[('xero_instance_id', '=', instance_id),
					('xero_contact_id', '=', xr_contact_ref)], limit=1)
				partner = partner_map.partner_id if partner_map else False

			if not partner:
				partner = self._get_data_from_xero_by_id(xr_contact_ref, 'Contacts')
				opr_msg = "Partner Successfully Imported from Xero"
				xero_credit_note_log_ln.append(
					self.build_xero_log(entity_name='partner', message=opr_msg, instance_id=instance_id,
										entity_data=partner, log_id=log_id, fault=False))
			cr_note_created = False
			if not credit_details:
				credit_details = self._prepare_invoice_creation(creditnote, partner)
				cr_note_created = True

			if not credit_details:
				msg = f"Failed to create Xero Credit Note in Odoo: {xr_credit_number}"
				activity = self._create_import_failure_activity(msg, log_id)
				xero_credit_note_log_ln.append(self.build_xero_log(entity_name='credit_note', message=msg, instance_id=instance_id,
										entity_data=creditnote, log_id=log_id, fault=True))
			elif credit_details:
				credit_details.write({'xero_instance_id': instance_id,'xero_ref_id':xr_credit_note_id})
				if cr_note_created:
					opr_msg = f"Xero Credit Note successfully created: {xr_credit_number}"
				else:
					opr_msg = f"Credit Note successfully updated with Xero Invoice: {xr_credit_number}"
				xero_credit_note_log_ln.append(
					self.build_xero_log(entity_name='credit_note', message=opr_msg, instance_id=instance_id,
										entity_data=creditnote, log_id=log_id, fault=False))
		if xero_credit_note_log_ln:
			credit_note_log_line = self.env['xero.log.vts.line'].sudo().create(xero_credit_note_log_ln)
		return credit_details

	def prepare_pre_over_payment_creation(self,payment,partner):
		"""
		Fetch Pre Payment  from Xero
		"""
		payment_type = payment.get('Type')
		customer_payment = payment_type in ('RECEIVE-PREPAYMENT','RECEIVE-OVERPAYMENT')
		pre_payment = payment_type in ('RECEIVE-PREPAYMENT', 'SPEND-PREPAYMENT')
		over_payment = payment_type in ('RECEIVE-OVERPAYMENT', 'SPEND-OVERPAYMENT')
		xero_payment_id = payment.get('PrepaymentID') if pre_payment else payment.get('OverpaymentID')

		payment_vals = {
			'xero_instance_id': self.xero_instance_id.id,
			'xero_payment_id': xero_payment_id,
			'partner_id': partner.id if partner else False,
			'amount': payment.get('Total'),
			'date': datetime.fromtimestamp(int(re.search(r'/Date\((\d+)', payment.get('Date', '') or '0').group(1)) / 1000,tz=timezone.utc).date(),
			'payment_type': 'inbound' if customer_payment else 'outbound',
			'partner_type': 'customer' if customer_payment else 'supplier',
			'company_id': self.xero_instance_id.company_id.id,
		}

		allocations = payment.get('Allocations')
		if not allocations:
			return self.env['account.payment'].create(payment_vals)
		invoice_ids = []
		for allocation in allocations:
			invoice_data = allocation.get('Invoice') or {}
			xero_invoice_id = invoice_data.get('InvoiceID')
			if customer_payment:
				invoice = self.env['account.move'].search([('xero_ref_id', '=', xero_invoice_id),
					('xero_instance_id', '=', self.xero_instance_id.id)], limit=1)
			else:
				invoice = self.env['account.move'].search([('xero_ref_id', '=', xero_invoice_id),
						('xero_instance_id', '=', self.xero_instance_id.id)], limit=1)
			if not invoice:
				return
			if invoice and sum(invoice.mapped('amount_residual')) <= 0.0:
				return
			invoice_ids.append(invoice.id)
		payment_vals['invoice_ids'] = [(6,0,invoice_ids)]
		payment_details = self.env['account.payment'].create(payment_vals)
		return payment_details

	def get_prepayment_from_xero(self,pre_payment_info,pre_payment_status):

		instance_id = self.xero_instance_id.id if self.xero_instance_id else False
		company = self.xero_instance_id.company_id.id if self.xero_instance_id.company_id else False

		if pre_payment_status == 200 and pre_payment_info and 'Prepayments' in pre_payment_info:
			pre_payments = pre_payment_info.get('Prepayments', [])

			log_id = self.env['xero.log.vts'].sudo().generate_xero_logs(xero_operation_name='pre_payment',xero_operation_type='import',
																		instance=instance_id,xero_operation_message='Fetch Pre Payment From Xero')

			xero_pre_payment_log_ln = []
			for pre_payment in pre_payments:
				if pre_payment.get('Status') == 'DELETED':
					continue
				xr_partner_ref = pre_payment.get('Contact').get('ContactID')
				xero_prepayment_id = pre_payment.get('PrepaymentID')

				pre_payment_detail=False
				if xero_prepayment_id:
					pre_payment_detail = self.env['account.payment'].sudo().search( [('xero_payment_id', '=', xero_prepayment_id),('xero_instance_id', '=',instance_id),('company_id','=',company)],limit=1)

				partner=False
				if xr_partner_ref:
					partner_map = self.env['xero.partner.map'].sudo().search([('xero_instance_id', '=', instance_id),
						('xero_contact_id', '=', xr_partner_ref)], limit=1)
					partner = partner_map.partner_id if partner_map else False

				if not partner:
					partner = self._get_data_from_xero_by_id(xr_partner_ref, 'Contacts')
					opr_msg = "Partner Successfully Imported from Xero"
					xero_pre_payment_log_ln.append(
						self.build_xero_log(entity_name='partner', message=opr_msg, instance_id=instance_id,
											entity_data=partner, log_id=log_id, fault=False))

				pre_payment_created=False
				if not pre_payment_detail:
					pre_payment_detail = self.prepare_pre_over_payment_creation(pre_payment,partner)
					if pre_payment_detail:
						pre_payment_created=True

				if not pre_payment_detail:
					msg = f"Failed to create xero Pre Payment in odoo: {xero_prepayment_id}"
					activity = self._create_import_failure_activity(msg, log_id)
					xero_pre_payment_log_ln.append(
						self.build_xero_log(entity_name='pre_payment', message=msg, instance_id=instance_id,
											entity_data=pre_payment, log_id=log_id, fault=True))

				elif pre_payment_detail:
					vals = {'xero_instance_id': instance_id,
							'xero_payment_id': xero_prepayment_id,
							'xero_payment_type' : "RECEIVE-PREPAYMENT" if pre_payment.get('Type') == 'RECEIVE-PREPAYMENT' else "SPEND-PREPAYMENT",
							}
					pre_payment_detail.write(vals)

				if pre_payment_created:
					opr_msg = "Xero Pre Payment successfully Created"
				else:
					opr_msg = "Pre Payment successfully Updated with Xero Pre Payment"
				xero_pre_payment_log_ln.append(
					self.build_xero_log(entity_name='pre_payment', message=opr_msg, instance_id=instance_id,
										entity_data=pre_payment, log_id=log_id, fault=False))
			if xero_pre_payment_log_ln:
				payment_log_line = self.env['xero.log.vts.line'].sudo().create(xero_pre_payment_log_ln)
		else:
			log_id = self.env['xero.log.vts'].sudo().generate_xero_logs(
				xero_operation_name='pre_payment',
				xero_operation_type='import', instance=instance_id,
				xero_operation_message="Error During pre payment Import Process"
			)
			log_line = self.env['xero.log.vts.line'].sudo().generate_xero_process_line(
				xero_operation_name='pre_payment',
				xero_operation_type='import', instance=instance_id,
				xero_operation_message="Error During Pre Payment Import Process",
				process_response_message=pprint.pformat(pre_payment_info), log_id=log_id, fault_operation=True)

	def _prepare_purchase_order_creation(self,order,partner):
		"""
		Prepare purchase.order create vals from Xero purchase order payload

		:param order: dict -> Xero purchase order payload
		:param partner: res.partner -> Vendor
		:return: dict -> purchase.order create vals
		"""
		PurchaseOrderLine = []

		for line in order.get('LineItems', []):
			product = False
			if line.get('ItemCode'):
				product = self.env['product.template'].sudo().search([('default_code', '=', line.get('ItemCode'))],limit=1)
				# if not product and line.get('ItemCode'):
				#     product = self._get_data_from_xero_by_id(line.get('ItemCode'), 'Items')

			tax_id = False
			if line.get('TaxType'):
				tax_mapping = self.env['xero.tax.map'].search([('xero_instance_id', '=', self.xero_instance_id.id), ('xero_tax_id', '=', line.get('TaxType'))], limit=1)
				tax_ids = tax_mapping.tax_id
				for tax in tax_ids:
				   if tax.type_tax_use == 'purchase':
					   tax_id = tax

			analytic_distribution = {}
			tracking_vals = line.get('Tracking') or []
			for tracking in tracking_vals:

				analytic_map = self.env['account.analytic.account'].sudo().search([('name', '=', tracking.get('Option')),('plan_id', '=',tracking.get('Name'))], limit=1)
				if analytic_map:
					analytic_distribution[str(analytic_map.id)] = 100.0
			product_variant = product.product_variant_id if product and product.product_variant_id else False
			uom = product_variant.uom_id if product_variant else self.env.ref('uom.product_uom_unit')

			PurchaseOrderLine.append(
				(0, 0, {
					'product_id': product.product_variant_id.id  if product and product.product_variant_id else False,
					'name': line.get('Description'),
					'product_qty': line.get('Quantity'),
					'uom_id': uom.id,
					'price_unit': line.get('UnitAmount'),
					'tax_ids': [(6, 0, [tax_id.id])] if tax_id else False,
					'date_planned': (order.get('DeliveryDateString') or '').replace('T', ' '),
					'analytic_distribution': analytic_distribution,
				})
			)
		currency = self.env['res.currency'].search([('name', '=', order.get('CurrencyCode'))],limit=1)

		purchase_vals = {
			'partner_id': partner.id,
			# 'partner_ref': order.get('PurchaseOrderNumber'),
			'origin': order.get('Reference'),
			'date_order': (order.get('DateString') or '').replace('T', ' '),
			'date_planned': (order.get('DeliveryDateString') or '').replace('T', ' '),
			'currency_id': currency.id if currency else self.env.company.currency_id.id,
			# 'notes': order.get('DeliveryInstructions'),
			'order_line': PurchaseOrderLine,
			'xero_po_id': order.get('PurchaseOrderID'),
			'xero_instance_id':self.xero_instance_id.id if self.xero_instance_id else False,
			'xero_po_number':order.get('PurchaseOrderNumber')
		}

		purchase_details = self.env['purchase.order'].sudo().create(purchase_vals)

		return purchase_details

	def get_purchase_order_from_xero(self,po_info,po_status):
		"""
		   Fetch Purchase Order from Xero
		"""
		instance_id = self.xero_instance_id.id if self.xero_instance_id else False
		company = self.xero_instance_id.company_id.id if self.xero_instance_id.company_id else False
		if po_status == 200 and po_info and 'PurchaseOrders' in po_info:
			purchase_order = po_info.get('PurchaseOrders', {})

			log_id = self.env['xero.log.vts'].sudo().generate_xero_logs(xero_operation_name='purchase_order',xero_operation_type='import',
																		instance=instance_id,xero_operation_message='Fetch Purchase Order From Xero')
			xero_po_log_ln = []
			po_detail = False
			for order in purchase_order:
				xr_partner_ref = order.get('Contact').get('ContactID')
				xr_po_id = order.get('PurchaseOrderID')
				xr_po_number = order.get('PurchaseOrderNumber')

				if xr_po_id:
					po_detail = self.env['purchase.order'].sudo().search([('xero_po_id', '=', xr_po_id),('xero_instance_id', '=', instance_id),
																		  ('company_id', '=', company)], limit=1)
				partner = False
				if xr_partner_ref:
					partner_map = self.env['xero.partner.map'].sudo().search([('xero_instance_id', '=', instance_id),('xero_contact_id', '=', xr_partner_ref)], limit=1)
					partner = partner_map.partner_id if partner_map else False

				if not partner:
					partner = self._get_data_from_xero_by_id(xr_partner_ref, 'Contacts')
					opr_msg = "Partner Successfully Imported from Xero"
					xero_po_log_ln.append(
						self.build_xero_log(entity_name='purchase_order', message=opr_msg, instance_id=instance_id,
											entity_data=order, log_id=log_id, fault=False))
				po_created = False
				if not po_detail:
					po_detail = self._prepare_purchase_order_creation(order, partner)
					if po_detail:
						po_created = True

				if not po_detail:
					msg = f"Failed to create Xero Purchase Order in Odoo: {xr_po_id}"
					activity = self._create_import_failure_activity(msg, log_id)
					xero_po_log_ln.append(
						self.build_xero_log(entity_name='purchase_order', message=msg, instance_id=instance_id,
											entity_data=order, log_id=log_id, fault=True))
				elif po_detail:
					po_detail.write({'xero_instance_id': instance_id,'xero_po_id':xr_po_id,'xero_po_number':xr_po_number})
					if po_created:
						opr_msg = "Xero Purchase Order successfully Created"
					else:
						opr_msg = "Purchase Order successfully Updated with Xero Purchase Order"
					xero_po_log_ln.append(
						self.build_xero_log(entity_name='purchase_order', message=opr_msg, instance_id=instance_id,
											entity_data=order, log_id=log_id, fault=False))
			if xero_po_log_ln:
				payment_log_line = self.env['xero.log.vts.line'].sudo().create(xero_po_log_ln)

		else:
			log_id = self.env['xero.log.vts'].sudo().generate_xero_logs(xero_operation_name='purchase_order',xero_operation_type='import',
					instance=instance_id,xero_operation_message="Error During Purchase Order Import Process")
			log_line = self.env['xero.log.vts.line'].sudo().generate_xero_process_line(xero_operation_name='purchase_order',
					xero_operation_type='import', instance=instance_id,xero_operation_message="Error During Purchase Order Import Process",
					process_response_message=pprint.pformat(po_info), log_id=log_id, fault_operation=True)


	def get_overpayment_from_xero(self, overpayment_info, overpayment_status):
		"""
		Fetch Over Payments from Xero
		"""
		instance_id = self.xero_instance_id.id if self.xero_instance_id else False
		company = self.xero_instance_id.company_id.id if self.xero_instance_id.company_id else False

		if overpayment_status == 200 and overpayment_info and 'Overpayments' in overpayment_info:
			over_payments = overpayment_info.get('Overpayments', [])

			log_id = self.env['xero.log.vts'].sudo().generate_xero_logs(xero_operation_name='over_payment',xero_operation_type='import',instance=instance_id,
																		xero_operation_message='Fetch Over Payment From Xero')
			xero_over_payment_log_ln = []
			for payment in over_payments:
				xr_partner_ref = payment.get('Contact').get('ContactID')
				xero_overpayment_id = payment.get('OverpaymentID')

				over_payment_detail = False
				if xero_overpayment_id:
					over_payment_detail = self.env['account.payment'].sudo().search([('xero_payment_id','=',xero_overpayment_id), ('xero_instance_id', '=', instance_id),('company_id', '=', company)], limit=1)

				partner = False
				if xr_partner_ref:
					partner_map = self.env['xero.partner.map'].sudo().search([('xero_instance_id', '=', instance_id),('xero_contact_id', '=', xr_partner_ref)],limit=1)
					partner = partner_map.partner_id if partner_map else False

				if not partner:
					partner = self._get_data_from_xero_by_id(xr_partner_ref, 'Contacts')
					opr_msg = "Partner Successfully Imported from Xero"
					xero_over_payment_log_ln.append(
						self.build_xero_log(entity_name='partner', message=opr_msg, instance_id=instance_id,
										entity_data=partner, log_id=log_id, fault=False))

				over_payment_created = False
				if not over_payment_detail:
					over_payment_detail = self.prepare_pre_over_payment_creation(payment,partner)
					if over_payment_detail:
						over_payment_created = True

				if not over_payment_detail:
					msg = f"Failed to create xero Over Payment in odoo: {xero_overpayment_id}"
					activity = self._create_import_failure_activity(msg, log_id)
					xero_over_payment_log_ln.append(
						self.build_xero_log(entity_name='over_payment', message=msg, instance_id=instance_id,
											entity_data=payment, log_id=log_id, fault=True))
				elif over_payment_detail:
					vals = {
						'xero_instance_id': instance_id,
						'xero_payment_id': xero_overpayment_id,
						'xero_payment_type': "RECEIVE-OVERPAYMENT" if payment.get('Type') == 'RECEIVE-OVERPAYMENT' else "SPEND-OVERPAYMENT",
					}
					over_payment_detail.write(vals)
				if over_payment_created:
					opr_msg = "Xero Over Payment Successfully Created "
				else:
					opr_msg = "Over Payment Successfully Updated with Xero Over Payment "
				xero_over_payment_log_ln.append(
					self.build_xero_log(entity_name='over_payment', message=opr_msg, instance_id=instance_id,
										entity_data=payment ,log_id=log_id, fault=False))
			if xero_over_payment_log_ln:
				over_payment_log_ln = self.env['xero.log.vts.line'].sudo().create(xero_over_payment_log_ln)
		else:
			log_id = self.env['xero.log.vts'].sudo().generate_xero_logs(xero_operation_name='over_payment',
				xero_operation_type='import', instance=instance_id,xero_operation_message="Error During Over Payment Import Process")
			log_line = self.env['xero.log.vts.line'].sudo().generate_xero_process_line(xero_operation_name='over_payment',
				xero_operation_type='import', instance=instance_id,xero_operation_message="Error During Over Payment Import Process",
				process_response_message=pprint.pformat(overpayment_info), log_id=log_id, fault_operation=True)

	def execute_import_process_from_xero(self):
		"""
		Executes all the operation of importing Data from Xero
		"""
		xero_url = self.xero_instance_id.xero_base_url
		company_id = self.xero_instance_id.tenant_id
		token = self.xero_instance_id.access_token

		if self.import_operations == 'import_customers':
			# Import Customers / Vendors
			customer_info, customer_status = self.env['xero.api.vts'].get_data_from_xero(
				xero_url, company_id, token, self.import_operations, self.import_from_date,self.import_to_date)
			xero_customer_details = self.get_customer_from_xero(customer_info, customer_status)

			# Import Contact Groups
			contact_group_info, contact_group_status = self.env['xero.api.vts'].get_data_from_xero(
				xero_url, company_id, token, 'import_contact_groups')

			xero_contact_groups = self.get_contact_from_contact_group(xero_url,contact_group_info,contact_group_status)

		elif self.import_operations == 'import_accounts':

			# Import Chart of Account
			account_info, account_status = self.env['xero.api.vts'].get_data_from_xero(
				xero_url, company_id, token, self.import_operations)
			xero_account_details = self.get_account_from_xero(account_info, account_status)

			# Import Analytic Account
			analytic_acc_info, analytic_acc_status = self.env['xero.api.vts'].get_data_from_xero(
				xero_url, company_id, token, 'import_analytic_account')

			xero_tracking_categories = self.get_analytic_account_from_xero(analytic_acc_info, analytic_acc_status)

			# Import Taxes
			tax_info, tax_status = self.env['xero.api.vts'].get_data_from_xero(
				xero_url, company_id, token, 'import_taxes')

			xero_tax_details = self.get_tax_from_xero(tax_info, tax_status)

		elif self.import_operations == 'import_products':
			product_info, product_status = self.env['xero.api.vts'].get_data_from_xero(
				xero_url, company_id, token, self.import_operations)
			xero_product_details = self.get_product_from_xero(product_info, product_status)


		elif self.import_operations == 'import_invoice':
			invoices_info, invoices_status = self.env['xero.api.vts'].get_data_from_xero(
				xero_url, company_id, token, self.import_operations)

			invoice_list = invoices_info.get("Invoices", [])

			if invoices_info:
				queue_ids = self.env['move.data.queue'].create_xero_invoice_queue_job(self.xero_instance_id, invoice_list)

				if queue_ids:
					model_action = "xero_odoo_integration.action_xero_invoice_queue"
					model_form = "xero_odoo_integration.xero_invoice_data_form"

		elif self.import_operations == 'import_payment':
			payment_info, payment_status = self.env['xero.api.vts'].get_data_from_xero(
				xero_url, company_id, token, self.import_operations)

			xero_payments = self.get_payments_from_xero(payment_info, payment_status)

		elif self.import_operations == 'import_creditnote':
			credit_info, credit_status = self.env['xero.api.vts'].get_data_from_xero(
				xero_url, company_id, token, self.import_operations)

			creditnote_list = credit_info.get("CreditNotes", [])

			if credit_info:
				queue_ids = self.env['creditnote.data.queue'].create_xero_creditnote_queue_job(self.xero_instance_id, creditnote_list)

				if queue_ids:
					model_action = "xero_odoo_integration.action_xero_creditnote_queue"
					model_form = "xero_odoo_integration.xero_creditnote_queue_form_view"

		elif self.import_operations == 'import_purchase_order':
			po_info,po_status = self.env['xero.api.vts'].get_data_from_xero(
				xero_url, company_id, token, self.import_operations)

			xero_purchase_order = self.get_purchase_order_from_xero(po_info,po_status)

		elif self.import_operations == 'import_prepayment':
			prepayment_info , prepayment_status = self.env['xero.api.vts'].get_data_from_xero(
				xero_url, company_id, token, self.import_operations )

			xero_prepayment = self.get_prepayment_from_xero(prepayment_info, prepayment_status)

		elif self.import_operations == 'import_overpayment':
			overpayment_info, overpayment_status = self.env['xero.api.vts'].get_data_from_xero(
				xero_url, company_id, token, self.import_operations)

			xero_over_payment = self.get_overpayment_from_xero(overpayment_info, overpayment_status)

	def get_invoice_line_ids(self,endpoint,xero_url,invoices_info,invoices_status):
			base_xero_url = xero_url
			company_id = self.xero_instance_id.tenant_id
			token = self.xero_instance_id.access_token

			all_invoices = []
			if invoices_status == 200:
				invoices = invoices_info.get(f'{endpoint}', [])
				for inv in invoices:
					xr_invoice_id = inv.get(f'{endpoint[:-1]}ID')
					invoice_url = f"{base_xero_url}/{endpoint}/{xr_invoice_id}"
					inv_info, inv_status = self.env['xero.api.vts'].xero_get_request(token, company_id, invoice_url)

					if inv_status == 200 and inv_info.get(f'{endpoint}'):
						invoice = inv_info.get(f'{endpoint}')
						all_invoices.extend(invoice)
				xero_invoice_details=[]
				if all_invoices:
					if endpoint == 'Invoices':
						xero_invoice_details = self.get_invoice_from_xero(all_invoices)
					if endpoint == 'CreditNotes':
						xero_invoice_details = self.get_credit_note_from_xero(all_invoices)
				return xero_invoice_details
			else:
				log_id = self.env['xero.log.vts'].sudo().generate_xero_logs(
					xero_operation_name='invoice',
					xero_operation_type='import', instance=self.xero_instance_id.id,
					xero_operation_message=f"Error During {endpoint} Import Process"
				)
				log_line = self.env['xero.log.vts.line'].sudo().generate_xero_process_line(
					xero_operation_name='invoice',
					xero_operation_type='import', instance=self.xero_instance_id.id,
					xero_operation_message=f"Error During {endpoint} Import Process",
					process_response_message=pprint.pformat(invoices_info), log_id=log_id, fault_operation=True)


	def get_contact_from_contact_group(self,xero_url,contact_group_info,contact_group_status):
		company_id = self.xero_instance_id.tenant_id
		token = self.xero_instance_id.access_token

		all_contact_group=[]
		if contact_group_status == 200:
			xero_contact_groups = contact_group_info.get('ContactGroups', {})
			for group in xero_contact_groups:
				contact_group_id = group.get('ContactGroupID')
				url = f"{xero_url}/ContactGroups/{contact_group_id}"
				group_info,group_status = self.env['xero.api.vts'].xero_get_request(token, company_id, url)

				if group_status ==200 and group_info.get('ContactGroups'):
					contact_group = group_info.get('ContactGroups')
					all_contact_group.append(contact_group)
			if all_contact_group:
				xero_contact_groups = self.get_contact_group_from_xero(all_contact_group)
		else:
			log_id = self.env['xero.log.vts'].sudo().generate_xero_logs(
				xero_operation_name='contact_group',
				xero_operation_type='import', instance=self.xero_instance_id.id,
				xero_operation_message="Error During Contact Group Import Process"
			)
			log_line = self.env['xero.log.vts.line'].sudo().generate_xero_process_line(
				xero_operation_name='contact_group',
				xero_operation_type='import', instance=self.xero_instance_id.id,
				xero_operation_message="Error During Contact Group Import Process",
				process_response_message=pprint.pformat(contact_group_info), log_id=log_id, fault_operation=True)


	def _get_data_from_xero_by_id(self,reference_id,type):
		xero_url = self.xero_instance_id.xero_base_url
		company_id = self.xero_instance_id.tenant_id
		token = self.xero_instance_id.access_token

		header = self.env['xero.api.vts'].sudo().get_xero_header(token,company_id)

		endpoint = f"{xero_url}/{type}/{reference_id}"
		response = requests.get(endpoint, headers=header)

		response_status = response.status_code
		response_info = response.json()
		if type == 'Items' and response_status == 200:
			response = self.get_product_from_xero(response_info, response_status)
		if type == 'Contacts' and response_status==200:
			response = self.get_customer_from_xero(response_info,response_status)
		if type == 'Invoices' and response_status==200:
			invoice = response_info.get('Invoices')
			response = self.get_invoice_from_xero(invoice)
		if type == 'Accounts' and response_status == 200:
			response = self.get_account_from_xero(response_info,response_status)
		return response


