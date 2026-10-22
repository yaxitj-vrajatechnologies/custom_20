from odoo import api, fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    ai_vendor_score_ids = fields.One2many(
        'vendor.intelligence.score',
        'partner_id',
        string='AI Vendor Scores'
    )
    ai_vendor_risk_level = fields.Selection([
        ('reliable', 'Reliable (80-100)'),
        ('average', 'Average (50-79)'),
        ('risky', 'Risky (<50)'),
    ], string="AI Risk Level", readonly=True, compute="_compute_ai_vendor_risk_level", store=True)

    @api.depends('ai_vendor_score_ids.composite_score', 'ai_vendor_score_ids.category_id')
    def _compute_ai_vendor_risk_level(self):
        for partner in self:
            overall_score = partner.ai_vendor_score_ids.filtered(lambda score: not score.category_id)[:1]
            score = overall_score.composite_score if overall_score else 0.0
            if not overall_score:
                partner.ai_vendor_risk_level = False
            elif score >= 80:
                partner.ai_vendor_risk_level = 'reliable'
            elif score >= 50:
                partner.ai_vendor_risk_level = 'average'
            else:
                partner.ai_vendor_risk_level = 'risky'
