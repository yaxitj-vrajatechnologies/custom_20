# -*- coding: utf-8 *-*

from odoo import fields, models


class Company(models.Model):
    _inherit = 'res.company'


    printnode_auto_print = fields.Boolean(string='Enable Direct Printing', default=False, help="Automatically prints the document via PrintNode")
    printnode_printer_id = fields.Many2one('printnode.printer.vts', string='Set Default Printer', domain=[('status', '=', 'online')], help="Select a default printer for direct printing")
    label_printer_id = fields.Many2one('printnode.printer.vts',string='Shipping Label Printer', domain=[('status', '=', 'online')], help="Select a default shipping label printer for direct printing")
    report_id = fields.Many2one('ir.actions.report',string='Package Report to Print')
    auto_print_shipping_label= fields.Boolean(string='Print Shipping Labels',default=False, help="Automatically prints the shipping label via PrintNode")
    available_label_paper_ids = fields.Many2many('printnode.paper.vts', string='Papers', related='label_printer_id.paper_ids')
    label_paper_id = fields.Many2one('printnode.paper.vts', string="Select label Papers",
                                     domain="[('id', 'in', available_label_paper_ids)]")
    available_paper_id = fields.Many2many('printnode.paper.vts', string='Papers', related='printnode_printer_id.paper_ids')
    paper_id = fields.Many2one('printnode.paper.vts', string="Papers Format",
                                     domain="[('id', 'in', available_paper_id)]")


    product_labels_format = fields.Selection(
        [
            ('dymo', 'Dymo'),
            ('2x7xprice', '2 x 7 with price'),
            ('4x7xprice', '4 x 7 with price'),
            ('4x12', '4 x 12'),
            ('4x12xprice', '4 x 12 with price'),
            ('zpl', 'ZPL Labels'),
            ('zplxprice', 'ZPL Labels with price')
        ],
        string="Product Labels Format",
        default="2x7xprice",
        help='Set label printing format')
    
