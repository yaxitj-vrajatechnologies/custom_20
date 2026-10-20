
from odoo import models, fields


class PrintNodeComputer(models.Model):
    _name = 'printnode.computer.vts'
    _description = 'PrintNode Computer'

    name = fields.Char(string='Name',size=64,required=True)
    printnode_computer_id=fields.Char(string="PrintNode Computer ID")
    printnode_instance_id = fields.Many2one('printnode.connect', string="PrintNode Instance", required=True, ondelete='cascade',help="PrintNode connection this printer belongs to.")
    state = fields.Char(string='Status',size=64)

