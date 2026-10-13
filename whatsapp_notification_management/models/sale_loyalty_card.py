from odoo import models,fields,api,_
from datetime import timedelta
from dateutil.relativedelta import relativedelta
from odoo.exceptions import ValidationError

class LoyaltyCard(models.Model):
    _inherit = 'loyalty.card'

    loyalty_notify_value = fields.Integer(
        string="Notify Before",
        default=1,
        help="Number of units before sending the notification"
    )

    loyalty_notify_unit = fields.Selection([
        ('day', 'Day'),
        ('week', 'Week'),
        ('month', 'Month'),
        ('custom', 'Custom')
    ], string="Unit", default='day')

    notify_custom_date = fields.Datetime(
        string="Notify Before"
    )

    # ------------------------------------------------------------
    @api.constrains(
        'expiration_date',
        'loyalty_notify_value',
        'loyalty_notify_unit',
        'notify_custom_date'
    )
    def _check_coupon_notification_validity(self):
        today = fields.Date.today()

        for rec in self:
            if not rec.expiration_date:
                continue

            remaining_days = (rec.expiration_date - today).days

            if rec.loyalty_notify_unit == 'day':
                notify_days = rec.loyalty_notify_value

            elif rec.loyalty_notify_unit == 'week':
                notify_days = rec.loyalty_notify_value * 7

            elif rec.loyalty_notify_unit == 'month':
                notify_days = rec.loyalty_notify_value * 30

            elif rec.loyalty_notify_unit == 'custom' and rec.notify_custom_date:
                custom_date = rec.notify_custom_date.date()

                if custom_date > rec.expiration_date:
                    raise ValidationError(_(
                        "Custom notification date cannot be after the expiration date."
                    ))

                if custom_date < today:
                    raise ValidationError(_(
                        "Custom notification date cannot be in the past."
                    ))

                notify_days = (rec.expiration_date - custom_date).days
            else:
                notify_days = rec.loyalty_notify_value


            if notify_days > remaining_days:
                raise ValidationError(_(
                    "Invalid notification configuration.\n\n"
                    "Coupon expires in %s days.\n"
                    "You are trying to notify %s days before expiration.\n\n"
                    "Please reduce the notification period."
                ) % (remaining_days, notify_days))
        # ------------------------------------------------------------

    def send_discount_coupon_notification(self):
        """Send coupon notification to customers who received coupons."""

        today = fields.Date.today()

        coupons = self.env['loyalty.card'].search([
            ('partner_id', '!=', False),
            ('expiration_date', '>=', today)
        ])

        template = self.env['whatsapp.template'].search([
            ('template_name', '=', 'discount_coupon_offers')
        ], limit=1)

        if not template:
            return

        for coupon in coupons:

            partner = coupon.partner_id
            program = coupon.program_id

            if not partner.phone:
                continue

            reminder_date = False

            if coupon.loyalty_notify_unit == 'day':
                reminder_date = coupon.expiration_date - timedelta(days=coupon.loyalty_notify_value)

            elif coupon.loyalty_notify_unit == 'week':
                reminder_date = coupon.expiration_date - timedelta(weeks=coupon.loyalty_notify_value)

            elif coupon.loyalty_notify_unit == 'month':
                reminder_date = coupon.expiration_date - relativedelta(months=coupon.loyalty_notify_value)

            elif coupon.loyalty_notify_unit == 'custom' and coupon.notify_custom_date:
                reminder_date = coupon.notify_custom_date.date()

            if reminder_date != today:
                continue

            discount_value = ''
            if program.reward_ids:
                reward = program.reward_ids[0]
                if reward.discount:
                    discount_value = reward.discount

            composer = self.env['whatsapp.composer'].create({
                'res_model': 'res.partner',
                'res_ids': str([partner.id]),
                'wa_template_id': template.id,

                # Template Variables
                'free_text_1': partner.name or '',
                'free_text_2': coupon.code or '',
                'free_text_3': str(discount_value) or '',
                'free_text_4': coupon.expiration_date.strftime('%d-%m-%Y') if coupon.expiration_date else '',
                'free_text_5': program.website_id.name if program.website_id else '',
            })

            composer.action_send_whatsapp_template()
