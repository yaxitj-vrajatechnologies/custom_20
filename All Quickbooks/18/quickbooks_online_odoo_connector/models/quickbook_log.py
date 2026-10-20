# -*- coding: utf-8 -*-
from odoo import models, fields, api
import pprint

class QuickbooksLog(models.Model):

    _inherit = 'quickbooks.log.vts'

    quickbooks_operation_name = fields.Selection(selection_add=[('vendor', 'Vendor'),('product','Product'),('invoice','Invoice'),('bill','Bill'),('billpayment','Bill Payment'),('payment','Payment'),('credit_note','Credit Note'),('bill_credit_note','Bill Credit Note'),('payment_method','Payment Method')], string="Process Name")

class QuickbooksLogLine(models.Model):

    _inherit = 'quickbooks.log.vts.line'

    quickbooks_operation_name = fields.Selection(selection_add=[('vendor', 'Vendor'),('product','Product'),('invoice','Invoice'),('bill','Bill'),('billpayment','Bill Payment'),('payment','Payment'),('credit_note','Credit Note'),('bill_credit_note','Bill Credit Note'),('payment_method','Payment Method')], string="Process Name")
