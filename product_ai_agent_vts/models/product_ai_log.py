from odoo import models, fields, api


class ProductAILog(models.Model):
    _inherit = 'vraja.ai.log'

    vraja_common_log_store = fields.Selection(
        selection_add=[('product_alt_acc', 'Product Alternate & Accessory')]
    )
    product_ai_suggestion_type = fields.Selection([
        ('both', 'Both'),
        ('alternatives', 'Alternatives Only'),
        ('accessories', 'Accessories Only'),
    ], string='Suggestion Type', readonly=True,
        help="The type of AI suggestions generated in this run — whether alternatives, accessories, or both were requested.")

    product_ai_confidence = fields.Selection([
        ('all', 'All'),
        ('medium', 'High & Medium'),
        ('high', 'High Only'),
    ], string='Confidence Level', readonly=True,help="The minimum confidence level configured for this run. Higher confidence means stricter matching — fewer but more accurate suggestions.")

    product_ai_total_products = fields.Integer(string='Products Analysed', readonly=True)
    product_ai_total_alt = fields.Integer(string='Alternatives Applied', readonly=True)
    product_ai_total_acc = fields.Integer(string='Accessories Applied', readonly=True)
    product_ai_token_used = fields.Integer(string='Total Tokens Used', default=0,help="Total number of tokens consumed by the OpenAI API during this AI analysis run.")
    product_ai_log_message = fields.Text(string='Log Message')


class ProductAILogLine(models.Model):
    _inherit = 'vraja.ai.log.line'

    product_ai_product_id = fields.Many2one('product.template', string='Product', readonly=True)
    product_ai_product_name = fields.Char(string='Product Name', readonly=True)
    product_ai_alt_applied = fields.Integer(string='Alternatives Applied', readonly=True)
    product_ai_acc_applied = fields.Integer(string='Accessories Applied', readonly=True)
    product_ai_alt_names = fields.Text(string='Alternatives', readonly=True)
    product_ai_acc_names = fields.Text(string='Accessories', readonly=True)
    product_ai_status = fields.Selection([
        ('success', 'Success'),
        ('skipped', 'Skipped'),
        ('failed', 'Failed'),
    ], string='Status', default='success', readonly=True)
