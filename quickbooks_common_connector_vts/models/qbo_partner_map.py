# -*- coding: utf-8 *-*
from odoo import models, fields, api


class QuickbooksParnterMap(models.Model):

    _name = 'qbo.partner.map.vts'
    _description = "Quickbooks Partner Map"
    _rec_name = "partner_id"

    quickbook_instance_id = fields.Many2one('quickbooks.connect',string="Quickbook Instance ID")
    quickbook_id = fields.Char(string="Quickbook ID")
    quick_name = fields.Char(string="Customers Name")
    partner_id = fields.Many2one('res.partner',string="Odoo Customer")
    company_id = fields.Many2one('res.company',string="Company",default=lambda self: self.env.user.company_id)
    qbo_response = fields.Text(string="JSON Body")

    def partner_mapping_view(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Quickbooks Partner Map',
            'res_model': 'qbo.partner.map.vts',
            'view_mode': 'form',
            'view_id': self.env.ref('quickbooks_common_connector_vts.view_qbo_partner_map_form').id,
            'res_id': self.id,
            'target': 'current',
        }
