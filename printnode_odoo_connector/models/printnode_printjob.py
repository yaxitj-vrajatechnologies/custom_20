from datetime import datetime, timedelta
from odoo import models, fields


class PrintNodePrintJob(models.Model):
    """ PrintNode PrintJob entity
    """

    _name = 'printnode.printjob.vts'
    _rec_name='description'

    description = fields.Char(string="Label Name", help="Name of the document to print")
    printer_id = fields.Many2one('printnode.printer.vts', string='Printer', domain=[('status', '=', 'online')],help="Selected Printer is used to print the Attachment")
    printjob_id = fields.Char(string="Print ID")
    attachment_id = fields.Many2one('ir.attachment', string='Attachment')
    printnode_instance_id = fields.Many2one('printnode.connect', string='PrintNode Instance',ondelete='cascade',help='Select Instance Id')
    print_status = fields.Selection([('done','Done'),('failed','Failed')],default='failed',string="Status")

    def create_printjob(self, data, attachment_id, printer_id):
        payload = {
            'description': data.get('title'),
            'printer_id': printer_id.id if printer_id else False,
            'attachment_id': attachment_id.id if attachment_id else False,
        }

        printjob = self.sudo().create(payload)
        print("CREATED:", printjob.id, printjob.read())
        return printjob

    def unlink_printjobs_request(self):
        """
        Remove printjobs older than `older_than` days ago
        """
        days_ago = datetime.now() - timedelta(days=15)

        printjobs = self.search([('create_date', '<', days_ago)])

        printjobs.attachment_id.unlink()
        printjobs.unlink()
