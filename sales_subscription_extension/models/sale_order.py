from odoo.exceptions import UserError
from odoo import models,fields,api,_

class SaleOrder(models.Model):
    _inherit = "sale.order"

    subscription_state = fields.Selection(selection_add=[('8_downgrade', 'Downgrade')])
    move_id = fields.Many2one('account.move',string="Credit Note", store=True)
    credit_note_count = fields.Integer(string="Credit Note Count", compute='_compute_credit_note_count')

    def _compute_credit_note_count(self):
        for rec in self:
            rec.credit_note_count = self.env['account.move'].search_count([('id', '=', rec.move_id.id)])

    def action_credit_note(self):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id("account.action_move_out_refund_type_non_legacy")
        action['domain'] = [('move_type', '=', 'out_refund'),('invoice_origin', '=', self.name)]
        return action

    @api.model_create_multi
    def create(self, vals_list):
        orders = super().create(vals_list)
        for order in orders:
            if order.subscription_id and order.subscription_id.validity_date and order.subscription_id.date_order:
                order.validity_date = order.subscription_id.validity_date
                order.date_order = order.subscription_id.date_order

        return orders

    def _create_invoices(self, final=False, grouped=False):
        """ Create invoice(s) for the given Sales Order(s).
                :param bool grouped: if True, invoices are grouped by SO id.
                    If False, invoices are grouped by keys returned by :meth:`_get_invoice_grouping_keys`
                :param bool final: if True, refunds will be generated if necessary
                :param date: unused parameter
                :returns: created invoices
                :rtype: `account.move` recordset
                :raises: UserError if one of the orders has no invoiceable lines.
        """
        invoices = super()._create_invoices(final=final, grouped=grouped)

        for order in self:
            if order.subscription_state != '7_upsell':
                continue

            if not order.subscription_id:
                continue

            date_start = order.subscription_id.date_order.date()
            order.validity_date = order.subscription_id.validity_date
            date_end = order.validity_date

            total_days = 0
            remaining_days = 0

            if date_start and date_end:
                total_days = (date_end - date_start).days
                remaining_days = max(0, (date_end - fields.Date.today()).days)

            for invoice in invoices.filtered(lambda m: m.invoice_origin == order.name):

                for line in invoice.invoice_line_ids:
                    so_line = line.sale_line_ids[:1]

                    if not so_line:
                        continue

                    price = so_line.price_unit
                    qty = so_line.product_uom_qty
                    prorated_amount = 0

                    if total_days > 0:
                        prorated_amount = (price * qty / total_days) * remaining_days
                        if prorated_amount:
                            prorated_amount /= qty
                    if line.product_id:
                        line.write({
                            'price_unit': prorated_amount,
                            'name': f'{remaining_days} Days {fields.Date.today()} to {date_end}',
                        })
        return invoices

     # ------------------------------------------------------------------------------------------
     #            Downgrade order (credit note creation)
     # --------------------------------------------------------------------------------------------

    @api.depends('is_subscription')
    def _compute_subscription_state(self):
        """inherit and extend the base compute method and add  state in the condition that is skipped."""
        for order in self:
            if order.state not in ['draft', 'sent']:
                continue
            elif order.subscription_state in ['2_renewal', '7_upsell', '8_downgrade']:
                continue
            elif order.is_subscription:
                order.subscription_state = '2_renewal' if order.subscription_id else '1_draft'
            else:
                order.subscription_state = False

    def action_confirm(self):
        parent_dates = {}
        for order in self:
            if order.subscription_state == '8_downgrade' and order.subscription_id:

                parent_order = order.subscription_id
                parent_dates[order.id] = parent_order.date_order
                if order.amount_total >= parent_order.amount_total:
                    raise UserError(_("Downgrade order must be cheaper than the parent subscription."))

                today = fields.Date.today()
                start_date = parent_order.date_order.date()
                expire_date = parent_order.validity_date

                total_days = (expire_date - start_date).days
                remaining_days = (expire_date - today).days

                if remaining_days <= 0 or total_days <= 0:
                    return

                old_remaining_value = (parent_order.amount_total / total_days) * remaining_days
                downgrade_remaining_value = (order.amount_total / total_days) * remaining_days
                credit_amount = old_remaining_value - downgrade_remaining_value

                if credit_amount > 0:
                    credit_note = order._create_downgrade_credit_note(order, credit_amount)
                    order.move_id = credit_note.id

                parent_order.subscription_state = '6_churn'
                parent_order.end_date = fields.Date().today()
                parent_order.close_reason_id = self.env['sale.order.close.reason'].sudo().search(
                    [('name', '=', 'End of contract')], limit=1).id

        res = super().action_confirm()
        for order in self:
            if order.id in parent_dates:
                order.date_order = parent_dates[order.id]
        return res

    def _create_downgrade_credit_note(self, order, credit_amount):
        line_vals = []
        product_id = self.env['product.product'].sudo().search([('name','=','Refund Product')],limit=1)
        line_vals.append((0, 0, {
            'product_id': product_id.id,
            'quantity': 1,
            'price_unit': credit_amount,
            'tax_ids': [(6, 0, [])],
        }))
        move = self.env['account.move'].create({
            'move_type': 'out_refund',
            'partner_id': order.partner_id.id,
            'invoice_origin': order.name,
            'invoice_payment_term_id': order.payment_term_id.id,
            'currency_id': order.currency_id.id,
            'invoice_line_ids': line_vals,
        })

        move.action_post()

        return move

    def _prepare_downgrade_order_values(self):
        self.ensure_one()

        order_lines = []
        for line in self.order_line:
            order_lines.append((0, 0, {
                'product_id': line.product_id.id,
                'name': line.name,
                'product_uom_qty': line.product_uom_qty,
                'price_unit': line.price_unit,
            }))

        values = {
            'is_subscription': True,
            'subscription_id': self.id,
            'origin_order_id': self.id,
            'date_order':self.date_order,
            'validity_date':self.validity_date,
            'plan_id':self.plan_id.id if self.plan_id else False,
            'partner_id': self.partner_id.id,
            'partner_invoice_id': self.partner_invoice_id.id,
            'partner_shipping_id': self.partner_shipping_id.id,
            'order_line': order_lines,
            'subscription_state': '8_downgrade',
            'pricelist_id': self.pricelist_id.id if self.pricelist_id else False,
            'payment_term_id': self.payment_term_id.id if self.payment_term_id else False,
            'user_id': self.user_id.id,
            'company_id': self.company_id.id,
            'note': self.note,
            'start_date': self.start_date,
            'next_invoice_date': self.next_invoice_date,
        }

        return values

    def action_downgrade_order(self):
        self.ensure_one()

        today = fields.Date.today()

        if self.next_invoice_date and self.next_invoice_date <= max(self.first_contract_date or today, today):
            raise UserError(_(
                "You can not downgrade a subscription that has not been invoiced yet. "
                "Please, update directly the %s contract or invoice it first."
            ) % self.name)

        values = self._prepare_downgrade_order_values()
        downgrade_order = self.env['sale.order'].create(values)
        view = self.env.ref('sale_subscription.sale_subscription_primary_form_view')

        return {
            'name': 'Downgrade Order',
            'type': 'ir.actions.act_window',
            'res_model': 'sale.order',
            'view_mode': 'form',
            'view_id': view.id,
            'res_id': downgrade_order.id,
            'target': 'current',
        }