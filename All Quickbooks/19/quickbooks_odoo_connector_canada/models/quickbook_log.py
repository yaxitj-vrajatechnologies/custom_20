# -*- coding: utf-8 -*-
from odoo import models, fields


class QuickbooksLog(models.Model):

    _inherit = 'quickbooks.log.vts'

    quickbooks_operation_name = fields.Selection(selection_add=[('vendor', 'Vendor'),('product','Product'),('bill','Bills'),
                                                ('product_category','Product Category'),('invoice','Invoice'),('customer_payment', 'Payment'),
                                                ('billpayment','Bill Payment'),('payment_term','Payment Term'),('chart_of_account','Chart Of Accounts'),
                                                ('credit_note','Credit Note'),('bill_credit_note','Bill Credit Note')], string="Process Name")

class QuickbooksLogLine(models.Model):

    _inherit = 'quickbooks.log.vts.line'

    quickbooks_operation_name = fields.Selection(selection_add=[('vendor', 'Vendor'),('product','Product'),('bill','Bills'),
                                                ('product_category','Product Category'),('invoice','Invoice'),('customer_payment', 'Payment'),
                                                ('billpayment','Bill Payment'),('payment_term','Payment Term'),('chart_of_account','Accounts'),
                                                ('credit_note', 'Credit Note'),('bill_credit_note', 'Bill Credit Note')], string="Process Name")
