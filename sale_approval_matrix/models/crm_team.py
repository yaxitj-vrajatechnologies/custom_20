# -*- coding: utf-8 -*-
from odoo import fields, models


class CrmTeam(models.Model):
    _inherit = 'crm.team'

    approval_manager_ids = fields.Many2many(
        comodel_name='res.users',
        string='Approval Managers',
        domain=lambda self: [
            ('all_group_ids', 'in', [self.env.ref('sales_team.group_sale_manager').id])
        ],
        help="Users who should be notified (and are expected to review) when a "
             "salesperson on this team requests manager approval on a quotation. "
             "Only users with Sales Manager access can be selected here. If left "
             "empty, all users in the Sales Manager group are notified instead, "
             "as a safe fallback.")
