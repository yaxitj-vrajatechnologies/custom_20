# -*- coding: utf-8 -*-
import csv
import io
from datetime import datetime, timedelta

from odoo import models, fields,api
from odoo.exceptions import UserError
from odoo.tools.binary import BinaryBytes
_DATE_FORMATS = ('%d/%m/%y', '%d/%m/%Y', '%Y-%m-%d', '%m/%d/%Y', '%d-%m-%Y')


class PriceQuotation(models.Model):
    _name = 'price.quotation'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Vendor Quotation for Price Comparison'
    _rec_name="vendor_id"
    _order = 'id desc'

    enquiry_id = fields.Many2one('price.enquiry', string='Enquiry',
                                 required=True, ondelete='cascade', tracking=True)
    vendor_id = fields.Many2one('res.partner', string='Vendor', required=True,tracking=True,
                                domain=[('supplier_rank', '>', 0)])

    rfq_sent_date = fields.Datetime(string='RFQ Sent On')
    valid_until = fields.Date(string='Quote Valid Until')

    line_ids = fields.One2many('price.quotation.line', 'quotation_id', string='Lines')

    rfq_attachment = fields.Binary(string='RFQ Sheet Sent', readonly=True)
    rfq_attachment_name = fields.Char(string='RFQ Filename', readonly=True)

    import_file = fields.Binary(string='Vendor Filled Sheet')
    import_filename = fields.Char(string='Import Filename')

    state = fields.Selection([
        ('draft', 'Draft'),
        ('sent', 'RFQ Sent'),
        ('received', 'Quote Received'),
    ], string='Status', compute='_compute_state', store=True, tracking=True)

    @api.depends('rfq_sent_date', 'import_file')
    def _compute_state(self):
        for quotation in self:
            if quotation.import_file:
                quotation.state = 'received'
            elif quotation.rfq_sent_date:
                quotation.state = 'sent'
            else:
                quotation.state = 'draft'

    def _generate_rfq_sheet(self):
        """Build a CSV with Product + Qty filled in, Price and Lead Time left blank,
        for the vendor to fill and send back."""
        self.ensure_one()
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(['Product Code', 'Product Name', 'Qty', 'Price',
                         'Lead Time (Days, or Delivery Date DD/MM/YYYY)'])
        for line in self.line_ids:
            writer.writerow([line.product_id.default_code or '', line.product_id.name,
                             line.qty_offered, '', ''])
        content = buffer.getvalue().encode('utf-8')
        self.write({
            'rfq_attachment': BinaryBytes(content),
            'rfq_attachment_name': 'RFQ_%s_%s.csv' % (self.enquiry_id.name, self.vendor_id.name),
        })

    def _parse_lead_time(self, raw_value, base_date):
        """Accept either a plain number of days ('15') or a delivery date
        ('27/07/2026', '27/07/26', '2026-07-27', ...) and return an integer
        number of days from base_date, or None if no value was supplied at
        all. Raises ValueError if it's neither blank, a number, nor a
        recognisable date."""
        raw_value = raw_value.strip() if isinstance(raw_value, str) else raw_value
        if raw_value in ('', None):
            return None

        try:
            return int(float(raw_value))
        except (TypeError, ValueError):
            pass

        for fmt in _DATE_FORMATS:
            try:
                delivery_date = datetime.strptime(str(raw_value).strip(), fmt).date()
                return (delivery_date - base_date).days
            except ValueError:
                continue

        raise ValueError(raw_value)

    def action_import_quotation(self):
        """Read the vendor filled sheet (import_file) and update Price + Lead Time
        on the matching lines. Returns a warning notification if some rows were
        skipped, or nothing on a clean import (used directly by the form button
        and internally by the bulk-import wizard)."""
        self.ensure_one()
        if not self.import_file:
            raise UserError('Please attach the vendor filled sheet first.')

        content = self.import_file.content.decode('utf-8')
        reader = csv.DictReader(io.StringIO(content))

        base_date = (self.rfq_sent_date and self.rfq_sent_date.date()) or fields.Date.context_today(self)

        line_by_code = {l.product_id.default_code: l for l in self.line_ids if l.product_id.default_code}
        line_by_name = {(l.product_id.name or '').strip().casefold(): l for l in self.line_ids}

        to_write = []  # list of (line, vals)
        errors = []
        for row_num, row in enumerate(reader, start=2):  # row 1 = header
            code = (row.get('Product Code') or '').strip()
            name = (row.get('Product Name') or '').strip()

            line = line_by_code.get(code) if code else None
            if not line:
                line = line_by_name.get(name.casefold())
            if not line:
                continue
            product = line.product_id

            price_raw = row.get('Price') or 0
            leadtime_raw = (row.get('Lead Time (Days, or Delivery Date DD/MM/YYYY)')
                            or row.get('Lead Time (Days)'))
            try:
                unit_price = float(price_raw)
            except (TypeError, ValueError):
                errors.append(
                    'Row %d (%s): "Price" value "%s" is not a valid number.'
                    % (row_num, product.display_name, price_raw))
                continue
            try:
                lead_time = self._parse_lead_time(leadtime_raw, base_date)
            except ValueError:
                errors.append(
                    'Row %d (%s): "Lead Time" value "%s" is not a valid number or date.'
                    % (row_num, product.display_name, leadtime_raw))
                continue

            if lead_time is None:
                # No lead time supplied in the file at all - leave it blank
                # (no lead time, no lead date), the price still gets imported.
                to_write.append((line, {
                    'unit_price': unit_price, 'lead_time': 0, 'has_lead_time': False,
                }))
                continue

            expected_date = base_date + timedelta(days=lead_time)
            if expected_date < fields.Date.context_today(self):
                # The resulting delivery date is already in the past (e.g. a
                # date from before today was entered in the file) - don't
                # block the import or fill in a misleading value, just leave
                # lead time/lead date blank for this line; price still
                # imports normally.
                to_write.append((line, {
                    'unit_price': unit_price, 'lead_time': 0, 'has_lead_time': False,
                }))
                continue

            to_write.append((line, {
                'unit_price': unit_price, 'lead_time': lead_time, 'has_lead_time': True,
            }))

        if not to_write and not errors:
            raise UserError('No matching product rows were found in the uploaded file.')

        if not to_write and errors:
            raise UserError(
                'The file could not be imported. Please fix these rows and re-upload:\n\n'
                + '\n'.join(errors)
            )

        for line, vals in to_write:
            line.write(vals)

        if errors:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Quotation partially imported',
                    'message': (
                            '%d row(s) imported. %d row(s) were skipped due to invalid data:\n%s'
                            % (len(to_write), len(errors), '\n'.join(errors))
                    ),
                    'sticky': True,
                    'type': 'warning',
                    'next': {'type': 'ir.actions.client', 'tag': 'reload'},
                },
            }

    def _send_rfq_email(self):
        """Email the already-generated RFQ sheet to the vendor. Returns an
        error string on failure (no email on file, send failure, etc.) so the
        caller can collect skipped vendors instead of aborting the whole batch."""
        self.ensure_one()
        if not self.rfq_attachment:
            return 'RFQ sheet not generated yet.'
        if not self.vendor_id.email:
            return '%s has no email address on file.' % self.vendor_id.name

        attachment = self.env['ir.attachment'].create({
            'name': self.rfq_attachment_name,
            'raw': self.rfq_attachment,
            'res_model': self._name,
            'res_id': self.id,
        })

        body = (
               '<p>Dear %s,</p>'
               '<p>Please find attached our RFQ sheet for enquiry <b>%s</b>. '
               'Kindly fill in the Price and Lead Time columns and send the '
               'file back to us.</p><p>Thank you.</p>'
               ) % (self.vendor_id.name, self.enquiry_id.name)

        mail = self.env['mail.mail'].create({
            'subject': 'Request for Quotation - %s' % self.enquiry_id.name,
            'body_html': body,
            'email_from': self.env.company.email or self.env.user.email,
            'email_to': self.vendor_id.email,
            'attachment_ids': [(6, 0, [attachment.id])],
        })
        mail.send(raise_exception=False)
        return False
