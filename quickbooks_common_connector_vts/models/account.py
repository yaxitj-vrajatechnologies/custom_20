# -*- coding: utf-8 *-*
from odoo import models, fields, api

class Account(models.Model):

	_inherit = "account.account"

	qck_instance_id = fields.Many2one('quickbooks.connect',string="Quickbook Instance",copy=False)
	quickbooks_id = fields.Char(string="Quickbook ID",copy=False)
	qk_classification = fields.Char(string="Classification")
	qk_accountsubType = fields.Char(string="Account SubType")

class PaymentTerms(models.Model):

	_inherit = 'account.payment.term'

	qck_instance_id = fields.Many2one('quickbooks.connect',string="Quickbook Instance",copy=False)
	qck_payment_terms_ID = fields.Char(string="Quickbook Terms ID",copy=False)

class Taxes(models.Model):

	_inherit = 'account.tax'

	qck_instance_id = fields.Many2one('quickbooks.connect',string="Quickbook Instance",copy=False)
	qck_taxes_ID = fields.Char(string="Quickbook Taxes ID",copy=False)

class AccountMove(models.Model):

    _inherit = 'account.move'

    is_error_mail_send = fields.Boolean(string="Is Error Mail Send", default=False, copy=False)

class AccountPayment(models.Model):

    _inherit = 'account.payment'

    is_error_mail_send = fields.Boolean(string="Is Error Mail Send", default=False, copy=False)