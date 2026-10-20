from odoo import fields, models


class DeliveryCarrier(models.Model):
    _inherit = 'delivery.carrier'


    printer_id = fields.Many2one(comodel_name='printnode.printer.vts',string='Printer',domain=[('status', '=', 'online')],help="Select The Printer For Printing Labels ")
    available_paper = fields.Many2many('printnode.paper.vts',related='printer_id.paper_ids')
    total_copies = fields.Integer(string="Copies",default=1,help="Number of copies to print for this label")
    label_paper_format = fields.Many2one(comodel_name='printnode.paper.vts',string='Paper Format',domain="[('id', 'in', available_paper)]",
            help='Select the label printing paper')
