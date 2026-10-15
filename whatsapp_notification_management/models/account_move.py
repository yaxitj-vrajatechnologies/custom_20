import ast
import base64
from odoo import models, fields
from datetime import date


class AccountMove(models.Model):
    _inherit = "account.move"

    notification_sent = fields.Boolean(string="Notification Sent")

    def generate_invoice_pdf_report(self):
        for invoice in self:

            report_ref = self.env.ref('account.account_invoices_without_payment')
            pdf_content, _ = self.env['ir.actions.report']._render_qweb_pdf(report_ref, res_ids=[invoice.id])

            attachment = self.env['ir.attachment'].create({
                'name': f'{invoice.name}.pdf',
                'type': 'binary',
                'datas': base64.b64encode(pdf_content),
                'res_model': self._name,
                'res_id': invoice.id,
                'mimetype': 'application/pdf',
            })
            return attachment

    def send_overdue_invoice_whatsapp(self):
        invoices = self.env['account.move'].search([
            ('move_type', '=', 'out_invoice'),
            ('state', '=', 'posted'),
            ('payment_state', '!=', 'paid'),
            # ('notification_sent', '!=', True),
            ('invoice_date_due', '<', date.today())
        ])

        # Customer template
        template = self.env['whatsapp.template'].sudo().search([
            ('template_name', '=', 'overdue_invoice_reminder')
        ], limit=1)

        # Account Manager template
        manager_template = self.env['whatsapp.template'].sudo().search([
            ('template_name', '=', 'account_manager_overdue_invoice_reminder')
        ], limit=1)

        if not template and not manager_template:
            return

        config = self.env['ir.config_parameter'].sudo()
        manager_ids = config.get_str('whatsapp_notification_management.user_ids')

        account_managers = False

        if manager_ids:
            manager_ids = ast.literal_eval(manager_ids) # convert manager_ids from string to the list
            account_managers = self.env['res.users'].browse(manager_ids)

        for invoice in invoices:

            partner = invoice.partner_id

            # -------------------
            # Send Notification to Customer
            # -------------------
            if template and partner.phone:
                attachment = invoice.generate_invoice_pdf_report()

                composer = self.env['whatsapp.composer'].create({
                    'res_model': 'account.move',
                    'res_ids': str([invoice.id]),
                    'wa_template_id': template.id,

                    # Template variables
                    'free_text_1': partner.name or '',
                    'free_text_2': invoice.name or '',
                    'free_text_3': f"{invoice.amount_total:,.2f}",
                    'free_text_4': invoice.invoice_date_due.strftime('%d-%m-%Y') if invoice.invoice_date_due else '',
                    'free_text_5': self.env.company.name or '',

                    # Attachment
                    'attachment_id': attachment.id
                })

                composer.action_send_whatsapp_template()

            # -------------------
            # Send Notification to Account Managers
            # The manager template is attached to res.partner, so the message goes to
            # the manager's own phone and not to the invoice customer's phone.
            # -------------------
            if manager_template:
                for manager in account_managers or []:

                    if not manager.partner_id.phone:
                        continue

                    manager_composer = self.env['whatsapp.composer'].create({
                        'res_model': 'res.partner',
                        'res_ids': str([manager.partner_id.id]),
                        'wa_template_id': manager_template.id,

                        # Template variables
                        'free_text_1': manager.name or '',
                        'free_text_2': partner.name or '',
                        'free_text_3': invoice.name or '',
                        'free_text_4': f"{invoice.amount_total:,.2f}",
                        'free_text_5': invoice.invoice_date_due.strftime('%d-%m-%Y') if invoice.invoice_date_due else '',
                        'free_text_6': self.env.company.name or '',
                    })

                    manager_composer.action_send_whatsapp_template()

            invoice.sudo().write({'notification_sent': True})