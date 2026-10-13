# -*- coding: utf-8 *-*
from odoo import models, fields


class ProjectTask(models.Model):
    _inherit = 'project.task'

    booking_id = fields.Many2one(
        'booking.request',
        string="Booking Reference",
        help="Related service booking reference for this task."
    )
