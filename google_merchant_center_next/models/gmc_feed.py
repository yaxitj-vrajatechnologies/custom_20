# -*- coding: utf-8 -*-
import io
import time
import logging
from xml.etree import ElementTree as ET

from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class GMCFeed(models.Model):
    _name = "gmc.feed"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _description = "Google Merchant Center Feed"
    _rec_name = "name"
    _order = "name asc"

    # ── Identity ──────────────────────────────────────────────────────────────
    name = fields.Char(string="Feed Name", required=True)
    active = fields.Boolean(string="Active", default=True)
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("active", "Active"),
            ("paused", "Paused"),
        ],
        string="State",
        default="draft",
        tracking=True,
    )
    color = fields.Integer(string="Color")

    # ── Store / Target ─────────────────────────────────────────────────────────
    store_title = fields.Char(
        string="Store Title",
        required=True,
        default=lambda self: self.env.company.name,
        help="Shown as <title> inside the RSS feed channel.",
    )
    store_url = fields.Char(
        string="Store URL",
        required=True,
        default=lambda self: self.get_base_url(),
    )
    language_id = fields.Many2one(
        "res.lang",
        string="Language",
        default=lambda self: self.env.ref("base.lang_en", raise_if_not_found=False),
    )
    currency_id = fields.Many2one(
        "res.currency",
        string="Currency",
        default=lambda self: self.env.company.currency_id,
    )
    pricelist_id = fields.Many2one(
        "product.pricelist",
        string="Pricelist",
        help="If set, prices will be computed using this pricelist.",
    )

    # ── Feed Format ────────────────────────────────────────────────────────────
    remote_filename = fields.Char(
        string="Remote Filename",
        required=True,
        default="products_feed.xml",
        help="The filename that will be created/overwritten on the SFTP server.",
    )

    # ── Product Filter ─────────────────────────────────────────────────────────
    product_domain = fields.Char(
        string="Product Domain (Filter)",
        default="[('sale_ok', '=', True), ('is_published', '=', True)]",
        help=(
            "Odoo domain to filter which products are included. "
            "Leave blank to export all publishable products."
        ),
    )
    include_variants = fields.Boolean(
        string="Include Variants",
        default=True,
        help="When enabled, each product VARIANT is exported as a separate item.",
    )
    max_products = fields.Integer(
        string="Max Products",
        default=0,
        help="Limit to first N products. Set 0 for unlimited.",
    )
    stock_location_ids = fields.Many2many(
        "stock.location",
        "gmc_feed_stock_location_rel",
        "feed_id",
        "location_id",
        string="Stock Locations",
        domain="[('usage', '=', 'internal')]",
        help=(
            "Select one or more internal stock locations to calculate availability. "
            "The stock quantity will be the SUM of quantities across all selected locations. "
            "Leave empty to use the product's total quantity available (all locations)."
        ),
    )

    # ── SFTP ───────────────────────────────────────────────────────────────────
    use_global_sftp = fields.Boolean(
        string="Use Global SFTP Settings",
        default=True,
        help="If enabled, SFTP credentials from Settings → Google Merchant Center are used.",
    )
    sftp_host = fields.Char(string="SFTP Host", default="partnerupload.google.com")
    sftp_port = fields.Integer(string="SFTP Port", default=19321)
    sftp_username = fields.Char(string="SFTP Username")
    sftp_password = fields.Char(string="SFTP Password")

    # ── Columns ────────────────────────────────────────────────────────────────
    column_ids = fields.One2many(
        "gmc.feed.column",
        "feed_id",
        string="Feed Columns",
        copy=True,
        context={'active_test': False},
    )
    attribute_mapping_ids = fields.One2many(
        "gmc.feed.attribute.mapping",
        "feed_id",
        string="Attribute Mappings",
    )

    # ── Logs ───────────────────────────────────────────────────────────────────
    log_ids = fields.One2many(
        "gmc.feed.log",
        "feed_id",
        string="Upload Logs",
    )
    last_sync = fields.Datetime(string="Last Sync", readonly=True)
    last_status = fields.Selection(
        [("success", "Success"), ("error", "Error"), ("warning", "Warning")],
        string="Last Status",
        readonly=True,
    )

    # ── Statistics ─────────────────────────────────────────────────────────────
    log_count = fields.Integer(
        string="Logs", compute="_compute_log_count"
    )

    def _compute_log_count(self):
        for rec in self:
            rec.log_count = self.env["gmc.feed.log"].search_count([("feed_id", "=", rec.id)])

    @api.model_create_multi
    def create(self, vals_list):
        feeds = super().create(vals_list)
        default_feed = self.env.ref("google_merchant_center_next.gmc_feed_default", raise_if_not_found=False)
        if default_feed and default_feed.column_ids:
            for feed in feeds:
                # Avoid copying onto the default feed itself during its creation/update
                if feed.id != default_feed.id and not feed.column_ids:
                    for col in default_feed.column_ids:
                        col.copy({'feed_id': feed.id})
        return feeds

    # ── Actions ────────────────────────────────────────────────────────────────
    def action_activate(self):
        self.write({"state": "active"})

    def action_pause(self):
        self.write({"state": "paused"})

    def action_reset_draft(self):
        self.write({"state": "draft"})

    def action_view_logs(self):
        self.ensure_one()
        return {
            "name": _("Feed Logs – %s") % self.name,
            "type": "ir.actions.act_window",
            "res_model": "gmc.feed.log",
            "view_mode": "list,form",
            "domain": [("feed_id", "=", self.id)],
        }

    def action_upload_now(self):
        """Manual trigger: generate feed and upload via SFTP."""
        self.ensure_one()
        warnings_count = self._run_feed_upload(trigger="manual")
        if warnings_count:
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": _("Feed Uploaded with Warnings"),
                    "message": _(
                        "Feed '%s' uploaded successfully, but %d required field issue(s) were detected. "
                        "Check the Sync Logs tab for details."
                    ) % (self.name, warnings_count),
                    "type": "warning",
                    "sticky": True,
                },
            }
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Feed Upload"),
                "message": _("Feed '%s' uploaded successfully!") % self.name,
                "type": "success",
                "sticky": False,
            },
        }

    def action_preview_feed(self):
        """Open feed preview wizard."""
        self.ensure_one()
        content, _count, _warnings = self._generate_feed_content(preview_limit=0)
        preview = self.env["gmc.feed.preview.wizard"].create({
            "feed_id": self.id,
            "content": content,
        })
        return {
            "name": _("Feed Preview – %s") % self.name,
            "type": "ir.actions.act_window",
            "res_model": "gmc.feed.preview.wizard",
            "res_id": preview.id,
            "view_mode": "form",
            "target": "new",
        }

    @api.model
    def _get_hardcoded_default_column_specs(self):
        """Fallback default columns used when XML/template data is missing."""
        return [
            {"sequence": 10, "name": "ID", "column_key": "g:id", "field_name": "default_code", "is_required": True,
             "notes": "Product Internal Reference (default_code). Change to 'id' to use system ID."},
            {"sequence": 20, "name": "Title", "column_key": "title", "field_name": "name", "is_required": True},
            {"sequence": 30, "name": "Description", "column_key": "description", "field_name": "description_sale", "is_required": True},
            {"sequence": 40, "name": "Link", "column_key": "link", "is_required": True},
            {"sequence": 50, "name": "Image Link", "column_key": "g:image_link", "field_name": "image_1920", "is_required": True},
            {"sequence": 60, "name": "Availability", "column_key": "g:availability", "field_name": "qty_available", "is_required": True},
            {"sequence": 70, "name": "Price", "column_key": "g:price", "field_name": "list_price", "is_required": True},
            {"sequence": 80, "name": "Condition", "column_key": "g:condition", "static_value": "new", "is_required": True},
            {"sequence": 90, "name": "Brand", "column_key": "g:brand", "field_name": "brand_id"},
            {"sequence": 100, "name": "GTIN", "column_key": "g:gtin", "field_name": "barcode"},
            {"sequence": 110, "name": "MPN", "column_key": "g:mpn", "field_name": "default_code"},
            {"sequence": 120, "name": "Google Product Category", "column_key": "g:google_product_category", "field_name": "google_product_category_id"},
            {"sequence": 130, "name": "Product Type", "column_key": "g:product_type", "field_name": "categ_id"},
            {"sequence": 140, "name": "Custom Label 0", "column_key": "g:custom_label_0"},
        ]

    @api.model
    def _find_product_field_for_default_column(self, field_name):
        if not field_name:
            return False
        return self.env["ir.model.fields"].sudo().search(
            [
                ("model", "in", ["product.template", "product.product"]),
                ("name", "=", field_name),
            ],
            limit=1,
        )

    def _create_hardcoded_default_columns(self, target_feed):
        """Create fallback defaults directly on a feed."""
        self.ensure_one()
        target_feed.ensure_one()
        column_model = self.env["gmc.feed.column"].sudo()
        for spec in self._get_hardcoded_default_column_specs():
            field = self._find_product_field_for_default_column(spec.get("field_name"))
            vals = {
                "feed_id": target_feed.id,
                "sequence": spec.get("sequence", 10),
                "name": spec["name"],
                "column_key": spec["column_key"],
                "is_required": bool(spec.get("is_required")),
                "static_value": spec.get("static_value", False),
                "notes": spec.get("notes", False),
            }
            if field:
                vals["field_id"] = field.id
            column_model.create(vals)

    def _ensure_default_feed_has_full_columns(self, default_feed):
        """Top up missing default columns on template feed."""
        self.ensure_one()
        default_feed.ensure_one()
        expected_specs = self._get_hardcoded_default_column_specs()
        existing_keys = {
            (c.column_key, c.custom_column_key or "")
            for c in default_feed.column_ids
        }
        to_create = []
        for spec in expected_specs:
            spec_key = (spec["column_key"], spec.get("custom_column_key", "") or "")
            if spec_key not in existing_keys:
                to_create.append(spec)

        if not to_create:
            return

        column_model = self.env["gmc.feed.column"].sudo()
        for spec in to_create:
            field = self._find_product_field_for_default_column(spec.get("field_name"))
            vals = {
                "feed_id": default_feed.id,
                "sequence": spec.get("sequence", 10),
                "name": spec["name"],
                "column_key": spec["column_key"],
                "custom_column_key": spec.get("custom_column_key", False),
                "is_required": bool(spec.get("is_required")),
                "static_value": spec.get("static_value", False),
                "notes": spec.get("notes", False),
            }
            if field:
                vals["field_id"] = field.id
            column_model.create(vals)

    def action_load_default_columns(self):
        self.ensure_one()
        default_feed = self.env.ref("google_merchant_center_next.gmc_feed_default", raise_if_not_found=False)
        if not default_feed:
            raise UserError(
                _("Default feed template is missing. Please upgrade the module to reload demo/default data.")
            )

        default_columns = default_feed.column_ids
        # Self-heal: if template feed has no linked columns, recover them via XML IDs.
        if not default_columns:
            xml_default_columns = []
            for xmlid in [
                "google_merchant_center_next.gmc_column_id",
                "google_merchant_center_next.gmc_column_title",
                "google_merchant_center_next.gmc_column_description",
                "google_merchant_center_next.gmc_column_link",
                "google_merchant_center_next.gmc_column_image_link",
                "google_merchant_center_next.gmc_column_availability",
                "google_merchant_center_next.gmc_column_price",
                "google_merchant_center_next.gmc_column_condition",
                "google_merchant_center_next.gmc_column_brand",
                "google_merchant_center_next.gmc_column_gtin",
                "google_merchant_center_next.gmc_column_mpn",
                "google_merchant_center_next.gmc_column_google_product_category",
                "google_merchant_center_next.gmc_column_product_type",
                "google_merchant_center_next.gmc_column_custom_label_0",
            ]:
                col = self.env.ref(xmlid, raise_if_not_found=False)
                if col and col._name == "gmc.feed.column":
                    xml_default_columns.append(col)

            # Re-link or clone XML default columns to the default feed.
            for col in xml_default_columns:
                if col.feed_id != default_feed:
                    if not col.feed_id:
                        col.sudo().write({"feed_id": default_feed.id})
                    else:
                        col.sudo().copy({"feed_id": default_feed.id})
            default_columns = default_feed.column_ids

        # Last fallback: build defaults at runtime so button works without upgrade.
        if not default_columns:
            self._create_hardcoded_default_columns(default_feed)
            default_columns = default_feed.column_ids

        # If template exists but is incomplete, top up missing default columns.
        self._ensure_default_feed_has_full_columns(default_feed)
        default_columns = default_feed.column_ids

        if not default_columns:
            return {"type": "ir.actions.client", "tag": "reload"}

        added = 0
        skipped = 0
        for col in default_columns:
            # Use (column_key, custom_column_key) as uniqueness criterion.
            existing = self.column_ids.filtered(
                lambda c: c.column_key == col.column_key
                and (c.custom_column_key or "") == (col.custom_column_key or "")
            )
            if existing:
                skipped += 1
                continue
            # Load defaults even for non-admin users who can access this screen.
            col.sudo().copy({'feed_id': self.id})
            added += 1

        return {"type": "ir.actions.client", "tag": "reload"}

    # ── Cron entry point ───────────────────────────────────────────────────────
    def run_scheduled_feed_upload(self):
        """Called by ir.cron. Uploads all active feeds."""
        active_feeds = self.search([("state", "=", "active")])
        for feed in active_feeds:
            try:
                feed._run_feed_upload(trigger="scheduled")
            except Exception as exc:
                _logger.error("GMC Feed '%s' scheduled upload failed: %s", feed.name, exc)

    # ── Core feed generation + upload ─────────────────────────────────────────
    def _run_feed_upload(self, trigger="manual"):
        """Generate feed content and upload via SFTP. Writes a log.

        Returns the number of required-field warnings found (0 = clean upload).
        """
        self.ensure_one()
        t0 = time.time()
        status = "success"
        message = ""
        product_count = 0
        file_size_kb = 0.0
        warnings = {}       # {"Column Label (g:tag)": ["Product A", "Product B", ...]}
        warnings_text = ""  # Formatted string stored in the log

        try:
            content, product_count, warnings = self._generate_feed_content()
            encoded = content.encode("utf-8")
            file_size_kb = len(encoded) / 1024.0

            self._upload_via_sftp(encoded, self.remote_filename)

            if warnings:
                warnings_text = self._format_warnings_text(warnings)
                status = "warning"
                self.write({"last_sync": fields.Datetime.now(), "last_status": "warning"})
            else:
                self.write({"last_sync": fields.Datetime.now(), "last_status": "success"})

        except Exception as exc:
            status = "error"
            message = str(exc)
            self.write({"last_status": "error"})
            _logger.exception("GMC Feed '%s' upload error", self.name)
            raise UserError(_("Feed upload failed:\n%s") % exc)

        finally:
            duration = time.time() - t0
            issues = sum(len(v) for v in warnings.values())
            self.env["gmc.feed.log"].sudo().create({
                "feed_id": self.id,
                "remote_filename": self.remote_filename,
                "status": status,
                "message": message or _(
                    "Uploaded %(count)d products in %(sec).1fs%(warn)s"
                ) % {
                    "count": product_count,
                    "sec": duration,
                    "warn": _(" — %d required-field issue(s) detected. See below.") % issues if issues else "",
                },
                "warnings_text": warnings_text or False,
                "product_count": product_count,
                "file_size_kb": file_size_kb,
                "duration_seconds": duration,
                "trigger": trigger,
            })

        return sum(len(v) for v in warnings.values())

    # ── Feed content builder ───────────────────────────────────────────────────

    def _get_products(self, preview_limit=0):
        """Return product.template or product.product recordset based on config."""
        domain = []
        if self.product_domain:
            try:
                domain = eval(self.product_domain)  # noqa: S307
            except Exception:
                domain = []

        if self.include_variants:
            products = self.env["product.product"].search(domain)
        else:
            products = self.env["product.template"].search(domain)

        limit = preview_limit or (self.max_products if self.max_products > 0 else 0)
        if limit:
            products = products[:limit]
        return products

    # ── Variant attribute resolution helpers ─────────────────────────────────

    @staticmethod
    def _get_variant_attribute_value(product, attribute_names):
        """Return the first matching attribute value string for a product.product.

        attribute_names is a list of attribute names to search (case-insensitive),
        e.g. ['Color', 'Colour'] for g:color. Returns empty string if not found
        or if the product is not a product.product variant.
        """
        if product._name != 'product.product':
            return ""
        for ptav in product.product_template_attribute_value_ids:
            attr_name = ptav.attribute_id.name or ""
            if attr_name.lower() in [n.lower() for n in attribute_names]:
                return ptav.product_attribute_value_id.name or ""
        return ""

    @staticmethod
    def _is_true_variant(product):
        """Return True only when the product belongs to a template with 2+ active variants.

        Google's spec explicitly states: do NOT submit item_group_id for products
        that are not part of a variant group. A product.product whose parent
        template has product_variant_count == 1 is effectively a standalone
        product and must be treated accordingly.
        """
        if product._name != 'product.product':
            return False
        return (product.product_tmpl_id.product_variant_count or 0) > 1

    def _get_variant_google_tags(self, product):
        """Return an ordered list of (g:tag, value) pairs derived from the
        product.product's attribute combination.

        Google requires at least ONE variant attribute tag (g:color, g:size,
        g:material, g:pattern, g:age_group or g:gender) alongside every
        g:item_group_id. This helper auto-maps Odoo attribute names to the
        correct Google tag so the feed builder can inject them automatically
        without the user having to add individual columns.

        Comprehensive mapping rules
        ──────────────────────────
        • Exact / well-known names are mapped precisely.
        • Fabric, textile, cloth, leather, wood, finish → g:material
        • Height, width, length, depth, dimension → g:size  (Google
          accepts these for furniture / hardware variant grouping)
        • Any attribute with NO standard Google tag falls back to g:size
          if free, so Google can still distinguish items in the group.

        Returns a list of (tag, value) tuples (not a dict) to preserve
        insertion order — most specific tag first.
        """
        if product._name != 'product.product':
            return []

        # Map lowercase attribute name → Google XML tag.
        ATTR_TO_GOOGLE = {
            # ── Color ────────────────────────────────────────────────────
            'color': 'g:color', 'colour': 'g:color',
            'farbe': 'g:color', 'couleur': 'g:color', 'colore': 'g:color',
            'kleur': 'g:color', 'cor': 'g:color',
            # ── Material / fabric ─────────────────────────────────────────
            'material': 'g:material', 'fabric': 'g:material',
            'textile': 'g:material', 'cloth': 'g:material',
            'tissue': 'g:material', 'stoffe': 'g:material',
            'matériau': 'g:material', 'materiale': 'g:material',
            'leather': 'g:material', 'wood': 'g:material',
            'metal': 'g:material', 'upholstery': 'g:material',
            'finish': 'g:material',
            # ── Size / dimensions ─────────────────────────────────────────
            'size': 'g:size', 'taille': 'g:size', 'größe': 'g:size',
            'tamaño': 'g:size', 'dimensione': 'g:size',
            'height': 'g:size', 'hoogte': 'g:size', 'hauteur': 'g:size',
            'width': 'g:size', 'breedte': 'g:size', 'largeur': 'g:size',
            'length': 'g:size', 'lengte': 'g:size', 'longueur': 'g:size',
            'depth': 'g:size', 'diepte': 'g:size', 'profondeur': 'g:size',
            'dimension': 'g:size', 'dimensions': 'g:size',
            'capacity': 'g:size', 'measurement': 'g:size',
            # ── Pattern ───────────────────────────────────────────────────
            'pattern': 'g:pattern', 'design': 'g:pattern',
            'motif': 'g:pattern', 'muster': 'g:pattern',
            'print': 'g:pattern',
            # ── Age group ─────────────────────────────────────────────────
            'age group': 'g:age_group', 'age_group': 'g:age_group',
            'age': 'g:age_group',
            # ── Gender ────────────────────────────────────────────────────
            'gender': 'g:gender', 'sex': 'g:gender',
            'geschlecht': 'g:gender', 'genre': 'g:gender',
        }

        result = []        # ordered (tag, value) pairs
        used_tags = set()  # prevent duplicate Google tags
        unmatched = []     # (attr_name, value) with no standard match

        # Build dict for fast lookup of mappings for this feed
        custom_mappings = {m.attribute_id.id: m for m in self.attribute_mapping_ids}

        for ptav in product.product_template_attribute_value_ids:
            attr_id = ptav.attribute_id.id
            attr_name = (ptav.attribute_id.name or '').strip()
            attr_val = (ptav.product_attribute_value_id.name or '').strip()
            if not attr_val:
                continue

            mapping = custom_mappings.get(attr_id)
            if mapping:
                if mapping.gmc_tag == 'ignore':
                    continue
                tag = mapping.custom_tag if mapping.gmc_tag == 'custom' else mapping.gmc_tag
                if tag and tag not in used_tags:
                    result.append((tag, attr_val))
                    used_tags.add(tag)
                continue

            g_tag = ATTR_TO_GOOGLE.get(attr_name.lower())
            if g_tag and g_tag not in used_tags:
                result.append((g_tag, attr_val))
                used_tags.add(g_tag)
            elif not g_tag:
                unmatched.append((attr_name, attr_val))

        # Fallback: use the first unmatched attribute for g:size so Google
        # can still distinguish variants whose axis names are non-standard
        # (e.g. 'Legs', 'Frame', 'Configuration').
        if unmatched and 'g:size' not in used_tags:
            result.append(('g:size', unmatched[0][1]))

        return result

    def _get_item_group_id(self, product):
        """Return a stable, unique item_group_id for a variant's parent template.

        Priority: template's default_code → template's barcode → 'TMPL-{id}'.
        This value is the same for ALL variants of the same product template,
        which is exactly what Google requires to group them.

        Call this ONLY after confirming _is_true_variant(product) is True.
        """
        tmpl = product.product_tmpl_id if product._name == 'product.product' else product
        code = getattr(tmpl, 'default_code', False)
        if code:
            return str(code)[:50]
        barcode = getattr(tmpl, 'barcode', False)
        if barcode:
            return str(barcode)[:50]
        return "TMPL-%d" % tmpl.id

    def _get_variant_id(self, product):
        """Return a unique, stable g:id for a product.product variant.

        Priority:
          1. Variant's own default_code (internal reference set on the variant)
          2. Template default_code + variant attribute values (e.g. SKU001-Red-L)
          3. Variant's own barcode
          4. 'VAR-{variant.id}' — guaranteed unique numeric fallback

        This MUST be unique per variant so Google does not overwrite one variant
        with another belonging to the same template.
        """
        # 1. Variant has its own SKU — best case
        code = getattr(product, 'default_code', False)
        if code:
            return str(code)[:50]

        # 2. Build composite: template_code + attribute combination string
        tmpl = product.product_tmpl_id
        tmpl_code = getattr(tmpl, 'default_code', False) or ""
        attr_parts = []
        for ptav in product.product_template_attribute_value_ids.sorted('attribute_id'):
            val = ptav.product_attribute_value_id.name
            if val:
                attr_parts.append(val)
        if tmpl_code and attr_parts:
            composite = "%s-%s" % (tmpl_code, "-".join(attr_parts))
            return composite[:50]

        # 3. Variant barcode
        barcode = getattr(product, 'barcode', False)
        if barcode:
            return str(barcode)[:50]

        # 4. Numeric fallback — always unique
        return "VAR-%d" % product.id

    def _get_stock_quantity(self, product):
        """Return the available quantity for the specified stock locations, or globally."""
        if not self.stock_location_ids:
            # Fallback to all locations. Use free_qty (equivalent to available_quantity)
            # or qty_available as fallback.
            qty = getattr(product, "free_qty", getattr(product, "qty_available", 0)) or 0
            return int(max(0, qty))
        quant_domain = [
            ("location_id", "in", self.stock_location_ids.ids),
            ("location_id.usage", "=", "internal"),
        ]
        if self.include_variants:
            quant_domain.append(("product_id", "=", product.id))
        else:
            quant_domain.append(("product_id.product_tmpl_id", "=", product.id))
        quants = self.env["stock.quant"].sudo().search(quant_domain)
        # Use available_quantity — Odoo 19 stock.quant computed field
        # equals (quantity - reserved_quantity), matching the Inventory UI.
        qty = sum(quants.mapped("available_quantity"))
        return int(max(0, qty))

    def _resolve_column_value(self, col, product):
        """Resolve a single column value for a product record."""
        tag = col.custom_column_key if col.column_key == 'custom' else col.column_key

        # 1. Special Computed Cases (Standard Google Tags)

        # ── g:id — Primary key. MUST be unique per variant so Google does not
        # merge or overwrite sibling variants of the same template.
        if tag == 'g:id':
            if col.field_id:
                val = getattr(product, col.field_id.name, False)
                if val:
                    return str(val)[:50]  # GMC enforces 50-char max
            # In variants mode use a dedicated helper that guarantees per-variant
            # uniqueness even when default_code is not set on the variant itself.
            if self.include_variants and product._name == 'product.product':
                return self._get_variant_id(product)
            # Template mode: default_code → barcode → 'ODOO-{id}'
            code = getattr(product, 'default_code', False)
            if code:
                return str(code)[:50]
            barcode = getattr(product, 'barcode', False)
            if barcode:
                return str(barcode)[:50]
            return "ODOO-%d" % product.id

        # Image URLs
        if tag in ('g:image_link', 'g:additional_image_link', 'g:lifestyle_image_link'):
            field_name = col.field_id.name if col.field_id else 'image_1920'
            base = self.store_url.rstrip("/")
            if self.include_variants:
                return "%s/web/image/product.product/%d/%s" % (base, product.id, field_name)
            return "%s/web/image/product.template/%d/%s" % (base, product.id, field_name)

        # Product URLs — for variants, append attribute query params so Google
        # lands on the correct variant page (required per GMC best practices).
        if tag in ('link', 'g:mobile_link'):
            base = self.store_url.rstrip("/")
            url = ""

            # 1. Grab URL from mapped field if any
            if col.field_id:
                val = getattr(product, col.field_id.name, False)
                if val:
                    url = str(val)

            # 2. Fallback to native website_url or slug
            if not url:
                website_url = getattr(product, "website_url", None)
                if website_url:
                    url = website_url
                else:
                    slug = getattr(product, "default_code", None) or str(product.id)
                    url = "/shop/%s" % slug

            # 3. Enforce the feed's store_url domain on the URL to prevent GMC Mismatched Domain errors
            if url.startswith('/'):
                url = "%s%s" % (base, url)
            elif url.startswith('http'):
                from urllib.parse import urlparse, urlunparse
                vp = urlparse(url)
                bp = urlparse(base)
                url = urlunparse((bp.scheme, bp.netloc, vp.path, vp.params, vp.query, vp.fragment))
            else:
                url = "%s/%s" % (base, url)

            # 4. Variant fallback parameter
            if self.include_variants and product._name == 'product.product' and '?' not in url:
                url = "%s?product_id=%d" % (url, product.id)

            return url

        # Pricing
        if tag in ('g:price', 'g:sale_price'):
            price = 0.0
            if self.pricelist_id:
                # Pricelist always takes priority when configured.
                # _get_product_price requires a product.product, so resolve the
                # first variant when working with a product.template.
                pricelist_product = product
                if product._name == 'product.template':
                    pricelist_product = product.product_variant_id or product.product_variant_ids[:1]
                if pricelist_product:
                    price = self.pricelist_id._get_product_price(pricelist_product, 1.0)
                else:
                    price = getattr(product, "list_price", 0.0) or 0.0
            elif col.field_id:
                # No pricelist — use the explicitly mapped field (e.g. list_price, taxes_id, etc.)
                price = getattr(product, col.field_id.name, 0.0) or 0.0
            else:
                # Ultimate fallback: sales price
                price = getattr(product, "list_price", 0.0) or 0.0
            currency = self.currency_id.name if self.currency_id else "USD"
            # Google disapproves items with a price of 0. Return an empty string
            # so the required-field warning system surfaces this as a data issue
            # rather than uploading a feed Google will silently reject.
            if price <= 0.0:
                return ""
            return "%.2f %s" % (price, currency)

        # Availability
        if tag == 'g:availability':
            # stock_location_ids always take priority when configured —
            # they override col.field_id to ensure filtered-location stock
            # is used (same priority pattern as pricelist for g:price).
            if self.stock_location_ids:
                qty = self._get_stock_quantity(product)
                return "in_stock" if qty > 0 else "out_of_stock"
            # No location filter — use col.field_id if set
            if col.field_id:
                val = getattr(product, col.field_id.name, 0)
                if isinstance(val, (int, float)):
                    return "in_stock" if float(val) > 0 else "out_of_stock"
                if val:
                    return str(val)
            # Ultimate fallback: product's total qty_available (all locations)
            qty = getattr(product, "qty_available", 0) or 0
            return "in_stock" if qty > 0 else "out_of_stock"

        # ── g:item_group_id ──────────────────────────────────────────────────
        # Google uses this to group all variants of the same product together.
        # ALL variants of the same template MUST share the same item_group_id
        # value. It must NOT appear for non-variant products.
        if tag == 'g:item_group_id':
            # If a model field is explicitly mapped, honour it first.
            if col.field_id:
                val = getattr(product, col.field_id.name, False)
                if val:
                    return str(val)[:50]
            if self.include_variants and self._is_true_variant(product):
                # Derive from the parent template — same for all siblings.
                # Only emitted for products that genuinely belong to a variant
                # group (template has 2+ variants). Google rejects item_group_id
                # on standalone single-variant products.
                return self._get_item_group_id(product)
            # Static value fallback (template mode or user-defined static)
            return str(col.static_value or "")

        # ── Variant attribute tags ───────────────────────────────────────────
        # When include_variants=True these tags are resolved from Odoo's
        # product.template.attribute.value records so Google receives the
        # actual variant-differentiating data it needs to display swatches.
        _VARIANT_ATTR_MAP = {
            'g:color':     ['color', 'colour'],
            'g:size':      ['size'],
            'g:material':  ['material'],
            'g:pattern':   ['pattern'],
            'g:age_group': ['age group', 'age_group', 'age'],
            'g:gender':    ['gender'],
        }
        if tag in _VARIANT_ATTR_MAP and self.include_variants:
            # Try to read the value from the variant's attribute combination first.
            attr_val = self._get_variant_attribute_value(product, _VARIANT_ATTR_MAP[tag])
            if attr_val:
                return attr_val
            # Fall through to the standard field/static resolution below so the
            # user can still override via a mapped field or static value.

        # Special Google Taxonomy Category ID
        # Handles BOTH cases:
        #   (a) No field_id mapped → resolve taxonomy ID from the product's
        #       google_product_category_id field automatically.
        #   (b) field_id IS mapped → fall through to the generic resolver below,
        #       but guard against an empty recordset returning 'google.product.taxonomy()'
        #       instead of a proper empty string.
        if tag == 'g:google_product_category':
            tmpl = (
                product
                if product._name == 'product.template'
                else getattr(product, "product_tmpl_id", product)
            )
            cat = getattr(tmpl, "google_product_category_id", False)
            if not col.field_id:
                # Auto-resolve: emit the numeric Google taxonomy ID
                if cat and cat.ids:  # non-empty recordset
                    return str(cat.google_id)
                return ""
            else:
                # User mapped a field — honour it, but make sure an empty
                # recordset renders as "" and not as 'model.name()'
                val = getattr(tmpl, col.field_id.name, False)
                if val and hasattr(val, '_name'):
                    # Relational: try google_id, then complete_name, then name
                    gid = getattr(val, 'google_id', None)
                    if gid:
                        return str(gid)
                    if hasattr(val, 'complete_name') and val.complete_name:
                        return val.complete_name
                    if hasattr(val, 'name') and val.name:
                        return val.name
                    return ""
                if val:
                    return str(val)
                return ""

        # 2. Extract from selected Model Field
        value = False
        if col.field_id:
            value = getattr(product, col.field_id.name, False)
            if value and hasattr(value, "_name"):  # it's a relational field
                if hasattr(value, 'complete_name'):
                    value = value.complete_name
                elif hasattr(value, 'name'):
                    value = value.name
                else:
                    value = value.display_name

        # 3. Fallback to static value
        if value is False or value is None or value == "":
            value = col.static_value or ""

        value = str(value)

        # Enforce Google's per-tag character limits on the final value.
        # Google will truncate or disapprove items that exceed these limits.
        #   title       → max 150 characters  (spec: Title [title])
        #   description → max 5000 characters (spec: Description [description])
        if tag == 'title':
            value = value[:150]
        elif tag == 'description':
            value = value[:5000]

        return value

    def _generate_feed_content(self, preview_limit=0):
        """Return (feed_string, product_count, warnings_dict).

        All translatable fields (name, description_sale, categ_id.name,
        attribute value names, etc.) are read in the language configured on
        the feed via ``with_context(lang=...)``.

        warnings_dict is {"Column Label (g:tag)": [product_name, ...]} and is
        non-empty only when a required column resolves to an empty value for one
        or more products.  The feed is always generated in full regardless.
        """
        self.ensure_one()
        products = self._get_products(preview_limit=preview_limit)
        # product_count uses only IDs — compute before the context switch.
        product_count = len(products)

        # Re-browse products in the feed's Odoo locale (e.g. 'fr_BE', 'de_DE').
        # From this point every getattr(product, field_name) call inside
        # _resolve_column_value will automatically return the stored translation
        # for that language — title, description, categ_id.name, attribute
        # value names, etc. — without changing any resolution logic.
        lang_odoo = self.language_id.code if self.language_id else (self.env.lang or 'en_US')
        products = products.with_context(lang=lang_odoo)

        columns = self.column_ids.filtered(lambda c: c.active).sorted("sequence")

        content, warnings = self._build_xml_feed(products, columns)
        return content, product_count, warnings

    def _build_xml_feed(self, products, columns):
        """Build RSS/XML feed (Google Merchant Center compatible).

        Returns (xml_string, warnings_dict) where warnings_dict is:
            {"Column Label (g:tag)": [product_display_name, ...]}
        It is collected as a zero-cost by-product of the normal render loop —
        no second pass, no extra DB queries.
        """
        # Pre-filter required columns once — avoids re-checking every cell
        required_keys = {
            col: "%s (%s)" % (
                col.name,
                col.custom_column_key if col.column_key == 'custom' else col.column_key,
            )
            for col in columns
            if col.is_required
        }
        warnings = {}  # {label_with_tag: [product_name, ...]}

        lines = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            '<rss version="2.0" xmlns:g="http://base.google.com/ns/1.0">',
            "  <channel>",
            "    <title>%s</title>" % self._escape(self.store_title),
            "    <link>%s</link>" % self._escape(self.store_url),
            "    <description>Product feed generated by Odoo GMC Integration</description>",
        ]

        # Determine whether a g:item_group_id column is already configured by
        # the user. If not and variants mode is on, we auto-inject the tag so
        # Google always receives the grouping signal it needs.
        # Pre-compute the set of tags already covered by explicit user columns.
        # Auto-injection below skips any tag already present to avoid duplicates.
        configured_tags = {
            c.custom_column_key if c.column_key == 'custom' else c.column_key
            for c in columns
        }
        has_item_group_col = 'g:item_group_id' in configured_tags

        for product in products:
            lines.append("    <item>")
            for col in columns:
                value = self._resolve_column_value(col, product)
                tag = col.custom_column_key if col.column_key == 'custom' else col.column_key
                lines.append("      <%s>%s</%s>" % (tag, self._escape(value), tag))

                # Collect warning if this is a required column with an empty result
                if col in required_keys and (not value or not value.strip()):
                    label = required_keys[col]
                    product_name = product.display_name or str(product.id)
                    warnings.setdefault(label, []).append(product_name)

            if self.include_variants and self._is_true_variant(product):
                # ── Auto-inject g:item_group_id ──────────────────────────────
                # Google REQUIRES this to group variants. Only inject if the
                # user hasn't added an explicit column for it.
                if not has_item_group_col:
                    group_id = self._get_item_group_id(product)
                    lines.append(
                        "      <g:item_group_id>%s</g:item_group_id>" % self._escape(group_id)
                    )

                # ── Auto-inject variant attribute tags ───────────────────────
                # Google REQUIRES at least one of g:color / g:size / g:material
                # / g:pattern / g:age_group / g:gender alongside every
                # g:item_group_id so it knows HOW the variants differ.
                # _get_variant_google_tags() maps Odoo attribute names to the
                # correct Google tag automatically (Fabric→material,
                # Height→size, Color→color, etc.). Tags the user has already
                # configured as explicit columns are skipped to avoid duplicates.
                for g_tag, attr_value in self._get_variant_google_tags(product):
                    if g_tag not in configured_tags:
                        lines.append(
                            "      <%s>%s</%s>" % (g_tag, self._escape(attr_value), g_tag)
                        )

            if 'g:quantity' not in configured_tags:
                qty = self._get_stock_quantity(product)
                lines.append("      <g:quantity>%d</g:quantity>" % qty)

            lines.append("    </item>")

        lines += ["  </channel>", "</rss>"]
        return "\n".join(lines), warnings

    @staticmethod
    def _format_warnings_text(warnings):
        """Format the warnings dict into a structured, human-readable report for the log.

        Input:
            warnings = {
                "Description (description)": ["Product A", "Product B"],
                "Brand (g:brand)": ["Product C"],
            }

        Output example:
            ╔══════════════════════════════════════════════════════════════╗
            ║        ⚠️  GMC FEED — REQUIRED FIELDS REPORT               ║
            ╚══════════════════════════════════════════════════════════════╝

            Summary
            ───────────────────────────────────────────────────────────────
            • Fields with missing values : 2
            • Unique products affected   : 3
            • Total missing cells        : 3
            ───────────────────────────────────────────────────────────────

            [1/2] Description (description)  — 2 product(s) affected
            ─────────────────────────────────────────────────────
              • Acoustic Bloc Screens
              • Customizable Desk (White, Steel)

            [2/2] Brand (g:brand)  — 1 product(s) affected
            ─────────────────────────────────────────────────────
              • Large Cabinet

            ───────────────────────────────────────────────────────────────
            ⚡ Action Required
            ───────────────────────────────────────────────────────────────
            Google may suppress or reject products with empty required fields.
            Please fill in the missing attributes in Odoo before the next upload.

            💡 Tip: Use the Feed Column's "Required" flag to track mandatory attributes.
            ───────────────────────────────────────────────────────────────
        """
        if not warnings:
            return ""

        SEP = "─" * 65
        WIDE_SEP = "═" * 65
        unique_products = len({p for v in warnings.values() for p in v})
        total_cells = sum(len(v) for v in warnings.values())
        field_count = len(warnings)

        lines = [
            "╔" + WIDE_SEP + "╗",
            "║{:^65}║".format("⚠️  GMC FEED — REQUIRED FIELDS REPORT"),
            "╚" + WIDE_SEP + "╝",
            "",
            "Summary",
            SEP,
            "  • Fields with missing values : %d" % field_count,
            "  • Unique products affected   : %d" % unique_products,
            "  • Total missing cells        : %d" % total_cells,
            SEP,
            "",
        ]

        for idx, (label, product_names) in enumerate(sorted(warnings.items()), start=1):
            count = len(product_names)
            lines.append(
                "[%d/%d] %s  — %d product(s) affected" % (idx, field_count, label, count)
            )
            lines.append(SEP)
            # Show up to 20 products per field; summarise the rest to keep logs readable
            visible = product_names[:20]
            hidden = product_names[20:]
            for name in visible:
                lines.append("  • %s" % name)
            if hidden:
                lines.append(
                    "  … and %d more product(s) not shown (fix the first %d and re-upload)."
                    % (len(hidden), len(visible))
                )
            lines.append("")

        lines += [
            SEP,
            "⚡ Action Required",
            SEP,
            "Google may suppress or reject products with empty required fields.",
            "Please fill in the missing attributes in Odoo before the next upload.",
            "",
            "💡 Tip: Use the Feed Column's \"Required\" flag to track mandatory attributes.",
            SEP,
        ]

        return "\n".join(lines)

    @staticmethod
    def _escape(text):
        """XML-escape a string."""
        if not text:
            return ""
        return (
            str(text)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
        )

    # ── SFTP ───────────────────────────────────────────────────────────────────
    def _get_sftp_credentials(self):
        if self.use_global_sftp:
            ICP = self.env["ir.config_parameter"].sudo()
            return {
                "host": ICP.get_str("gmc.sftp_host", "partnerupload.google.com"),
                "port": int(ICP.get_str("gmc.sftp_port", "19321")),
                "username": ICP.get_str("gmc.sftp_username", ""),
                "password": ICP.get_str("gmc.sftp_password", ""),
            }
        return {
            "host": self.sftp_host or "partnerupload.google.com",
            "port": self.sftp_port or 19321,
            "username": self.sftp_username or "",
            "password": self.sftp_password or "",
        }

    def _upload_via_sftp(self, content_bytes, remote_filename):
        """Upload bytes to Google SFTP server using paramiko."""
        try:
            import paramiko
        except ImportError as exc:
            raise UserError(_(
                "Python library 'paramiko' is required for SFTP uploads.\n"
                "Install it with: pip install paramiko"
            )) from exc

        creds = self._get_sftp_credentials()
        if not creds["username"] or not creds["password"]:
            raise UserError(_(
                "SFTP credentials are not configured. "
                "Go to Settings → Google Merchant Center and fill in the credentials."
            ))

        transport = paramiko.Transport((creds["host"], creds["port"]))
        try:
            transport.connect(
                username=creds["username"].strip(),
                password=creds["password"].strip(),
            )
            sftp = paramiko.SFTPClient.from_transport(transport)
            with sftp.file(remote_filename, "wb") as remote_file:
                remote_file.write(content_bytes)
            sftp.close()
            _logger.info(
                "GMC Feed '%s': uploaded %d bytes to sftp://%s/%s",
                self.name, len(content_bytes), creds["host"], remote_filename,
            )
        finally:
            transport.close()

    def action_test_sftp_connection(self):
        """Test SFTP connection credentials."""
        self.ensure_one()
        try:
            import paramiko
        except ImportError as exc:
            raise UserError(_("Python library 'paramiko' is required. Install it using: pip install paramiko")) from exc

        creds = self._get_sftp_credentials()
        if not creds["username"] or not creds["password"]:
            raise UserError(_("SFTP credentials are not configured. Please enter them first."))

        transport = paramiko.Transport((creds["host"], creds["port"]))
        try:
            transport.connect(
                username=creds["username"].strip(),
                password=creds["password"].strip(),
            )
            sftp = paramiko.SFTPClient.from_transport(transport)
            sftp.close()
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _("SFTP Connection Successful"),
                    'message': _("Successfully connected to SFTP server: %s") % creds["host"],
                    'type': 'success',
                    'sticky': False,
                }
            }
        except Exception as exc:
            raise UserError(_("SFTP Connection Failed!\nError details: %s") % str(exc))
        finally:
            transport.close()
