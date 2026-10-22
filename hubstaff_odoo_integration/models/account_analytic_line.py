from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)


class AccountAnalyticLine(models.Model):
    _inherit = 'account.analytic.line'

    hubstaff_task_entry_id = fields.Char(
        string="Hubstaff Task Entry ID",
        index=True, copy=False, help="Unique identifier of the task entry received from Hubstaff."
    )
    hubstaff_task_id = fields.Char(
        string="Hubstaff Task ID",
        index=True, copy=False, help="Unique identifier of the task in Hubstaff."
    )
    hubstaff_instance_id = fields.Many2one(
        'hubstaff.instance.integration', string="Hubstaff Instance", copy=False,
        help="Hubstaff instance from which this task entry was imported."
    )
    is_billable= fields.Boolean(string="Is Billable", copy=False)
