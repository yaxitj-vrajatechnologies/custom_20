# -*- coding: utf-8 -*-
from odoo import models, fields, api


class AvailabilityChecker(models.Model):
    _name = 'empl.availability.vts'
    _description = 'Employee & Team Availability Checker'
    _order = 'id desc'

    name = fields.Char(default='Check Availability')
    check_date = fields.Date(
        string='Date',
        default=fields.Date.today,
        help="Select the date for which you want to check employee and team availability "
    )

    cleaning_shift_id = fields.Many2one(
        'cleaning.shift.vts',
        string='Shift',
        help="Select the cleaning shift for which availability need to be checked."

    )

    shift_slot_id = fields.Many2one(
        'cleaning.shift.slot.vts',
        string='Time Slot',
        domain="[('shift_id', '=', cleaning_shift_id)]",
        help="Select the time slot for the chosen shift to check availability."
    )

    available_employee_ids = fields.Many2many(
        'hr.employee',
        'availability_checker_employee_rel',
        'checker_id',
        'employee_id',
        string='Available Employees',
        readonly=True
    )

    available_team_ids = fields.Many2many(
        'cleaning.team.vts',
        'availability_checker_team_rel',
        'checker_id',
        'team_id',
        string='Available Teams',
        readonly=True,
    )

    result_summary = fields.Text(
        string='Summary',
        readonly=True
    )

    @api.onchange('cleaning_shift_id')
    def _onchange_cleaning_shift_id(self):
        self.shift_slot_id = False

    def _is_holiday(self, date):
        day_of_week = str(date.weekday())  if date else False

        weekly_off = self.env['cleaning.holiday.vts'].search([
            ('is_active', '=', True),
            ('holiday_type', '=', 'weekly_off'),
            ('day_of_week', '=', day_of_week),
        ], limit=1)

        if weekly_off:
            return True

        exception_holiday = self.env['cleaning.holiday.vts'].search([
            ('is_active', '=', True),
            ('holiday_type', '=', 'exception'),
            ('date_from', '<=', date),
            ('date_to', '>=', date),
        ], limit=1)

        return bool(exception_holiday)

    def _get_booked_employee_ids(self, date, shift_id, slot_id):
        domain = [
            ('preferred_date', '=', date),
            ('cleaning_shift_id', '=', shift_id),
            ('state', '=', 'approved'),
        ]
        if slot_id:
            domain.append(('shift_slot_id', '=', slot_id))

        bookings = self.env['booking.request'].search(domain)
        booked_emp_ids = set()
        for b in bookings:
            if b.is_individual and b.individual_id:
                booked_emp_ids.add(b.individual_id.id)
            elif b.cleaning_team_id:
                booked_emp_ids.update(b.cleaning_team_id.employee_ids.ids)
        return booked_emp_ids

    def action_check_cleaner_availability(self):
        self.ensure_one()

        if self._is_holiday(self.check_date):
            self.available_employee_ids = [(5,)]
            self.available_team_ids = [(5,)]
            self.result_summary = (
                "The selected date is a Holiday / Weekly Off. "
                "No employees or teams are available."
            )
            return

        booked_ids = self._get_booked_employee_ids(
            self.check_date,
            self.cleaning_shift_id.id,
            self.shift_slot_id.id if self.shift_slot_id else False,
        )

        all_shift_employees = self.env['hr.employee'].search([
            ('cleaning_shift_ids', 'in', self.cleaning_shift_id.id),
            ('active', '=', True),
        ])
        available_empl = all_shift_employees.filtered(lambda e: e.id not in booked_ids)

        shift_teams = self.env['cleaning.team.vts'].search([
            ('cleaning_shift_id', '=', self.cleaning_shift_id.id),
        ])
        available_teams = shift_teams.filtered(
            lambda t: t.employee_ids and not (set(t.employee_ids.ids) & booked_ids)
        )

        self.available_employee_ids = [(6, 0, available_empl.ids)]
        self.available_team_ids = [(6, 0, available_teams.ids)]

        # slot_label = f" | Slot: {self.shift_slot_id.name}" if self.shift_slot_id else ""
        lines = [ f"Available Employees : {len(available_empl)} |  Available Teams : {len(available_teams)} "]
        if not available_empl and not available_teams:
            lines.append("No employees or teams are free for the selected slot.")
        self.result_summary = "\n".join(lines)
