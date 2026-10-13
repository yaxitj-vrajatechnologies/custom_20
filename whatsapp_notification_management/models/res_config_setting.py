from odoo import models, fields
import json


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    abandoned_cart_hours = fields.Integer(
        string="Auto Reminder After (Hours)",
        config_parameter="whatsapp_notification_management.abandoned_cart_hours",
        help="Send WhatsApp reminder if cart is abandoned after X hours."
    )

    user_ids = fields.Many2many(
        'res.users',
        string="Account Managers"
    )

    def set_values(self):
        super().set_values()
        self.env['ir.config_parameter'].sudo().set_str(
            'whatsapp_notification_management.user_ids',
            json.dumps(self.user_ids.ids)
        )

    def get_values(self):
        res = super().get_values()

        param = self.env['ir.config_parameter'].sudo().get_str(
            'whatsapp_notification_management.user_ids', '[]'
        )

        user_ids = json.loads(param)
        res.update(
            user_ids=[(6, 0, user_ids)]
        )

        return res
