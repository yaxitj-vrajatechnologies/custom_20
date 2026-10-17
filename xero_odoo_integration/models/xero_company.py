from odoo import models, fields

class XeroCompanyVTS(models.Model):
    _name = "xero.company.vts"
    _description = "Xero Company"

    name = fields.Char(string="Company Name", required=True)
    tenant_id = fields.Char(string="Tenant ID", required=True)
    xero_response = fields.Text(string="Xero API Response")
