from odoo import models, fields, api

class XeroInstance(models.TransientModel):
    _name = 'xero.instance.wizard'
    _description = 'Xero Instance Wizard'

    xero_instance_id = fields.Many2one('xero.connect', string='Xero Instance', required=True)

    def xero_export_operation(self):
        active_ids = self.env.context.get('active_ids')
        active_model = self.env.context.get('active_model')
        record = self.env[active_model].browse(active_ids)

        company = (record.company_id if 'company_id' in record._fields and record.company_id else self.env.company)

        xero_instance = self.env['xero.connect'].sudo().search([('id', '=', self.xero_instance_id.id), ('state', '=', 'connected'), ('company_id', '=', company.id), ], limit=1)

        if not xero_instance:
            record = self.env[active_model].browse(active_ids)
            record.message_post(body=f" Xero instance is not configured for {company.name}.")
            return

        if active_model == 'res.partner':
            record.export_partner_to_xero(xero_instance)

        if active_model == 'product.template':
            record.export_product_to_xr(xero_instance)

        if active_model == 'account.move' and not xero_instance.consolidated_invoice:
            record.export_invoice_bill_to_xero(xero_instance)

        if active_model == 'account.payment':
            record.export_xero_payment(xero_instance)

        if active_model == 'account.analytic.account':
            record.export_analytics_account(xero_instance)

        if active_model == 'account.account':
            record.export_charts_of_account_to_xero(xero_instance)

        if active_model == 'account.move' and xero_instance.consolidated_invoice:
            record.export_consolidated_invoice_to_xero(xero_instance)