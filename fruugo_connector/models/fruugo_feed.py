# -*- coding: utf-8 -*-
import base64
import logging
import time
import uuid
from datetime import timedelta
from xml.sax.saxutils import escape

from odoo import api, fields, models, _

_logger = logging.getLogger(__name__)

# ─── Fruugo XML Feed filename — always fixed so the URL never changes ────────
FEED_FILENAME = 'fruugo_feed.xml'
FRUUGO_SUPPORTED_LANGUAGES = {
    'en', 'fr', 'de', 'es', 'pt', 'nl', 'pl', 'it', 'da',
    'sv', 'fi', 'no', 'cs', 'el', 'hu', 'tr', 'sk', 'ro',
}


class FruugoFeed(models.Model):
    _name = 'fruugo.feed'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Fruugo Product Feed'
    _rec_name = 'name'
    _order = 'name asc'

    # ── Identity ──────────────────────────────────────────────────────────────
    name = fields.Char(string='Feed Name', required=True, tracking=True)
    active = fields.Boolean(default=True)
    state = fields.Selection(
        [('draft', 'Draft'), ('active', 'Active'), ('paused', 'Paused')],
        string='State', default='draft', tracking=True,
    )
    color = fields.Integer(string='Color')

    # ── Public URL (token-based, fixed forever) ───────────────────────────────
    feed_token = fields.Char(
        string='Feed Token',
        readonly=True,
        copy=False,
        default=lambda self: uuid.uuid4().hex,
        help='Auto-generated secure token. Part of the fixed feed URL given to Fruugo.',
    )
    store_url = fields.Char(
        string='Store Base URL',
        required=True,
        default=lambda self: self.env['ir.config_parameter'].sudo().get_str('web.base.url', ''),
        help='Your Odoo site base URL (e.g. https://yourshop.com). Used for image URLs in the feed.',
    )
    feed_url = fields.Char(
        string='Feed URL (Give this to Fruugo)',
        compute='_compute_feed_url',
        store=False,
    )

    # ── Language & Currency ───────────────────────────────────────────────────
    language_id = fields.Many2one(
        'res.lang', string='Feed Language',
        default=lambda self: self.env.ref('base.lang_en', raise_if_not_found=False),
        help='ISO language code of text fields (Title, Description, etc.).',
    )
    currency_id = fields.Many2one(
        'res.currency', string='Currency',
        default=lambda self: self.env.company.currency_id,
    )
    pricelist_id = fields.Many2one(
        'product.pricelist', string='Pricelist',
        help='If set, prices are computed using this pricelist.',
    )

    # ── Pricing / VAT ─────────────────────────────────────────────────────────
    price_include_vat = fields.Boolean(
        string='Price Includes VAT',
        default=False,
        help=(
            'If checked → feed uses <NormalPriceWithVAT> (tax-inclusive price).\n'
            'If unchecked → feed uses <NormalPriceWithoutVAT> (tax-exclusive price).'
        ),
    )
    default_vat_rate = fields.Float(
        string='Default VAT Rate (%)',
        default=0.0,
        help='VAT rate to use when no tax is set on the product. EU retailers: 20. Non-EU: 0.',
    )

    # ── Product Filter ────────────────────────────────────────────────────────
    product_domain = fields.Char(
        string='Product Domain (Filter)',
        default="[('sale_ok', '=', True), ('is_published', '=', True)]",
        help='Odoo domain to filter products. Leave empty to include all storable/consumable products.',
    )
    include_variants = fields.Boolean(
        string='Include Variants',
        default=True,
        help='When enabled, each product variant is exported as a separate <Product> row.',
    )
    max_products = fields.Integer(
        string='Max Products (0 = unlimited)',
        default=0,
    )
    stock_location_ids = fields.Many2many(
        'stock.location',
        'fruugo_feed_stock_location_rel',
        'feed_id', 'location_id',
        string='Stock Locations',
        domain="[('usage', '=', 'internal')]",
        help=(
            'Filter stock quantity by specific internal locations. '
            'Leave empty to use total on-hand quantity across all locations.'
        ),
    )

    # ── Logs / Status ─────────────────────────────────────────────────────────
    log_ids = fields.One2many('fruugo.feed.log', 'feed_id', string='Generation Logs')
    log_count = fields.Integer(string='Logs', compute='_compute_log_count')
    last_generated = fields.Datetime(string='Last Generated', readonly=True)
    last_status = fields.Selection(
        [('success', 'Success'), ('error', 'Error')],
        string='Last Status', readonly=True,
    )
    log_cleanup_enabled = fields.Boolean(
        string='Auto Cleanup Logs',
        default=False,
        help='If enabled, scheduled cleanup deletes old logs and their XML attachments for this feed.',
    )
    log_retention_days = fields.Integer(
        string='Keep Logs For (Days)',
        default=30,
        help='Logs older than this many days will be removed by scheduled cleanup.',
    )

    # ── Computeds ─────────────────────────────────────────────────────────────
    @api.depends('feed_token', 'store_url')
    def _compute_feed_url(self):
        for rec in self:
            base = (rec.store_url or '').rstrip('/')
            token = rec.feed_token or ''
            rec.feed_url = '%s/fruugo/feed/%s.xml' % (base, token) if token else ''

    def _compute_log_count(self):
        for rec in self:
            rec.log_count = self.env['fruugo.feed.log'].search_count([('feed_id', '=', rec.id)])

    # ── Token management ──────────────────────────────────────────────────────
    def action_regenerate_token(self):
        """Regenerate the feed token. WARNING: this changes the feed URL — notify Fruugo."""
        for rec in self:
            rec.feed_token = uuid.uuid4().hex
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Feed Token Regenerated'),
                'message': _(
                    'The feed URL has changed! You must update the URL in your Fruugo Retailer Portal.'
                ),
                'type': 'warning',
                'sticky': True,
            },
        }

    # ── State transitions ─────────────────────────────────────────────────────
    def action_activate(self):
        self.write({'state': 'active'})

    def action_pause(self):
        self.write({'state': 'paused'})

    def action_reset_draft(self):
        self.write({'state': 'draft'})

    def action_view_logs(self):
        self.ensure_one()
        return {
            'name': _('Feed Logs – %s') % self.name,
            'type': 'ir.actions.act_window',
            'res_model': 'fruugo.feed.log',
            'view_mode': 'list,form',
            'domain': [('feed_id', '=', self.id)],
        }

    # ── Manual trigger ────────────────────────────────────────────────────────
    def action_generate_now(self):
        """Manual feed generation — creates a log with the XML attached."""
        self.ensure_one()
        self._run_feed_generation(trigger='manual')
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Feed Generated'),
                'message': _("Feed '%s' generated successfully! Check the Logs tab for the attached XML file.") % self.name,
                'type': 'success',
                'sticky': False,
            },
        }

    def action_cleanup_old_logs(self):
        """Manual cleanup trigger from form view."""
        self.ensure_one()
        removed = self._cleanup_old_logs()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Cleanup Completed'),
                'message': _('%(count)d old logs removed for "%(feed)s".') % {
                    'count': removed,
                    'feed': self.name,
                },
                'type': 'success',
                'sticky': False,
                'next': {'type': 'ir.actions.client', 'tag': 'reload'},
            },
        }

    # ── Cron entry point ──────────────────────────────────────────────────────
    @api.model
    def run_scheduled_feed_generation(self):
        """Called by ir.cron. Generates XML for all active feeds."""
        active_feeds = self.search([('state', '=', 'active')])
        for feed in active_feeds:
            try:
                feed._run_feed_generation(trigger='scheduled')
            except Exception as exc:
                _logger.error("Fruugo Feed '%s' scheduled generation failed: %s", feed.name, exc)

    @api.model
    def run_scheduled_log_cleanup(self):
        """Called by ir.cron. Cleans old logs/attachments for opted-in feeds."""
        feeds = self.search([
            ('log_cleanup_enabled', '=', True),
            ('log_retention_days', '>', 0),
        ])
        for feed in feeds:
            try:
                feed._cleanup_old_logs()
            except Exception as exc:
                _logger.error("Fruugo Feed '%s' log cleanup failed: %s", feed.name, exc)

    def _cleanup_old_logs(self):
        """Delete old logs based on retention setting.

        Note: deleting log records also deletes their linked attachments through
        Odoo's standard attachment cleanup for res_model/res_id.
        """
        self.ensure_one()
        retention_days = self.log_retention_days or 0
        if retention_days < 0:
            return 0

        cutoff_dt = fields.Datetime.now() - timedelta(days=retention_days)
        old_logs = self.env['fruugo.feed.log'].sudo().search([
            ('feed_id', '=', self.id),
            ('create_date', '<', cutoff_dt),
        ])
        if not old_logs:
            return 0

        removed_count = len(old_logs)
        old_logs.unlink()
        return removed_count

    # ── Core generation + logging ─────────────────────────────────────────────
    def _run_feed_generation(self, trigger='manual'):
        """Generate the Fruugo XML, attach it to a new log record."""
        self.ensure_one()
        t0 = time.time()
        status = 'success'
        message = ''
        product_count = 0
        file_size_kb = 0.0
        attachment = False

        try:
            xml_content, product_count = self._generate_xml_content()
            encoded = xml_content.encode('utf-8')
            file_size_kb = len(encoded) / 1024.0

            # Attach the XML to the log. Filename is ALWAYS 'fruugo_feed.xml'.
            attachment = self.env['ir.attachment'].sudo().create({
                'name': FEED_FILENAME,
                'type': 'binary',
                'datas': base64.b64encode(encoded),
                'mimetype': 'application/xml',
                'res_model': 'fruugo.feed',
                'res_id': self.id,
            })

            duration = time.time() - t0
            message = _('Generated %(count)d products in %(sec).1fs — file: %(file)s') % {
                'count': product_count,
                'sec': duration,
                'file': FEED_FILENAME,
            }
            self.write({'last_generated': fields.Datetime.now(), 'last_status': 'success'})

        except Exception as exc:
            status = 'error'
            message = str(exc)
            self.write({'last_status': 'error'})
            _logger.exception("Fruugo Feed '%s' generation error", self.name)

        finally:
            duration = time.time() - t0
            log = self.env['fruugo.feed.log'].sudo().create({
                'feed_id': self.id,
                'status': status,
                'message': message,
                'product_count': product_count,
                'file_size_kb': file_size_kb,
                'duration_seconds': duration,
                'trigger': trigger,
                'attachment_id': attachment.id if attachment else False,
            })
            # Re-link the attachment to the log record so it appears in its chatter / attachments
            if attachment:
                attachment.sudo().write({'res_model': 'fruugo.feed.log', 'res_id': log.id})

    # ── Feed Live Serving (called by HTTP controller) ─────────────────────────
    def _get_latest_xml(self):
        """Return the latest generated XML bytes for live serving via HTTP.

        If a cached attachment exists from the last successful generation, serve it.
        Otherwise generate on-the-fly (first request before any cron has run).
        """
        self.ensure_one()
        # Try to find the most recent successful log with an attachment
        last_log = self.env['fruugo.feed.log'].sudo().search(
            [('feed_id', '=', self.id), ('status', '=', 'success'), ('attachment_id', '!=', False)],
            order='create_date desc', limit=1,
        )
        if last_log and last_log.attachment_id:
            return base64.b64decode(last_log.attachment_id.datas)

        # On-the-fly fallback (no log yet)
        xml_content, _ = self._generate_xml_content()
        return xml_content.encode('utf-8')

    # ── Product query ─────────────────────────────────────────────────────────
    def _get_products(self):
        """Return product.template or product.product records based on config."""
        domain = []
        if self.product_domain:
            try:
                domain = eval(self.product_domain)  # noqa: S307
            except Exception:
                domain = []

        if self.include_variants:
            products = self.env['product.product'].search(domain)
        else:
            products = self.env['product.template'].search(domain)

        if self.max_products and self.max_products > 0:
            products = products[:self.max_products]
        return products

    # ── Stock helpers ─────────────────────────────────────────────────────────
    def _get_stock_qty(self, product):
        """Return integer on-hand quantity for the product, respecting location filter."""
        if not self.stock_location_ids:
            qty = getattr(product, 'free_qty', getattr(product, 'qty_available', 0)) or 0
            return int(max(0, qty))
        quant_domain = [
            ('location_id', 'in', self.stock_location_ids.ids),
            ('location_id.usage', '=', 'internal'),
        ]
        if self.include_variants:
            quant_domain.append(('product_id', '=', product.id))
        else:
            quant_domain.append(('product_id.product_tmpl_id', '=', product.id))
        quants = self.env['stock.quant'].sudo().search(quant_domain)
        qty = sum(quants.mapped('available_quantity'))
        return int(max(0, qty))

    def _get_stock_qty_map(self, products):
        """Return a batched quantity map in one query.

        The returned dict keys follow the current export mode:
        - include_variants=True  -> product.product ids
        - include_variants=False -> product.template ids
        """
        self.ensure_one()
        if not products:
            return {}

        quant_domain = [('location_id.usage', '=', 'internal')]
        if self.stock_location_ids:
            quant_domain.append(('location_id', 'in', self.stock_location_ids.ids))

        Quant = self.env['stock.quant'].sudo()

        if self.include_variants:
            product_ids = products.ids
            qty_map = {pid: 0 for pid in product_ids}
            rows = Quant._read_group(
                domain=quant_domain + [('product_id', 'in', product_ids)],
                groupby=['product_id'],
                aggregates=['available_quantity:sum'],
            )
            for product_rec, qty_sum in rows:
                if product_rec:
                    qty_map[product_rec.id] = int(max(0, qty_sum or 0))
            return qty_map

        # Template mode: aggregate by variant product, then roll-up to template
        template_ids = products.ids
        qty_map = {tid: 0 for tid in template_ids}
        rows = Quant._read_group(
            domain=quant_domain + [('product_id.product_tmpl_id', 'in', template_ids)],
            groupby=['product_id'],
            aggregates=['available_quantity:sum'],
        )
        product_ids = [product_rec.id for product_rec, _qty_sum in rows if product_rec]
        prod_to_tmpl = {
            prod.id: prod.product_tmpl_id.id
            for prod in self.env['product.product'].browse(product_ids)
        }
        for product_rec, qty_sum in rows:
            if not product_rec:
                continue
            tmpl_id = prod_to_tmpl.get(product_rec.id)
            if tmpl_id:
                qty_map[tmpl_id] += int(max(0, qty_sum or 0))
        return qty_map

    def _get_stock_status(self, qty, product):
        """Return Fruugo StockStatus string (INSTOCK / OUTOFSTOCK / NOTAVAILABLE)."""
        tmpl = product.product_tmpl_id if product._name == 'product.product' else product
        # If explicitly excluded or archived → NOTAVAILABLE
        if not tmpl.active or getattr(tmpl, 'fruugo_excluded', False):
            return 'NOTAVAILABLE'
        return 'INSTOCK' if qty > 0 else 'OUTOFSTOCK'

    # ── Pricing helpers ───────────────────────────────────────────────────────
    def _get_price(self, product):
        """Return (price_tag_name, price_value_str, vat_rate_str)."""
        # Determine base price
        if self.pricelist_id:
            pp = product if product._name == 'product.product' else (
                product.product_variant_id or product.product_variant_ids[:1]
            )
            price = self.pricelist_id._get_product_price(pp, 1.0) if pp else 0.0
        else:
            price = getattr(product, 'list_price', 0.0) or 0.0

        # Determine VAT rate from product taxes.
        # In some UIs the percentage widget stores "5%" as 0.05 internally.
        # Fruugo expects VATRate as plain percent (5), so normalize fallback.
        vat_rate_default = self.default_vat_rate or 0.0
        if 0 < abs(vat_rate_default) <= 1:
            vat_rate_default *= 100.0
        vat_rate = vat_rate_default
        taxes = getattr(product, 'taxes_id', False)
        if not taxes and product._name == 'product.product':
            taxes = product.product_tmpl_id.taxes_id
        if taxes:
            for tax in taxes:
                if tax.amount_type == 'percent' and tax.amount > 0:
                    vat_rate = tax.amount
                    break

        if self.price_include_vat:
            # Odoo list_price is always tax-exclusive.
            # Add VAT on top to produce the tax-inclusive value Fruugo needs.
            tag = 'NormalPriceWithVAT'
            price_incl = price * (1 + vat_rate / 100.0)
            return tag, '%.2f' % price_incl, '%.0f' % vat_rate
        else:
            tag = 'NormalPriceWithoutVAT'
            return tag, '%.2f' % price, '%.0f' % vat_rate

    # ── ID helpers ────────────────────────────────────────────────────────────
    def _get_product_id(self, product):
        """Return stable ProductId (same for all variants of a template)."""
        if product._name == 'product.product':
            tmpl = product.product_tmpl_id
        else:
            tmpl = product
        return tmpl.default_code or ('TMPL-%d' % tmpl.id)

    def _get_sku_id(self, product):
        """Return unique SkuId for each variant (or same as ProductId if no variants)."""
        if product._name == 'product.product':
            code = product.default_code
            if code:
                return code
            barcode = product.barcode
            if barcode:
                return barcode
            return 'VAR-%d' % product.id
        else:
            # Template mode: SkuId = ProductId
            return self._get_product_id(product)

    def _get_ean(self, product):
        """Return EAN/barcode or 'EXCEP' for manufacturer's own products."""
        tmpl = product.product_tmpl_id if product._name == 'product.product' else product
        if getattr(tmpl, 'fruugo_ean_exception', False):
            return 'EXCEP'
        # Try variant barcode first, then template barcode
        barcode = getattr(product, 'barcode', None) or getattr(tmpl, 'barcode', None)
        return barcode or ''

    def _get_image_url(self, product, index=1):
        """Build Odoo image CDN URL for the product."""
        base = (self.store_url or '').rstrip('/')
        if product._name == 'product.product':
            return '%s/web/image/product.product/%d/image_1920' % (base, product.id)
        return '%s/web/image/product.template/%d/image_1920' % (base, product.id)

    def _get_variant_attribute(self, product, attr_names):
        """Extract a variant attribute value by attribute name (case-insensitive)."""
        if product._name != 'product.product':
            return ''
        for ptav in product.product_template_attribute_value_ids:
            if (ptav.attribute_id.name or '').lower() in [n.lower() for n in attr_names]:
                return ptav.product_attribute_value_id.name or ''
        return ''

    def _get_fruugo_language_code(self):
        """Return Fruugo-compatible 2-letter language code.

        Odoo languages can be locale-like (e.g. en_US). Fruugo expects 2-letter
        data language codes. Fallback to 'en' for unsupported/unknown values.
        """
        self.ensure_one()
        raw_code = ((self.language_id.iso_code or '') if self.language_id else '').strip().lower()
        normalized = (raw_code.split('_')[0].split('-')[0] if raw_code else 'en')
        return normalized if normalized in FRUUGO_SUPPORTED_LANGUAGES else 'en'

    # ── XML builder ───────────────────────────────────────────────────────────
    def _generate_xml_content(self):
        """Generate the full Fruugo XML feed string.

        All translatable fields (name, description_sale, description,
        categ_id.name, attribute value names) are read in the language
        configured on the feed via ``with_context(lang=...)``.

        Returns (xml_str, product_count).
        """
        self.ensure_one()
        products = self._get_products()

        # Build qty_map first — it only needs IDs, no translatable field reads.
        qty_map = self._get_stock_qty_map(products)

        lang_code = self._get_fruugo_language_code()

        # Re-browse products in the feed's Odoo locale (e.g. 'fr_BE', 'de_DE').
        # From this point every ORM field read on product/tmpl/category/attribute
        # will automatically return the stored translation for that language.
        lang_odoo = self.language_id.code if self.language_id else (self.env.lang or 'en_US')
        products = products.with_context(lang=lang_odoo)

        currency_code = self.currency_id.name if self.currency_id else 'GBP'

        lines = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            '<Products>',
        ]

        for product in products:
            tmpl = product.product_tmpl_id if product._name == 'product.product' else product

            # Skip if excluded
            if getattr(tmpl, 'fruugo_excluded', False):
                continue

            # ── IDs ──────────────────────────────────────────────────────────
            product_id = self._get_product_id(product)
            sku_id = self._get_sku_id(product)
            ean = self._get_ean(product)

            # ── Brand & Category ─────────────────────────────────────────────
            brand = (
                getattr(tmpl, 'fruugo_brand', '') or
                tmpl.categ_id.name or ''
            )
            
            fruugo_cat = getattr(tmpl, 'fruugo_category_id', False)
            if not fruugo_cat:
                fruugo_cat = tmpl.categ_id.fruugo_category_id if hasattr(tmpl.categ_id, 'fruugo_category_id') else False
                
            category = fruugo_cat.name if fruugo_cat else ''

            # ── Images ───────────────────────────────────────────────────────
            image_url1 = self._get_image_url(product, 1)

            # ── Stock ────────────────────────────────────────────────────────
            # Keep current behavior: batched lookup with safe fallback.
            qty = qty_map.get(product.id)
            if qty is None:
                qty = self._get_stock_qty(product)
            stock_status = self._get_stock_status(qty, product)

            # ── Title & Description ───────────────────────────────────────────
            title = (product.name or tmpl.name or '').strip()
            if product._name == 'product.product':
                # For variants, append variant attributes to title if multi-variant template
                if tmpl.product_variant_count > 1:
                    attr_parts = [
                        ptav.product_attribute_value_id.name
                        for ptav in product.product_template_attribute_value_ids
                        if ptav.product_attribute_value_id.name
                    ]
                    if attr_parts:
                        title = '%s - %s' % (tmpl.name, ', '.join(attr_parts))
                else:
                    title = tmpl.name or ''

            description = (
                tmpl.description_sale or
                tmpl.description or
                tmpl.name or ''
            ).strip()

            # ── Price ─────────────────────────────────────────────────────────
            price_tag, price_val, vat_rate = self._get_price(product)

            # ── Variant Attributes ────────────────────────────────────────────
            attr_color = self._get_variant_attribute(product, ['color', 'colour', 'farbe', 'couleur', 'colore'])
            attr_size = self._get_variant_attribute(product, ['size', 'taille', 'größe', 'tamaño', 'dimensione'])

            # ── Weight (grams, no decimal, no unit) ───────────────────────────
            weight_g = ''
            weight_kg = getattr(product, 'weight', None) or getattr(tmpl, 'weight', None)
            if weight_kg and float(weight_kg) > 0:
                weight_g = str(int(float(weight_kg) * 1000))

            # ── Lead Time ─────────────────────────────────────────────────────
            lead_time = getattr(tmpl, 'fruugo_lead_time', 0) or 0

            # ── Country Restriction ───────────────────────────────────────────
            country_restriction = getattr(tmpl, 'fruugo_country_restriction', '') or ''

            # ── Build XML block ───────────────────────────────────────────────
            lines.append('  <Product>')
            lines.append('    <ProductId>%s</ProductId>' % escape(str(product_id)))
            lines.append('    <SkuId>%s</SkuId>' % escape(str(sku_id)))

            if ean:
                lines.append('    <EAN>%s</EAN>' % escape(str(ean)))

            if brand:
                lines.append('    <Brand>%s</Brand>' % escape(brand))

            if category:
                lines.append('    <Category>%s</Category>' % escape(category))

            lines.append('    <Imageurl1>%s</Imageurl1>' % escape(image_url1))
            lines.append('    <StockStatus>%s</StockStatus>' % stock_status)
            lines.append('    <StockQuantity>%d</StockQuantity>' % qty)
            lines.append('    <Title>%s</Title>' % escape(title[:500]))
            lines.append('    <Description>%s</Description>' % escape(description[:10000]))
            lines.append('    <%s>%s</%s>' % (price_tag, price_val, price_tag))
            lines.append('    <VATRate>%s</VATRate>' % vat_rate)

            if attr_color:
                lines.append('    <AttributeColor>%s</AttributeColor>' % escape(attr_color))

            if attr_size:
                lines.append('    <AttributeSize>%s</AttributeSize>' % escape(attr_size))

            if weight_g:
                lines.append('    <PackageWeight>%s</PackageWeight>' % weight_g)

            if lead_time and lead_time > 1:
                lines.append('    <LeadTime>%d</LeadTime>' % lead_time)

            if country_restriction:
                lines.append('    <Country>%s</Country>' % escape(country_restriction))

            # Language & Currency (recommended fields)
            lines.append('    <Language>%s</Language>' % escape(lang_code))
            lines.append('    <Currency>%s</Currency>' % escape(currency_code))

            lines.append('  </Product>')

        lines.append('</Products>')
        xml_str = '\n'.join(lines)
        # len(products) can change after skip; count <Product> blocks
        product_count = xml_str.count('<Product>')
        return xml_str, product_count
