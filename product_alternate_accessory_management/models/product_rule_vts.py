from odoo import models, fields

class AlternateProductRule(models.Model):
    _name = 'product.rule.vts'
    _description = 'Alternative Product Rule'

    name = fields.Char(
        string="Rule Name",
        required=True
    )
    code = fields.Char(required=True)

    rule_type = fields.Selection([
        ('accessory', 'Accessory'),
        ('alternative', 'Alternative'),
        ('both', 'Both'),
    ], default='both', required=True)
