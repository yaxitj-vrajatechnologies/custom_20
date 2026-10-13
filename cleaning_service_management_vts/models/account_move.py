# -*- coding: utf-8 *-*
from odoo import models, fields

class AccountMove(models.Model):
    _inherit = 'account.move'

    booking_id = fields.Many2one(
        'booking.request',
        string="Booking",
        ondelete='cascade',
    )