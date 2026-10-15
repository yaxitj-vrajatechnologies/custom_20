from odoo import fields, models,api
import json


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    main_rule_ids = fields.Many2many(
        'product.rule.vts',
        'config_setting_main_rel',
        string="Alternative Rules",
        domain=[('code', 'in', ['brand', 'category'])]
    )

    other_rule_ids = fields.Many2many(
        'product.rule.vts',
        'config_setting_other_rel',
        string="Other Rules",
        domain=[('code', 'not in', ['brand', 'category'])]
    )

    min_price_range = fields.Float(
        string="Min Price Range",
        default=10.0
    )

    max_price_range = fields.Float(
        string="Max Price Range",
        default=10.0
    )

    show_price_range = fields.Boolean(compute="_compute_show_price_range")

    @api.depends('other_rule_ids')
    def _compute_show_price_range(self):
        for rec in self:
            rec.show_price_range = 'price' in rec.other_rule_ids.mapped('code')

    def set_values(self):
        """Save the values to ir.config_parameter"""
        super().set_values()
        ICP = self.env['ir.config_parameter'].sudo()

        ICP.set_str('product_alternate_accessory_management.main_rule_ids', json.dumps(self.main_rule_ids.ids))
        ICP.set_str('product_alternate_accessory_management.other_rule_ids', json.dumps(self.other_rule_ids.ids))
        ICP.set_float('product_alternate_accessory_management.min_price_range', self.min_price_range)
        ICP.set_float('product_alternate_accessory_management.max_price_range', self.max_price_range)

    def get_values(self):
        res = super().get_values()
        ICP = self.env['ir.config_parameter'].sudo()

        main_param = ICP.get_str('product_alternate_accessory_management.main_rule_ids') or '[]'
        other_param = ICP.get_str('product_alternate_accessory_management.other_rule_ids') or '[]'

        res.update(
            main_rule_ids=[(6, 0, json.loads(main_param))],
            other_rule_ids=[(6, 0, json.loads(other_param))],
            min_price_range=ICP.get_float('product_alternate_accessory_management.min_price_range') or 10.0,
            max_price_range=ICP.get_float('product_alternate_accessory_management.max_price_range') or 10.0,
        )

        return res