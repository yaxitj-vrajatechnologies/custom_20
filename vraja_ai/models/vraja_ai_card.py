# -*- coding: utf-8 -*-
from odoo import fields, models


class VrajaAICard(models.Model):
    _name = 'vraja.ai.card'
    _description = 'VRAJA AI Dashboard Card'

    vraja_ai_configration_id = fields.Many2one(
        comodel_name='vraja.ai.config',
        string='VRAJA AI Configuration',
    )
    vraja_common_store = fields.Selection(
        selection=[]
    )
    vraja_common_card_name = fields.Char(
        string='VRAJA Card Name',
    )
    vraja_common_card_description = fields.Text(
        string='VRAJA Card Description',
    )
    vraja_common_card_active = fields.Boolean(
        string='Active Card?',
    )

    def action_review_dashboard(self):
        self.ensure_one()

        return {
            'type': 'ir.actions.client',
            'tag': 'vraja_ai_dashboard_template',
            'target': 'current',
            'params': {
                'card_id': self.id,
                'store': self.vraja_common_store,
            }
        }

    def action_log_view(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'AI Logs',
            'res_model': 'vraja.ai.log',
            'view_mode': 'list,form',
            'domain': [],
            'context': {},
        }

    def action_toggle_active(self):
        self.ensure_one()
        self.sudo().write({
            'vraja_common_card_active': not self.vraja_common_card_active
        })
