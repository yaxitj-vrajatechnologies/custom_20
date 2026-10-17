import logging
import pprint
from odoo import models, fields, api, tools

_logger = logging.getLogger("Xero Credit Note Queue")


class CreditNoteDataQueue(models.Model):
    _name = "creditnote.data.queue"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _description = "Xero Credit Note Data Queue"
    _order = "id desc"

    name = fields.Char(string="Name")
    instance_id = fields.Many2one("xero.connect", string="Instance")

    state = fields.Selection([("draft", "Draft"),("partially_completed", "Partially Completed"),
        ("completed", "Completed"),("failed", "Failed")
    ], default="draft", tracking=True, compute="_compute_queue_state", store=True)

    creditnote_queue_line_ids = fields.One2many("creditnote.data.queue.line",
        "queue_id","Credit Note Queue Lines")

    queue_process_count = fields.Integer()
    xero_log_id = fields.Many2one("xero.log.vts", string="Logs")

    @api.depends('creditnote_queue_line_ids.state')
    def _compute_queue_state(self):
        for queue in self:
            lines = queue.creditnote_queue_line_ids
            if all(l.state == 'draft' for l in lines):
                queue.state = 'draft'
            elif all(l.state == 'failed' for l in lines):
                queue.state = 'failed'
            elif all(l.state == 'completed' for l in lines):
                queue.state = 'completed'
            else:
                queue.state = 'partially_completed'

    @api.model_create_multi
    def create(self, vals_list):
        sequence = self.env.ref("xero_odoo_integration.seq_xero_creditnote_queue")
        for vals in vals_list:
            vals["name"] = sequence.next_by_id() or "/"
        return super().create(vals_list)

    def process_xero_creditnote_queue(self, instance=False):

        instance = instance or self.instance_id

        if self._context.get('from_cron'):
            queues = self.search([('instance_id', '=', instance.id),('state', '!=', 'completed')], order="id asc")
        else:
            queues = self

        for queue in queues:

            if not queue.xero_log_id:
                log_id = self.env['xero.log.vts'].sudo().generate_xero_logs(xero_operation_name='credit_note',
                    xero_operation_type='import',instance=instance.id,xero_operation_message='Queue Processing Fetch Credit Note From Xero')
                queue.xero_log_id = log_id.id
            else:
                log_id = queue.xero_log_id

            lines = queue.creditnote_queue_line_ids.filtered(lambda l: l.state in ['draft', 'failed'] and l.number_of_fails < 3)

            commit_counter = 0

            for line in lines:
                commit_counter += 1
                if commit_counter == 10:
                    self._cr.commit()
                    commit_counter = 0

                try:
                    base_url = instance.xero_base_url
                    token = instance.access_token
                    tenant_id = instance.tenant_id

                    url = f"{base_url}/CreditNotes/{line.creditnote_data_id}"

                    data, status = self.env['xero.api.vts'].sudo().xero_get_request(token, tenant_id, url)

                    credit_move = False
                    if status == 200 and data.get('CreditNotes'):
                        wizard = self.env['xero.operations'].sudo().create({'xero_instance_id': instance.id,
                            'xero_operations': 'import','import_operations': 'import_creditnote'})
                        credit_move = wizard.get_credit_note_from_xero(data.get('CreditNotes'), log_id)
                    if credit_move:
                        line.state = 'completed'
                    else:
                        line.number_of_fails += 1

                except Exception as e:
                    line.state = 'failed'
                    line.number_of_fails += 1
                    self.env['xero.log.vts.line'].sudo().generate_xero_process_line(xero_operation_name='creditnote',
                        xero_operation_type='import',instance=instance.id,xero_operation_message="Queue Credit Note Processing Error",
                        process_response_message=str(e),log_id=log_id,fault_operation=True)

    def generate_xero_creditnote_queue(self, instance):
        return self.create({'instance_id': instance.id})

    def create_xero_creditnote_queue_job(self, instance, creditnote_list):
        """
        Creates queue records in batches and adds credit note lines
        """
        queue_ids = []
        batch_size = 20

        for creditnotes in tools.split_every(batch_size, creditnote_list):
            queue = self.generate_xero_creditnote_queue(instance)

            for cn in creditnotes:
                self.env['creditnote.data.queue.line'].create_xero_creditnote_queue_line(cn, instance, queue)

            queue_ids.append(queue.id)

        return queue_ids

    def process_xero_creditnote_queue_using_cron(self):
        instances = self.env['xero.connect'].search([('state', '=', 'connected')])
        for instance in instances:
            self.with_context(from_cron=True).process_xero_creditnote_queue(instance)


class CreditNoteDataQueueLine(models.Model):
    _name = "creditnote.data.queue.line"
    _inherit = ["mail.thread", "mail.activity.mixin"]

    name = fields.Char("Name")
    queue_id = fields.Many2one("creditnote.data.queue", string="Queue")
    instance_id = fields.Many2one("xero.connect", string="Instance")
    creditnote_data_id = fields.Char("Credit Note ID")
    state = fields.Selection([("draft", "Draft"),("completed", "Completed"),("failed", "Failed")], default="draft")
    xero_move_type = fields.Char("Xero Type")
    creditnote_data_to_process = fields.Text()
    number_of_fails = fields.Integer(copy=False)

    def create_xero_creditnote_queue_line(self, data, instance, queue):
        return self.create({
            "name": data.get("CreditNoteNumber"),
            "creditnote_data_id": data.get("CreditNoteID"),
            "creditnote_data_to_process": pprint.pformat(data),
            "instance_id": instance.id,
            "xero_move_type": data.get("Type"),
            "queue_id": queue.id,
        })