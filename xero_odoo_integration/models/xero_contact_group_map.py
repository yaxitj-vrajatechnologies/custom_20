from odoo import models, fields


class XeroContactGroup(models.Model):
    _name = 'xero.contact.group.map'
    _description = 'Xero Contact Group Mapping'

    xero_instance_id = fields.Many2one('xero.connect',string='Xero Instance')
    xero_group_id = fields.Char(string='Contact Group ID',)
    xero_group_name = fields.Char(string='Contact Group Name')
    category_id = fields.Many2one('res.partner.category',string='Odoo Category Tag')
    xero_response = fields.Text(string='Contact Group Response')

    def action_contact_group_mapping(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Xero Contact Group Mapping',
            'res_model': 'xero.contact.group.map',
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'current',
        }
