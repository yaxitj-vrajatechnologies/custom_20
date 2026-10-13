# -*- coding: utf-8 *-*
from odoo import models, fields

class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    task_count = fields.Integer(
        string="Tasks",
        compute="_compute_task_count"
    )
    cleaning_shift_ids = fields.Many2many(
        'cleaning.shift.vts',
        string="Working Shift",
        help="Select working shift of this employee "
    )

    def _compute_task_count(self):
        for emp in self:
            emp.task_count = self.env['project.task'].search_count([
                ('user_ids', 'in', emp.id)
            ])

    def action_view_tasks(self):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id("project.act_project_project_2_project_task_all")
        action['domain'] = [('user_ids', 'in', self.id)]
        return action