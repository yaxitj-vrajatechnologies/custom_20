# -*- coding: utf-8 -*-
import requests
import logging
from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)

class FruugoCategory(models.Model):
    _name = 'fruugo.category'
    _description = 'Fruugo Category'
    _rec_name = 'full_path'
    _order = 'full_path asc'

    name = fields.Char(string='Category Name', help="Leaf-level name")
    full_path = fields.Char(string='Full Path', required=True, index=True)
    active = fields.Boolean(default=True)

    parent_id = fields.Many2one(
        'fruugo.category',
        string='Parent Category',
        ondelete='set null',
        index=True,
    )
    child_ids = fields.One2many(
        'fruugo.category',
        'parent_id',
        string='Sub-categories',
    )
    product_count = fields.Integer(
        string='Products',
        compute='_compute_product_count',
        store=False,
    )

    @api.constrains('full_path')
    def _check_full_path_unique(self):
        for rec in self:
            if rec.full_path:
                domain = [('full_path', '=', rec.full_path), ('id', '!=', rec.id)]
                if self.search_count(domain) > 0:
                    raise ValidationError(_('Category path must be unique.'))

    @api.depends()
    def _compute_product_count(self):
        """Count product.templates linked to each taxonomy node."""
        for rec in self:
            rec.product_count = self.env['product.template'].search_count(
                [('fruugo_category_id', '=', rec.id)]
            )

    def action_view_products(self):
        self.ensure_one()
        return {
            "name": "Products",
            "type": "ir.actions.act_window",
            "res_model": "product.template",
            "view_mode": "list,form",
            "domain": [("fruugo_category_id", "=", self.id)],
        }


