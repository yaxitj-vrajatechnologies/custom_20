from odoo import models, fields


class PrintNodeRuleAction(models.Model):
    """
    Action for Rules
    """
    _name = 'printnode.rule.action'
    _description = 'PrintNode Rule Action'

    name = fields.Char(string='Name',required=True)
    code = fields.Char(string='Code',required=True)
    model_id = fields.Many2one('ir.model',string='Model',required=True,ondelete='cascade',)
    reports_model_id = fields.Many2one('ir.model',string='Model For Reports',required=True,ondelete='cascade')

