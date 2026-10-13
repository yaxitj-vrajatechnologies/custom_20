from odoo import api, models


class HrTimesheetStopTimerConfirmationWizard(models.Model):
    _inherit = 'hr.timesheet.stop.timer.confirmation.wizard'

    @api.model
    def default_get(self, fields_list):
        res = {}
        timesheet = self.env['account.analytic.line'].browse(self.env.context.get('default_timesheet_id'))

        if timesheet:
            res['timesheet_id'] = timesheet.id
            res['timesheet_name'] = (timesheet.name if timesheet.name != "/" else "")

            if timesheet.user_timer_id:
                minutes_spent = timesheet.user_timer_id._get_minutes_spent()

                res['time_spent'] = (minutes_spent / 60.0) + timesheet.unit_amount
            else:
                res['time_spent'] = timesheet.unit_amount

        return res