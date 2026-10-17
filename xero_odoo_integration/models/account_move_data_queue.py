import logging
import pprint
from datetime import timedelta
from odoo import models, fields, api, tools

_logger = logging.getLogger("Xero Invoice Queue")

class MoveDataQueue(models.Model):
    _name = "move.data.queue"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _description = "Xero Invoice Data Queue"
    _order = "id desc"

    name = fields.Char(string="Name")
    instance_id = fields.Many2one("xero.connect", string="Instance")
    state = fields.Selection([("draft", "Draft"),("partially_completed", "Partially Completed"),
        ("completed", "Completed"),("failed", "Failed")], default="draft", tracking=True, compute="_compute_move_queue_line_state_and_count",store=True)

    move_queue_line_ids = fields.One2many("move.data.queue.line","move_queue_id","Invoice Queue Lines")
    queue_process_count = fields.Integer(help="It is used for know, how many time queue is processed.")
    xero_log_id = fields.Many2one("xero.log.vts", string="Logs")

    @api.depends('move_queue_line_ids.state')
    def _compute_move_queue_line_state_and_count(self):
        for queue in self:
            queue_line_ids = queue.move_queue_line_ids
            if all(line.state == 'draft' for line in queue_line_ids):
                queue.state = 'draft'
            elif all(line.state == 'failed' for line in queue_line_ids):
                queue.state = 'failed'
            elif all(line.state == 'completed' for line in queue_line_ids):
                queue.state = 'completed'
            else:
                queue.state = 'partially_completed'

    @api.model_create_multi
    def create(self, vals_list):
        sequence = self.env.ref("xero_odoo_integration.seq_xero_move_queue")
        for vals in vals_list:
            vals["name"] = sequence.next_by_id() or "/"
        return super().create(vals_list)

    def process_xero_invoice_queue(self, instance=False):

        instance = instance or self.instance_id

        if self._context.get('from_cron'):
            queues = self.search([('instance_id', '=', instance.id),('state', '!=', 'completed')], order="id asc")
        else:
            queues = self

        for queue in queues:

            if not self.xero_log_id:
                log_id = self.env['xero.log.vts'].sudo().generate_xero_logs(xero_operation_name='invoice',xero_operation_type='import',
                    instance=instance.id,xero_operation_message='Queue Processing Fetch Invoices/Bills From Xero')
                queue.xero_log_id = log_id.id
            else:
                log_id = queue.xero_log_id

            lines = queue.move_queue_line_ids.filtered(lambda l: l.state in ['draft', 'failed'] and l.number_of_fails < 3)

            commit_counter = 0

            for line in lines:
                commit_counter += 1
                if commit_counter == 10:
                    self._cr.commit()
                    commit_counter = 0

                try:
                    base_xero_url = instance.xero_base_url
                    token = instance.access_token
                    company_id = instance.tenant_id
                    invoice_url = f"{base_xero_url}/Invoices/{line.move_data_id}"
                    inv_info, inv_status = self.env['xero.api.vts'].sudo().xero_get_request(token, company_id, invoice_url)

                    move = False
                    if inv_status == 200 and inv_info.get('Invoices'):
                        invoice = inv_info.get('Invoices')
                        wizard = self.env['xero.operations'].sudo().create({'xero_instance_id': instance.id,'xero_operations': 'import','import_operations': 'import_invoice'})
                        move = wizard.get_invoice_from_xero(invoice, log_id)

                    if move:
                        line.state = 'completed'
                    else:
                        line.number_of_fails += 1

                except Exception as e:
                    line.state = 'failed'
                    line.number_of_fails += 1
                    log_line = self.env['xero.log.vts.line'].sudo().generate_xero_process_line(xero_operation_name='invoice',xero_operation_type='import',
                        instance=instance.id,xero_operation_message="Queue Invoice Processing Error",process_response_message=str(e),
                        log_id=log_id,fault_operation=True)

    def generate_xero_invoice_queue(self, instance):
        return self.create({'instance_id': instance.id})

    def create_xero_invoice_queue_job(self, instance, invoice_list):
        queue_ids = []
        batch_size = 20

        for invoices in tools.split_every(batch_size, invoice_list):
            queue = self.generate_xero_invoice_queue(instance)

            for inv in invoices:
                self.env['move.data.queue.line'].create_xero_move_queue_line(inv, instance, queue)

            queue_ids.append(queue.id)

        return queue_ids

    def process_xero_invoice_queue_using_cron(self):
        instances = self.env['xero.connect'].search([('state','=','connected')])
        for instance in instances:
            self.with_context(from_cron=True).process_xero_invoice_queue(instance)



class MoveDataQueueLine(models.Model):
    _name = "move.data.queue.line"
    _inherit = ["mail.thread", "mail.activity.mixin"]

    name = fields.Char(string="Name")
    move_queue_id = fields.Many2one("move.data.queue",string="Move ID")
    instance_id = fields.Many2one("xero.connect",string="Instance")
    move_data_id = fields.Char(string="Move Data ID")
    state = fields.Selection([("draft", "Draft"),("completed", "Completed"),("failed", "Failed")], default="draft")
    xero_move_type = fields.Char("Xero Move Type")
    move_data_to_process = fields.Text()
    number_of_fails = fields.Integer(copy=False)

    def create_xero_move_queue_line(self, move_dict, instance, queue):
        return self.create({
            "name": move_dict.get("InvoiceNumber"),
            "move_data_id": move_dict.get("InvoiceID"),
            "move_data_to_process": pprint.pformat(move_dict),
            "instance_id": instance.id,
            "xero_move_type":move_dict.get("Type"),
            "move_queue_id": queue.id,
        })
