from odoo import models


class MailingMailing(models.Model):
    """Light inheritance of mailing.mailing - only adds the action
    that opens the AI Generate wizard for the current mailing.
    No new fields are added on this model to keep things simple.
    """
    _inherit = 'mailing.mailing'

    def action_open_ai_generate_wizard(self):
        """Open the AI Email Generate wizard for this mailing record."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Generate Email Template with AI',
            'res_model': 'ai.email.generate.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_mailing_id': self.id,
                'default_prompt': self.subject or '',
            },
        }
