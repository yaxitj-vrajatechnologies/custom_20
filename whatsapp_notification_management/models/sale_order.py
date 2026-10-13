from odoo import models, fields
from datetime import timedelta


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    notification_sent = fields.Boolean(string="Notification Sent")

    def send_abandoned_cart_whatsapp_notification(self):
        """
        Send WhatsApp reminder for abandoned carts
        """

        hours = self.env['ir.config_parameter'].sudo().get_int(
            'whatsapp_notification_management.abandoned_cart_hours', 24
        )

        abandoned_time = fields.Datetime.now() - timedelta(hours=hours)

        orders = self.env['sale.order'].search([
            ('state', '=', 'draft'),
            ('website_id', '!=', False),
            ('write_date', '<', abandoned_time),
            ('notification_sent', '!=', True)
        ])

        template = self.env['whatsapp.template'].search([
            ('template_name', '=', 'abandoned_cart_reminder')
        ], limit=1)

        if not template:
            return

        for order in orders:

            partner = order.partner_id

            if not partner.phone:
                continue

            checkout_url = f"{order.website_id.domain}/shop/cart/{order.id}"

            composer = self.env['whatsapp.composer'].create({
                'res_model': 'sale.order',
                'res_ids': str([order.id]),
                'wa_template_id': template.id,

                # Template Variables
                'free_text_1': partner.name or '',
                'free_text_2': str(order.amount_total) or '',
                'free_text_3': checkout_url or '',
            })

            composer.action_send_whatsapp_template()

            order.sudo().write({'notification_sent': True})