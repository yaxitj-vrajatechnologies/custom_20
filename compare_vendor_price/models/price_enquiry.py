# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import UserError
from datetime import timedelta


class PriceEnquiry(models.Model):
    _name = 'price.enquiry'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Purchase Enquiry for Vendor Price Comparison'
    _order = 'id desc'

    name = fields.Char(string='Enquiry No.', default='New', readonly=True, copy=False)
    date = fields.Date(string='Enquiry Date', default=fields.Date.context_today, required=True)
    requested_by = fields.Many2one('res.users', string='Requested By', default=lambda self: self.env.user)
    required_by_date = fields.Date(string='Required By')

    state = fields.Selection([
        ('draft', 'Draft'),
        ('rfq_sent', 'RFQ Sent'),
        ('compared', 'Compared'),
        ('po_created', 'PO Created'),
    ], default='draft', string='Status', copy=False, tracking=True)

    line_ids = fields.One2many('price.enquiry.line', 'enquiry_id', string='Products')
    vendor_ids = fields.Many2many('res.partner', string='Vendors', domain=[('supplier_rank', '>', 0)])
    quotation_ids = fields.One2many('price.quotation', 'enquiry_id', string='Vendor Quotations')

    po_ids = fields.One2many('purchase.order', 'price_enquiry_ids', string='Purchase Orders')
    vendor_files_ids = fields.Many2many('ir.attachment', string='Vendor Filled Files')

    # --- Smart button counters -------------------------------------------------
    po_count = fields.Integer(compute='_compute_counts', string='POs')
    vendor_count = fields.Integer(compute='_compute_counts', string='Vendor Count')
    quotation_count = fields.Integer(compute='_compute_counts', string='Quotations')
    quotation_received_count = fields.Integer(compute='_compute_counts', string='Received')

    enable_recompare = fields.Boolean(
        string='Recompare Quotations', default=False,
        help='Enable to recompare the vendor quotations file.')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('price.enquiry') or 'New'
        return super().create(vals_list)

    @api.depends('po_ids', 'vendor_ids', 'quotation_ids', 'quotation_ids.state')
    def _compute_counts(self):
        for rec in self:
            rec.po_count = len(rec.po_ids)
            rec.vendor_count = len(rec.vendor_ids)
            rec.quotation_count = len(rec.quotation_ids)
            rec.quotation_received_count = len(rec.quotation_ids.filtered(lambda q: q.state == 'received'))

    def action_send_rfq(self):
        """Create/refresh one quotation record per selected vendor and generate
        an RFQ sheet (Product + Qty filled, Price + Lead Time left blank)."""
        self.ensure_one()
        if not self.line_ids:
            raise UserError('Please add at least one product before sending RFQ.')
        if not self.vendor_ids:
            raise UserError('Please select at least one vendor.')

        for vendor in self.vendor_ids:
            quotation = self.quotation_ids.filtered(lambda q: q.vendor_id == vendor)
            if not quotation:
                quotation = self.env['price.quotation'].create({
                    'enquiry_id': self.id,
                    'vendor_id': vendor.id,
                    'valid_until': self.required_by_date,
                })
            # Reset lines with product + qty only, price/lead time blank
            quotation.line_ids.unlink()
            quotation.write({
                'line_ids': [(0, 0, {
                    'product_id': eline.product_id.id,
                    'qty_requested': eline.qty,
                    'qty_offered': eline.qty,
                }) for eline in self.line_ids],
            })
            quotation._generate_rfq_sheet()
            quotation._send_rfq_email()
            quotation.write({'rfq_sent_date': fields.Datetime.now()})

        self.state = 'rfq_sent'

    def action_compare(self):
        """Import the CSV attached directly on each vendor quotation row
                (the "Upload CSV" column in the Vendor Quotations tab). Unlike
                _import_vendor_files, no filename-matching is needed here - the file
                is already sitting on the correct vendor's own row, since only one
                file can be attached per row at a time."""
        self.ensure_one()
        notification = self._import_per_line_files()

        # AFTER
        for eline in self.line_ids:
            qlines = self.quotation_ids.mapped('line_ids').filtered(
                lambda l: l.product_id == eline.product_id
                          and l.quotation_id.state == 'received'
                          and l.quotation_id.import_file
            )
            if not qlines:
                eline.winning_line_id = False
                continue
            min_price = min(qlines.mapped('unit_price'))
            tied_lines = qlines.filtered(lambda l: l.unit_price == min_price)
            if len(tied_lines) > 1:
                # Same price from multiple vendors -> fastest lead time wins.
                # Lines with no known lead time (blank) are not treated as
                # "fastest" just because their stored value is 0.
                known_lead_lines = tied_lines.filtered(lambda l: l.has_lead_time)
                if known_lead_lines:
                    min_lead = min(known_lead_lines.mapped('lead_time'))
                    tied_lines = known_lead_lines.filtered(lambda l: l.lead_time == min_lead)
            eline.winning_line_id = tied_lines[:1].id

        self.state = 'compared'
        self.enable_recompare = False

        if notification:
            notification['params']['next'] = {'type': 'ir.actions.client', 'tag': 'reload'}
            return notification
        return True

    def action_create_po(self):
        """Group every product's currently-picked vendor (line_ids.winning_line_id)
        by vendor and create one PO per vendor - unless a draft PO for that
        vendor already exists somewhere in the system, in which case the
        products are merged into it instead of creating a new one:
          - product not yet on that PO -> new order line added, with our qty
          - product already on that PO -> its qty is increased by our qty,
            and its price is refreshed to the price we just compared/picked
        Lines already converted into a PO are skipped so re-running this
        never duplicates."""
        self.ensure_one()
        winning_lines = self.line_ids.mapped('winning_line_id')
        selected_lines = winning_lines.filtered(lambda l: not l.is_po_created)
        if not selected_lines:
            already_done = winning_lines.filtered(lambda l: l.is_po_created)
            if already_done:
                raise UserError(
                    'All selected lines already have a PO created for them. '
                    'Select a different winner if you need to change something.'
                )
            raise UserError('Please pick a vendor for at least one product before creating PO.')
        zero_price_lines = selected_lines.filtered(lambda l: l.unit_price <= 0)
        if zero_price_lines:
            raise UserError(
                'The following product(s) have a price of 0 - this usually means the '
                "vendor's file didn't match correctly during import. "
                ' Please re-check the upload and re-import before creating a PO:\n\n'
                + '\n'.join('%s (%s)' % (l.product_id.display_name, l.quotation_id.vendor_id.name)
                            for l in zero_price_lines)
            )

        vendors = selected_lines.mapped('quotation_id.vendor_id')
        created_po_ids = []
        for vendor in vendors:
            vendor_lines = selected_lines.filtered(lambda l: l.quotation_id.vendor_id == vendor)

            existing_po = self.env['purchase.order'].search([
                ('partner_id', '=', vendor.id),
                ('state', '=', 'draft'),
            ], order='id desc', limit=1)

            if existing_po:
                po = existing_po
                # Only claim it for this enquiry if it isn't already tied to
                # one - don't steal a PO that belongs to another enquiry.
                po.price_enquiry_ids = [(6, 0, [self.id])]

                new_line_vals = []
                for l in vendor_lines:
                    existing_line = po.order_line.filtered(lambda ol: ol.product_id == l.product_id)
                    if existing_line:
                        existing_line[0].write({
                            'product_qty': existing_line[0].product_qty + l.qty_offered,
                            'price_unit': l.unit_price,
                        })
                    else:
                        new_line_vals.append((0, 0, {
                            'product_id': l.product_id.id,
                            'product_qty': l.qty_offered,
                            'price_unit': l.unit_price,
                            # 'product_uom_id': l.product_id.uom_id.id,
                            'date_planned': fields.Datetime.now() + timedelta(days=l.lead_time),
                        }))
                if new_line_vals:
                    po.write({'order_line': new_line_vals})
            else:
                po = self.env['purchase.order'].create({
                    'partner_id': vendor.id,
                    'price_enquiry_ids': [(6, 0, [self.id])],
                    'order_line': [(0, 0, {
                        'product_id': l.product_id.id,
                        'product_qty': l.qty_offered,
                        'price_unit': l.unit_price,
                        # 'product_uom_id': l.product_id.uom_id.id,
                        'date_planned': fields.Datetime.now() + timedelta(days=l.lead_time),
                    }) for l in vendor_lines],
                })

            created_po_ids.append(po.id)
            vendor_lines.write({'is_po_created': True})
        self.enable_recompare = False
        self.state = 'po_created'
        return {
            'type': 'ir.actions.act_window',
            'name': 'Purchase Orders',
            'res_model': 'purchase.order',
            'view_mode': 'list,form',
            'domain': [('id', 'in', created_po_ids)],
        }

    def action_reset_to_draft(self):
        """Unlock the enquiry so products/vendors can be edited again.
        Existing quotations are left untouched - re-running Send RFQ will
        simply refresh/reuse them per vendor as usual. Blocked if any
        non-cancelled PO already exists, since resetting past a live
        purchase document would leave it orphaned."""
        self.ensure_one()
        active_pos = self.po_ids.filtered(lambda p: p.state != 'cancel')
        if active_pos:
            raise UserError(
                'Cannot reset to draft: Purchase Order(s) %s already exist '
                'for this enquiry. Cancel them first.'
                % ', '.join(active_pos.mapped('name'))
            )
        self.state = 'draft'

    # --- Smart button actions ---------------------------------------------------
    def action_view_po(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Purchase Orders',
            'res_model': 'purchase.order',
            'view_mode': 'list,form',
            'domain': [('price_enquiry_ids', '=', self.id)],
        }

    def action_view_vendors(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Vendors',
            'res_model': 'res.partner',
            'view_mode': 'list,form',
            'domain': [('id', 'in', self.vendor_ids.ids)],
        }

    def action_view_quotations(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Vendor Quotations',
            'res_model': 'price.quotation',
            'view_mode': 'list,form',
            'domain': [('enquiry_id', '=', self.id)],
        }

    def _import_per_line_files(self):
        """Import the CSV attached directly on each vendor quotation row
        (the "Upload CSV" column in the Vendor Quotations tab). Unlike
        _import_vendor_files, no filename-matching is needed here - the file
        is already sitting on the correct vendor's own row, since only one
        file can be attached per row at a time."""
        self.ensure_one()
        # quotations = self.quotation_ids.filtered(lambda q: q.import_file and q.state != 'received')
        quotations = self.quotation_ids.filtered(lambda q: q.import_file)

        if not quotations:
            return None

        matched, warnings, failures = [], [], []
        for quotation in quotations:
            try:
                result = quotation.action_import_quotation()
                if result:
                    warnings.append('%s (%s): %s' % (
                        quotation.vendor_id.name, quotation.import_filename or '', result['params']['message']))
                else:
                    matched.append('%s (%s)' % (quotation.vendor_id.name, quotation.import_filename or ''))
            except UserError as e:
                failures.append('%s (%s): %s' % (quotation.vendor_id.name, quotation.import_filename or '', e))

        message_parts = []
        if matched:
            message_parts.append('Imported cleanly: %s' % ', '.join(matched))
        if warnings:
            message_parts.append('Imported with warnings:\n' + '\n'.join(warnings))
        if failures:
            message_parts.append('Failed to import:\n' + '\n'.join(failures))

        if not message_parts:
            return None

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Vendor quotation files imported',
                'message': '\n\n'.join(message_parts),
                'sticky': True,
                'type': 'danger' if failures else ('warning' if warnings else 'success'),
            },
        }
