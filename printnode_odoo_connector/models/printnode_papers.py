# -*- coding: utf-8 *-*
from odoo import models, fields


class PrintNodePapers(models.Model):
    _name = 'printnode.paper.vts'

    name = fields.Char('Name',size=64,required=True,help="Define the name of the paper")
    width = fields.Integer('Width')
    height = fields.Integer('Height')

