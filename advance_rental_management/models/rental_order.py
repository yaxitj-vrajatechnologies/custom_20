from datetime import datetime, timedelta
from odoo import models, fields, api


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    is_damage_after_returned = fields.Boolean(
        string='Damage After Returned?',
        default=False,
        copy=False
    )
    ord_total_amount = fields.Monetary(
        string="Total Amount",
        compute='compute_total_amounts',
        store=True,
        copy=False
    )

    @api.depends('amount_total')
    def compute_total_amounts(self):
        for ord in self:
            ord.ord_total_amount = ord.amount_total

    def action_advance_payment(self):
        action = self.env.ref('advance_rental_management.action_advance_payment_wizard')
        return action.read()[0]

    @api.model
    def send_rental_return_reminders(self):
        # Get today's date and calculate tomorrow's date
        today = datetime.today()
        tomorrow = today + timedelta(days=1)

        # Search for rental orders where the rental_return_date is tomorrow
        rental_orders = self.env['sale.order'].search([])
        pickup_orders = rental_orders.filtered(lambda
                                   a: a.rental_return_date and a.rental_return_date.date() == tomorrow.date() and a.rental_status == 'return')

        for order in pickup_orders:
            # Send email to the customer
            customer_subject = f"Reminder: Rental Period Ending Tomorrow (Order {order.name})"
            customer_body = f"Dear {order.partner_id.name},\n\n" \
                            f"This is a reminder that your rental period for the order {order.name} is ending tomorrow, {tomorrow.date()}." \
                            " Please make arrangements for the return of the items.\n\n" \
                            "If you have any questions, feel free to contact us.\n\n" \
                            "Best regards"
            if order.partner_id.email:
                self.env['mail.mail'].create({
                    'subject': customer_subject,
                    'body_html': f'<pre>{customer_body}</pre>',
                    'email_to': order.partner_id.email,
                    'auto_delete': True,
                }).send()

            # Send email to the salesperson
            salesperson_subject = f"Rental Order Reminder: Rental Period Ending Tomorrow (Order {order.name})"
            salesperson_body = f"Dear {order.user_id.name},\n\n" \
                               f"Please be informed that the rental period for order {order.name} will be ending tomorrow, {tomorrow.date()}." \
                               " Kindly follow up with the customer to ensure the return process goes smoothly.\n\n" \
                               "Best regards"
            if order.user_id.email:
                self.env['mail.mail'].create({
                    'subject': salesperson_subject,
                    'body_html': f'<pre>{salesperson_body}</pre>',
                    'email_to': order.user_id.email,
                    'auto_delete': True,
                }).send()

        return True

    def open_repair_wizard(self):
        # Create repair order wizard and populate the order lines
        wizard = self.env['repair.order.wizard'].create({
            'sale_order_id': self.id,
            'order_line_ids': [(0, 0, {
                'product_id': line.product_id.id,
                'quantity': line.product_uom_qty
            }) for line in self.order_line if line.product_id and line.product_uom_qty > 0]
        })
        return {
            'name': 'Create Repair Order',
            'type': 'ir.actions.act_window',
            'res_model': 'repair.order.wizard',
            'view_mode': 'form',
            'view_id': self.env.ref('advance_rental_management.view_repair_order_wizard').id,
            'target': 'new',
            'res_id': wizard.id,
        }
