from odoo import models, fields

class XeroPartnerMap(models.Model):
    _name = 'xero.partner.map'
    _description = 'Xero Customer Mapping'
    _rec_name = "xero_contact_name"

    xero_instance_id = fields.Many2one('xero.connect',string='Xero Instance',)
    xero_contact_id = fields.Char(string='Contact ID',)
    xero_contact_name = fields.Char(string='Customer Name')
    partner_id = fields.Many2one('res.partner',string='Partner')

    xero_response = fields.Text(string='Xero Customer Response')

    def action_customer_mapping(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Xero Customer Mapping',
            'res_model': 'xero.partner.map',
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'current',
        }
