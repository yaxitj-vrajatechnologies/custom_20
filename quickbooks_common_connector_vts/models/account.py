# -*- coding: utf-8 *-*
from odoo import models, fields, api

class Account(models.Model):

	_inherit = "account.account"

	qk_classification = fields.Char(string="Classification")
	qk_accountsubType = fields.Char(string="Account SubType")


class AccountMove(models.Model):

    _inherit = 'account.move'

    is_error_mail_send = fields.Boolean(string="Is Error Mail Send", default=False, copy=False)

class AccountPayment(models.Model):

    _inherit = 'account.payment'

    is_error_mail_send = fields.Boolean(string="Is Error Mail Send", default=False, copy=False)
