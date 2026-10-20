# -*- coding: utf-8 -*-
from odoo import models
from odoo.exceptions import UserError

class QuickbooksAPIVts(models.AbstractModel):

    _inherit = "quickbooks.api.vts"
    _description = "QuickBooks API"

    def _get_operation_map(self):
        operation_map = super(QuickbooksAPIVts, self)._get_operation_map()
        operation_map.update({'import_vendor': 'Vendor','import_pro_category': 'Item',
                              'import_invoice': 'Invoice','import_vendor_bill':'Bill','import_customer_payment':'Payment',
                              'import_billpayment':'BillPayment'})
        return operation_map


