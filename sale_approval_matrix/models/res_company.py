# -*- coding: utf-8 -*-
from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    approval_matrix_enabled = fields.Boolean(
        string='Enable Sales Approval Matrix',
        default=True,
        help="When enabled, quotations for this company are checked against the "
             "Revenue/Margin Approval Matrix, showing warning banners and requiring "
             "manager approval before Send/Confirm on Yellow or Red quotations. "
             "When disabled, quotations behave as if this module were not installed.")
