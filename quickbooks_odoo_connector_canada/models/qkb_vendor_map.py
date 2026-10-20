from odoo import models, fields


class QuickbooksVendor(models.Model):

    _name = 'qbo.vendor.ca.map.vts'
    _description = "Quickbooks vendor"

    quickbook_instance_id = fields.Many2one('quickbooks.connect', string="Quickbook Instance ID")
    quickbook_vendor_id = fields.Char(string="Vendor ID")
    quickbook_vendor_name = fields.Char(string="Vendor Name")
    vendor_id = fields.Many2one('res.partner', string="Vendor")
    company_id = fields.Many2one('res.company', string="Company", default=lambda self: self.env.user.company_id)
    qbo_response = fields.Text(string="JSON Body")

    def vendor_mapping_view(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Quickbooks Vendor',
            'res_model': 'qbo.vendor.ca.map.vts',
            'view_mode': 'form',
            'view_id': self.env.ref('quickbooks_odoo_connector_canada.view_qkb_vendor_ca_form').id,
            'res_id': self.id,
            'target': 'current'}
