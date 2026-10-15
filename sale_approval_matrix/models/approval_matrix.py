# -*- coding: utf-8 -*-
from odoo import api, fields, models


class ApprovalMatrixLine(models.Model):
    _name = 'approval.matrix.line'
    _description = 'Sales Approval Matrix Line'
    _order = 'sequence, revenue_from, margin_from'
    _rec_name = 'display_name'

    sequence = fields.Integer(default=10)
    display_name = fields.Char(compute='_compute_display_name', store=True)

    revenue_from = fields.Float(
        string='Revenue From', required=True,
        help="Lower bound of the order total for this band (inclusive).")
    revenue_to = fields.Float(
        string='Revenue To', required=True,
        help="Upper bound of the order total for this band (inclusive). "
             "Use a very large number (e.g. 100000000) to represent 'and above'.")
    margin_from = fields.Float(
        string='Margin % From', required=True,
        help="Lower bound of the overall margin percentage for this band (inclusive).")
    margin_to = fields.Float(
        string='Margin % To', required=True,
        help="Upper bound of the overall margin percentage for this band (inclusive). "
             "Use a very large number (e.g. 100000) to represent 'and above'.")
    zone = fields.Selection([
        ('green', 'Green - No Approval Needed'),
        ('yellow', 'Yellow - Approval Required'),
        ('red', 'Red - Approval Required'),
    ], required=True, default='green')

    active = fields.Boolean(default=True)

    @api.depends('revenue_from', 'revenue_to', 'margin_from', 'margin_to', 'zone')
    def _compute_display_name(self):
        for rec in self:
            rec.display_name = "Revenue %s-%s | Margin %s%%-%s%% -> %s" % (
                rec.revenue_from, rec.revenue_to, rec.margin_from, rec.margin_to,
                dict(rec._fields['zone'].selection).get(rec.zone, ''))
