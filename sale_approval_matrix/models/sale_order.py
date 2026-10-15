# -*- coding: utf-8 -*-
from odoo import api, fields, models, _, tools
from odoo.exceptions import UserError


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    total_margin_percent = fields.Float(
        string='Overall Margin %', compute='_compute_total_margin_percent',
        store=True, digits=(16, 2))

    approval_zone = fields.Selection([
        ('green', 'Green'),
        ('yellow', 'Yellow'),
        ('red', 'Red'),
    ], string='Approval Zone', compute='_compute_approval_zone', store=True)

    show_manager_review_banner = fields.Boolean(
        string='Show Manager Review Banner (Red)', compute='_compute_approval_zone', store=True,
        help="True when the matrix places this quotation in the Red zone.")
    show_yellow_review_banner = fields.Boolean(
        string='Show Manager Review Banner (Yellow)', compute='_compute_approval_zone', store=True,
        help="True when the matrix places this quotation in the Yellow zone.")

    approval_state = fields.Selection([
        ('draft', 'Not Requested'),
        ('pending', 'Pending Approval'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ], string='Approval Status', default='draft', copy=False, tracking=True)

    approval_manager_id = fields.Many2one(
        'res.users', string='Approved/Rejected By', copy=False, readonly=True)
    approval_date = fields.Datetime(string='Approval Date', copy=False, readonly=True)
    approval_reject_reason = fields.Text(string='Rejection Reason', copy=False, readonly=True)

    @api.depends('amount_untaxed', 'margin')
    def _compute_total_margin_percent(self):
        # Margin is computed against the UNTAXED total. Tax is a pass-through to the
        # government, not revenue, and sale_margin's line-level margin_percent is also
        # computed on the untaxed subtotal - using amount_total here would mismatch it
        # and would let a customer's tax rate shift which approval band an order falls into.
        for order in self:
            order.total_margin_percent = (
                (order.margin / order.amount_untaxed) * 100.0 if order.amount_untaxed else 0.0
            )

    @api.depends('amount_untaxed', 'total_margin_percent', 'company_id.approval_matrix_enabled')
    def _compute_approval_zone(self):
        Matrix = self.env['approval.matrix.line']
        for order in self:
            if not order.company_id.approval_matrix_enabled:
                # Feature switched off for this company: behave as if the module
                # were not installed - no zone, no banners, nothing blocked.
                order.approval_zone = 'green'
                order.show_manager_review_banner = False
                order.show_yellow_review_banner = False
                continue

            zone = False
            if order.order_line:
                line = Matrix.search([
                    ('revenue_from', '<=', order.amount_untaxed),
                    ('revenue_to', '>=', order.amount_untaxed),
                    ('margin_from', '<=', order.total_margin_percent),
                    ('margin_to', '>=', order.total_margin_percent),
                ], order='sequence', limit=1)
                # If nothing in the matrix covers this combination, fail safe to 'red'
                # so it is never silently auto-approved.
                zone = line.zone if line else 'red'
            order.approval_zone = zone or 'green'

            has_lines = bool(order.order_line)
            # Both banners are driven purely by the matrix-derived zone - the zone
            # computation above already correctly accounts for "margin below 10%" (it's
            # the leftmost column of the matrix) AND the revenue-dependent cases where
            # 10-12% (or higher) is also Red for larger orders. Do not re-check margin
            # < 10% separately here, or you'll miss Red cells where margin is >= 10%.
            order.show_manager_review_banner = has_lines and order.approval_zone == 'red'
            order.show_yellow_review_banner = has_lines and order.approval_zone == 'yellow'

    # ---------------------------------------------------------
    # Approval workflow actions
    # ---------------------------------------------------------
    def action_request_approval(self):
        self.ensure_one()
        if not self.company_id.approval_matrix_enabled:
            raise UserError(_(
                "The Sales Approval Matrix is currently disabled for this company. "
                "Enable it in Settings > Sales to use this feature."
            ))
        if self.approval_zone == 'green':
            raise UserError(_("This quotation is within approved limits and does not require manager approval."))

        self.write({
            'approval_state': 'pending',
            'approval_reject_reason': False,
        })

        managers = self._get_approval_notify_users()
        note = _(
            "Quotation <b>%(name)s</b> requires manager approval.<br/>"
            "Revenue: %(revenue)s<br/>Overall Margin: %(margin).2f%%<br/>Zone: %(zone)s"
        ) % {
            'name': self.name,
            'revenue': self.amount_untaxed,
            'margin': self.total_margin_percent,
            'zone': (self.approval_zone or '').upper(),
        }
        for manager in managers:
            self.activity_schedule(
                'mail.mail_activity_data_todo',
                summary=_('Approval Required: %s') % self.name,
                note=note,
                user_id=manager.id,
            )
        self.message_post(body=tools.html_sanitize(_(
            "Approval requested by %(user)s.<br/>Revenue: %(revenue)s<br/>"
            "Overall Margin: %(margin).2f%%<br/>Zone: %(zone)s"
        )) % {
            'user': self.env.user.name,
            'revenue': self.amount_untaxed,
            'margin': self.total_margin_percent,
            'zone': (self.approval_zone or '').upper(),
        },
        partner_ids=managers.mapped('partner_id').ids,
        )
        return True

    def _get_approval_notify_users(self):
        """Who gets notified/assigned an activity when approval is requested.

        Priority: this order's Sales Team's configured Approval Managers.
        Falls back to the full Sales Manager group when the team has none
        configured, or when the order has no Sales Team assigned at all -
        this guarantees a request is never sent into a silent void just
        because a team hasn't been set up yet.
        """
        self.ensure_one()
        if self.team_id and self.team_id.approval_manager_ids:
            return self.team_id.approval_manager_ids
        return self.env.ref('sales_team.group_sale_manager').user_ids

    def action_approve_quotation(self):
        self.ensure_one()
        if not self.env.user.has_group('sales_team.group_sale_manager'):
            raise UserError(_("Only Sales Managers can approve quotations."))
        if self.approval_state != 'pending':
            raise UserError(_("Only quotations pending approval can be approved."))

        self.write({
            'approval_state': 'approved',
            'approval_manager_id': self.env.user.id,
            'approval_date': fields.Datetime.now(),
        })
        self._close_approval_activities()
        self.message_post(
            body=tools.html_sanitize(_("Quotation approved by %s.")) % self.env.user.name,
            partner_ids=self._get_salesperson_partner_ids(),
        )
        return True

    def action_reject_quotation(self):
        """Opens a wizard so the manager can record a rejection reason."""
        self.ensure_one()
        if not self.env.user.has_group('sales_team.group_sale_manager'):
            raise UserError(_("Only Sales Managers can reject quotations."))
        if self.approval_state != 'pending':
            raise UserError(_("Only quotations pending approval can be rejected."))

        return {
            'type': 'ir.actions.act_window',
            'name': _('Reject Quotation'),
            'res_model': 'approval.matrix.reject.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_sale_order_id': self.id},
        }

    def _close_approval_activities(self):
        self.ensure_one()
        activities = self.activity_ids.filtered(
            lambda a: a.summary and self.name and self.name in a.summary)
        if activities:
            activities.action_feedback(feedback=_('Processed'))

    def _get_salesperson_partner_ids(self):
        """Returns the partner_id of this order's salesperson, as a list, for use in
        message_post(partner_ids=...). Empty list if no salesperson is assigned, so
        callers don't need to guard against a missing user_id themselves."""
        self.ensure_one()
        if self.user_id and self.user_id.partner_id:
            return [self.user_id.partner_id.id]
        return []

    # ---------------------------------------------------------
    # Guard rails: block send / confirm until approved
    # ---------------------------------------------------------
    def action_quotation_send(self):
        for order in self:
            if order.approval_zone != 'green' and order.approval_state != 'approved':
                raise UserError(_(
                    "Quotation %s requires manager approval before it can be sent. "
                    "Please request approval first."
                ) % order.name)
        return super().action_quotation_send()

    def action_confirm(self):
        for order in self:
            if order.approval_zone != 'green' and order.approval_state != 'approved':
                raise UserError(_(
                    "Quotation %s requires manager approval before it can be confirmed. "
                    "Please request approval first."
                ) % order.name)
        return super().action_confirm()

    def action_cancel(self):
        result = super().action_cancel()
        self.write({'approval_state': 'draft'})
        return result


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    line_risk_flag = fields.Selection([
        ('none', 'None'),
        ('amber', 'Amber'),
        ('red', 'Red'),
    ], string='Line Risk', compute='_compute_line_risk_flag', store=True)

    @api.depends('margin', 'margin_percent', 'display_type', 'order_id.company_id.approval_matrix_enabled')
    def _compute_line_risk_flag(self):
        for line in self:
            if not line.order_id.company_id.approval_matrix_enabled:
                line.line_risk_flag = 'none'
                continue
            if line.display_type or not line.product_id:
                line.line_risk_flag = 'none'
                continue
            if line.margin < 0:
                line.line_risk_flag = 'red'
            elif (line.margin_percent * 100.0) < 10.0:
                line.line_risk_flag = 'amber'
            else:
                line.line_risk_flag = 'none'
