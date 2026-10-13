# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import ValidationError


class CleaningHolidayVTS(models.Model):
    _name = 'cleaning.holiday.vts'
    _description = 'Cleaning Holiday'
    _order = 'date_from asc'

    name = fields.Char(
        string='Holiday Name',
        required=True,
        help="e.g. Festival Name, Weekly Off Day"
    )
    holiday_type = fields.Selection([
        ('weekly_off', 'Weekly Off'),
        ('exception',  'Exception Holiday'),
    ], string='Holiday Type', required=True, default='exception', help="Select the holiday type based on your requirement, such as Festival or Week Off.")

    day_of_week = fields.Selection([
        ('0', 'Monday'),
        ('1', 'Tuesday'),
        ('2', 'Wednesday'),
        ('3', 'Thursday'),
        ('4', 'Friday'),
        ('5', 'Saturday'),
        ('6', 'Sunday'),
    ], string='Week Off Day')

    date_from = fields.Date(string='From Date', help="Start date of the exception holidays", copy=False)
    date_to   = fields.Date(string='To Date',help="End date of the exception holidays", copy=False)

    is_active = fields.Boolean(string='Active', default=True,help='Enable this option to keep the holiday active')
    note = fields.Text(string='Description', copy=False)

    @api.constrains('holiday_type', 'day_of_week', 'date_from', 'date_to')
    def _check_required_fields(self):
        for rec in self:
            if rec.holiday_type == 'weekly_off' and not rec.day_of_week:
                raise ValidationError("Please select a Week Off Day.")

            if rec.holiday_type == 'exception':
                if not rec.date_from or not rec.date_to:
                    raise ValidationError("Please set From Date and To Date for Exception Holiday.")
                if rec.date_to < rec.date_from:
                    raise ValidationError("To Date must be greater than or equal to From Date.")

    @api.constrains('holiday_type', 'day_of_week')
    def _check_weekly_off(self):
        for rec in self:
            if rec.holiday_type == 'weekly_off' and rec.day_of_week:
                duplicate = self.search([
                    ('holiday_type', '=', 'weekly_off'),
                    ('day_of_week',  '=', rec.day_of_week),
                    ('id', '!=', rec.id)
                ])
                if duplicate:
                    day_labels = {
                        '0': 'Monday',    '1': 'Tuesday', '2': 'Wednesday',
                        '3': 'Thursday',  '4': 'Friday',  '5': 'Saturday',
                        '6': 'Sunday'
                    }
                    raise ValidationError(
                        f"Weekly off for {day_labels.get(rec.day_of_week)} is already configured."
                    )