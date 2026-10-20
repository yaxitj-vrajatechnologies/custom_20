from itertools import product

from odoo import models, fields

class InstanceWizard(models.TransientModel):
    _name = "instance.wizard"

    instance_id = fields.Many2one('quickbooks.connect',string='Quickbooks Instance')

    def qbk_export_operation(self):
        active_ids = self.env.context.get('active_ids')
        active_model = self.env.context.get('active_model')
        record = self.env[active_model].browse(active_ids)

        company = (record.company_id if 'company_id' in record._fields and record.company_id else self.env.company)

        quickbook_instance = self.env['quickbooks.connect'].sudo().search(
            [('id', '=', self.instance_id.id), ('state', '=', 'connected'), ('company_id', '=', company.id), ], limit=1)

        if not quickbook_instance:
            record = self.env[active_model].browse(active_ids)
            record.message_post(body=f" QuickBooks instance is not configured for {company.name}.")
            return

        if active_model == 'res.partner':
            record.export_customer_to_quickbooks(self.instance_id)

        if active_model == 'product.template':
            record.export_product_to_quickbooks(self.instance_id)

        if active_model == 'account.move':
            record.export_invoice_bill_to_quickbooks(self.instance_id)

        if active_model == 'account.payment':
            record.export_payment_to_quickbooks(self.instance_id)

