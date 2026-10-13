# -*- coding: utf-8 *-*
from odoo import models, fields

class CleaningTeam(models.Model):
    _name = 'cleaning.team.vts'
    _description = 'Cleaning Team'

    name = fields.Char(string="Team Name", required=True)

    employee_ids = fields.Many2many(
        'hr.employee',
        string="Team Members",
        help="Select employees who are part of the team.",
        copy= False

    )

    cleaning_shift_id = fields.Many2one(
        'cleaning.shift.vts',
        string="Shift",
        help="Select the shift for the cleaning service.",
        copy=False
    )

    note = fields.Text(string="Notes", help="Additional notes or remarks.")

    booked_request_ids = fields.One2many('booking.request','cleaning_team_id', string="Booked Request")