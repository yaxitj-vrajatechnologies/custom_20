# -*- coding: utf-8 -*-
from odoo import models, api, fields
from odoo.exceptions import UserError
import json
import requests
import base64
import csv
import io
import logging
import math
import pytz
from datetime import datetime, timedelta
from collections import defaultdict

_logger = logging.getLogger(__name__)


class VrajaAICard(models.Model):
    _inherit = 'vraja.ai.card'
    _rec_name = 'action_name'

    action_name = fields.Char(compute='_compute_card_name', store=False)

    def _compute_card_name(self):
        for rec in self:
            labels = dict(rec._fields['vraja_common_store']._description_selection(rec.env))
            rec.action_name = labels.get(rec.vraja_common_store, 'Unnamed')

    vraja_common_store = fields.Selection(
        selection_add=[('dynamic_pricing', 'Dynamic Pricing with AI')]
    )

    # Products selected for pricing analysis
    dp_selected_product_ids = fields.Many2many(
        'product.product',
        'vraja_card_dp_product_rel',
        'card_id', 'product_id',
        string='Selected Products',
        store=True,
        domain=[('active', '=', True), ('sale_ok', '=', True)],
    )

    # Target pricelists — used at the card level when writing prices
    dp_pricelist_ids = fields.Many2many(
        'product.pricelist',
        'vraja_card_dp_pricelist_rel',
        'card_id', 'pricelist_id',
        string='Target Pricelists',
    )

    # CSV attachment generated from product signals (one per card)
    dp_csv_attachment_id = fields.Many2one(
        'ir.attachment',
        string='Last Products CSV',
        readonly=True,
        help='CSV generated from product signals on Save & Next. Uploaded to OpenAI per batch.',
    )

    # Competitor URLs stored as JSON array of {url: ...} objects
    dp_competitor_urls_json = fields.Text(
        string='Competitor URLs JSON',
        default='[]',
        help='Dynamic list of competitor URLs as JSON array.',
    )

    # ── Global pricing guardrails (used as defaults for segments) ─────────────
    dp_min_margin_pct = fields.Float(
        string='Min Margin (%)', default=15.0,
        help='AI will never suggest a price below this margin. Acts as price floor.',
    )
    dp_max_margin_pct = fields.Float(
        string='Max Margin (%)', default=60.0,
        help='AI will never suggest a price above this margin. Acts as price ceiling.',
    )
    dp_max_increase_pct = fields.Float(
        string='Max Price Increase (%)', default=10.0,
        help='Maximum % the AI can increase price in one run.',
    )
    dp_max_decrease_pct = fields.Float(
        string='Max Price Decrease (%)', default=20.0,
        help='Maximum % the AI can decrease price in one run.',
    )

    # ── Thresholds ────────────────────────────────────────────────────────────
    dp_dead_stock_days = fields.Integer(
        string='Dead Stock Days', default=45,
        help='Days without any sale before a product is flagged as dead stock.',
    )
    dp_sales_history_days = fields.Integer(
        string='Sales History Days', default=30,
        help='How many recent days of sales to include in the analysis.',
    )

    # ── Business context & prompts ────────────────────────────────────────────
    dp_auto_apply = fields.Boolean(string='Auto Apply via Cron', default=False)
    dp_cron_time = fields.Char(string='Cron Run Time', default='02:00 AM')
    dp_business_info = fields.Text(string='Business Context')

    dp_ai_instruction = fields.Text(
        string='AI System Instruction',
        default=lambda self: self._default_dp_ai_instruction(),
    )
    dp_ai_prompt = fields.Text(
        string='AI User Prompt',
        default=lambda self: self._default_dp_ai_prompt(),
    )

    # Segment rules stored as JSON array of segment config objects
    dp_segment_rules_json = fields.Text(string='Segment Rules JSON', default='[]')

    # ── Status & results ──────────────────────────────────────────────────────
    dp_status = fields.Selection([
        ('idle', 'Idle'),
        ('running', 'Running'),
        ('done', 'Done'),
        ('error', 'Error'),
    ], default='idle', string='Status')

    dp_segment_type_options = fields.Selection([
        ('retailer', 'Retailer'),
        ('wholesaler', 'Wholesaler'),
        ('b2b', 'B2B'),
        ('b2c', 'B2C'),
        ('vip', 'VIP'),
        ('distributor', 'Distributor'),
        ('walkin', 'Walk-in'),
    ], string='Segment Type')

    # Accumulated AI results JSON (appended batch-by-batch by cron)
    dp_result_json = fields.Text(string='AI Result JSON', readonly=True)
    dp_analyzed_on = fields.Date(string='Last Analysed On', readonly=True)
    dp_last_tokens = fields.Integer(string='Last Tokens Used', default=0, readonly=True)

    # =========================================================================
    # DEFAULT PROMPTS
    # =========================================================================
    @api.model
    def _default_dp_ai_instruction(self):
        return """\
      You are a pricing engine. Decide the optimal price for every product × segment pair.

      CRITICAL PRIORITY RULE:
      - If COMPETITOR URLS are provided → ALWAYS use PATH A. PATH B is forbidden.
      - In PATH A, undercut % varies per segment. The ONLY price constraint is: suggested_price > cost_price.
      - Margin floor, ceiling, price_min, price_max — these are PATH B rules only. NEVER apply them in PATH A.
      - The purpose of competitor pricing is to MATCH the market, not to enforce our margin targets.

      PATH B rules (apply ONLY when no competitor URL):
      - floor   = cost_price / (1 - min_margin_pct / 100)
      - ceiling = cost_price / (1 - max_margin_pct / 100)
      - price min = max(floor,   current_price * (1 - max_decrease_pct / 100))
      - price max = min(ceiling, current_price * (1 + max_increase_pct / 100))
      - suggested_price must be within [price min, price max], rounded to 2dp.

      ALWAYS:
      - suggested_price must always be > cost_price. No exceptions, both paths.
      - cost_price = 0 → do NOT skip. Proceed with analysis using competitor URL, stock, and demand signals.
                        In PATH A: suggested_price must still be > 0.
                        In PATH B: skip margin clamp (floor/ceiling) only. Still apply stock + demand signals normally.

      - margin_before = (current_price - cost_price) / current_price * 100, rounded 2dp. If cost_price = 0 → null.
      - margin_after  = (suggested_price - cost_price) / suggested_price * 100, rounded 2dp. If cost_price = 0 → null.
      - decision must be: increase / decrease / hold / skip.
      - Return JSON array only. No markdown. No extra text.
      - Every product × segment pair from input must appear in output.
      - Each segment is INDEPENDENT.
      - Product data is provided in CSV format. Parse it as tabular data.
      - days_no_sale = empty string means the product was never sold (treat as null).
      """

    @api.model
    def _default_dp_ai_prompt(self):
        return """\
        Decide the best price for every product × segment pair.
        Read the product data from the CSV provided. Consider ALL signals together.

        CURRENCY NOTE:
        - All prices in the CSV are in {COMPANY_CURRENCY} (passed as COMPANY CURRENCY in the prompt).
        - Competitor URLs may show prices in a different currency.
        - You MUST convert competitor prices to the company currency before any comparison.
        - Use reasonable current exchange rates for conversion.
        - Always state: the competitor price found, the currency it was in, the exchange rate used, and the converted price — all in the reason field.

           ═══════════════════════════════════════════════════════
        PATH A — COMPETITOR URL IS PROVIDED (highest priority)
        ═══════════════════════════════════════════════════════
        CRITICAL: When PATH A is taken, margin clamp (floor/ceiling/price_min/price_max) does NOT apply.
        The ONLY protection is: suggested_price must always be > cost_price.
    
        STEP A1 — STOCK GATE (run before anything else):
        - stock_status = out_of_stock → decision = "hold". STOP. Never change price when stock is zero.
    
        STEP A2 — FETCH COMPETITOR PRICE:
        - Estimate the competitor market price for this product from the provided URL and product name/category.
        - Convert competitor price to company currency if needed. State conversion rate in reason.
        - If competitor price cannot be determined from the URL → fall through to PATH B entirely.
    
        STEP A3 — SEGMENT-BASED UNDERCUT (only rule that applies in PATH A):
        - Apply undercut % based on segment_name:
            b2b         → undercut 1.0%   
            wholesaler  → undercut 1.5%   
            distributor → undercut 1.5%   
            retailer    → undercut 0.5%   
            b2c         → undercut 0.3%   
            walkin      → undercut 0.3%   
            vip         → undercut 0.5%   
            default     → undercut 0.2%   

        - target_price = competitor_price (converted) × segment_multiplier
    
        - If target_price <= cost_price:
            → suggested_price = cost_price × 1.005  ← 0.5% above cost
            → decision = "decrease" if current_price > suggested_price, else "hold"
            → reason must state: "Competitor price below cost. Set to 0.5% above cost price."
            → STOP.
        - If target_price > cost_price:
            → suggested_price = target_price
            → Round to 2 decimal places.
            → Determine decision:
                suggested_price > current_price → increase
                suggested_price < current_price → decrease
                suggested_price = current_price → hold
            → reason must state: segment name, undercut % applied, competitor price, currency conversion if applied.
            → STOP. Do NOT apply any margin clamp. Do NOT run PATH B.

        ═══════════════════════════════════════════════════════
        PATH B — NO COMPETITOR URL (use stock + demand signals)
        ═══════════════════════════════════════════════════════
        (Also used as fallback if competitor price could not be determined in A2)

        STEP B1 — MARGIN COMPLIANCE (always run first, overrides everything):
        - floor   = cost_price / (1 - min_margin_pct / 100)
        - ceiling = cost_price / (1 - max_margin_pct / 100)
        - cost_price = 0 → floor = 0, ceiling = unlimited. Skip margin clamp entirely.
            Continue to STEP B2 normally using stock + demand signals.
            suggested_price must still be > 0.
            margin_before and margin_after = null (cannot calculate without cost price).
        - current_price < floor   → increase to floor immediately. STOP.
        - current_price > ceiling → decrease to ceiling immediately. STOP.

        STEP B2 — STOCK + DEMAND DECISION:
        Apply the first matching case:

          STOCK CRITICAL:
          - out_of_stock (any demand)
              → hold. Never change price when stock is zero.

          DEAD STOCK (days_no_sale > dead_stock_days):
          - dead + overstock   → decrease by max_decrease_pct%. Urgent clearance.
          - dead + in_stock    → decrease by 50% of max_decrease_pct%. Stimulate demand.
          - dead + low_stock   → hold. Stock already low, no need to push further.

          NEVER SOLD (days_no_sale is empty/null):
          - overstock          → decrease to floor. No history + excess stock.
          - in_stock/low_stock → decrease to floor. Price at minimum viable margin.

          OVERSTOCK:
          - overstock + avg_qty_per_day >= 1.0  → hold. High demand will clear stock naturally.
          - overstock + avg_qty_per_day 0.3–1.0 → decrease by 25% of max_decrease_pct%.
          - overstock + avg_qty_per_day < 0.3   → decrease by 50% of max_decrease_pct%.

          DEMAND SIGNALS (normal in_stock or low_stock):
          - avg_qty_per_day >= 1.0 + in_stock   → increase by max_increase_pct%. Strong demand.
          - avg_qty_per_day >= 1.0 + low_stock  → increase by 50% of max_increase_pct%. Strong demand but stock tight.
          - avg_qty_per_day 0.3–1.0             → hold. Moderate steady demand.
          - avg_qty_per_day < 0.3 + low_stock   → hold. Weak demand but stock is also low.
          - avg_qty_per_day < 0.3 + in_stock    → decrease by 30% of max_decrease_pct%. Weak demand, small stimulation.

          FALLBACK:
          - No match above → hold.

        STEP B3 — FINAL CLAMP (always run, no exceptions):
          If cost_price > 0:
            price_min = max(floor, current_price × (1 - max_decrease_pct / 100))
            price_max = min(ceiling, current_price × (1 + max_increase_pct / 100))
          If cost_price = 0:
            price_min = current_price × (1 - max_decrease_pct / 100)
            price_max = current_price × (1 + max_increase_pct / 100)
          suggested_price = clamp(decision price, price_min, price_max)
          Round to 2 decimal places.
          suggested_price must always be > 0.

        ═══════════════════════════════════════════════════════
        OUTPUT — one object per product × segment
        ═══════════════════════════════════════════════════════
        [{
          "product_id": int,
          "product_name": str,
          "segment_name": str,
          "current_price": float,
          "suggested_price": float,
          "decision": "increase|decrease|hold|skip",
          "margin_before": float,
          "margin_after": float,
          "reason": "One clear sentence explaining why this price was `suggested. Example: 'Competitor price ₹450 converted to $5.40, undercut by 0.5% gives $5.35, clamped to floor $5.20 due to margin.' or 'Dead stock with overstock — decreased by max_decrease_pct%. No sales in 60 days.'"    }]
        """

   # =========================================================================
    # DASHBOARD ROUTING
    # =========================================================================

    def action_review_dashboard(self):
        """Routes the card to the Dynamic Pricing dashboard template."""
        action = super().action_review_dashboard()
        self.ensure_one()
        action['name'] = 'Dynamic Pricing Dashboard'
        if self.vraja_common_store == 'dynamic_pricing':
            action['tag'] = 'dynamic_pricing_dashboard_template'
        return action

    def action_log_view(self):
        """Opens the Dynamic Pricing log list view."""
        action = super().action_log_view()
        if self.vraja_common_store == 'dynamic_pricing':
            action['name'] = 'Dynamic Pricing Logs'
            action['views'] = [
                (False, 'list'),
                (self.env.ref('dynamic_pricing_with_ai.dynamic_pricing_ai_log_form_view').id, 'form'),
            ]
            action['context'] = {
                'search_default_filter_dynamic_pricing_ai': 1,
                'create': False,
            }
        return action

    @api.model
    def action_dp_get_default_card_id(self):
        """Returns the ID of the first Dynamic Pricing card. Used by JS on dashboard init."""
        card = self.sudo().search(
            [('vraja_common_store', '=', 'dynamic_pricing')], limit=1
        )
        return card.id if card else False

    # =========================================================================
    # SIGNAL COMPUTATION
    # =========================================================================


    def _build_products_csv(self, products_data):
        """
        Converts a list of product signal dicts into a CSV string.
        Columns match what the AI prompt expects.
        """
        if not products_data:
            return ""

        fieldnames = [
            'product_id', 'product_name', 'category',
            'cost_price', 'current_price',
            'avg_qty_per_day', 'stock_status', 'qty_on_hand',
            'days_no_sale', 'dead_stock_days',
        ]

        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        for row in products_data:
            writer.writerow({f: row.get(f, '') for f in fieldnames})

        return output.getvalue()

    def _generate_and_save_csv(self):
        """
        Generates fresh product signals for all selected products and
        saves the result as an ir.attachment (dp_csv_attachment_id).

        Called automatically from action_save_dp_dashboard_data (Save & Next).
        The CSV is then split into batches and each batch CSV is uploaded
        separately to OpenAI when the cron processes it.

        NOTE: The CSV is generated ONCE here. The cron uploads each batch
        slice of this CSV — one upload per batch.
        """
        self.ensure_one()
        history_days = max(self.dp_sales_history_days or 30, 1)
        dead_stock_days = self.dp_dead_stock_days or 45
        date_from = fields.Date.subtract(fields.Date.today(), days=history_days)

        products_data = []
        for variant in self.dp_selected_product_ids:
            total_qty, _, _ = self._get_sales_history(variant, date_from)
            avg_qty = round(total_qty / history_days, 4)
            stock_status, qty_on_hand = self._get_stock_status(variant)
            days_no_sale = self._get_days_no_sale(variant)

            products_data.append({
                'product_id': variant.id,
                'product_name': variant.display_name,
                'category': variant.categ_id.complete_name or 'Uncategorized',
                'cost_price': variant.standard_price or 0.0,
                'current_price': variant.lst_price or 0.0,
                'avg_qty_per_day': avg_qty,
                'stock_status': stock_status,
                'qty_on_hand': qty_on_hand,
                'days_no_sale': days_no_sale if days_no_sale is not None else '',
                'dead_stock_days': dead_stock_days,
            })

        csv_content = self._build_products_csv(products_data)
        csv_bytes = csv_content.encode('utf-8')

        # Delete old attachment if it already exists
        if self.dp_csv_attachment_id:
            self.dp_csv_attachment_id.sudo().unlink()

        attachment = self.env['ir.attachment'].sudo().create({
            'name': f'dp_products_{fields.Date.today()}.csv',
            'type': 'binary',
            'datas': base64.b64encode(csv_bytes).decode('utf-8'),
            'mimetype': 'text/csv',
            'res_model': self._name,
            'res_id': self.id,
        })
        self.sudo().write({'dp_csv_attachment_id': attachment.id})

    def _upload_csv_to_openai(self, csv_content, api_key):
        """
        Uploads a batch CSV slice to the OpenAI Files API (purpose='user_data').
        Required by the Responses API (/v1/responses) to reference files by ID.

        Returns the file_id string.
        Raises UserError on any HTTP or API error.

        Called once per batch during cron processing — total uploads = total batches.
        """
        csv_bytes = csv_content.encode('utf-8')
        try:
            response = requests.post(
                'https://api.openai.com/v1/files',
                headers={'Authorization': f'Bearer {api_key}'},
                files={
                    'file': ('products.csv', io.BytesIO(csv_bytes), 'text/csv'),
                    'purpose': (None, 'user_data'),
                },
                timeout=60,
            )
            response.raise_for_status()
            file_id = response.json().get('id')
            if not file_id:
                raise UserError('OpenAI file upload returned no file_id.')

            return file_id
        except requests.exceptions.RequestException as e:
            raise UserError(f'Failed to upload CSV to OpenAI: {e}')

    def _delete_openai_file(self, file_id, api_key):
        """
        Deletes the uploaded file from OpenAI after the AI call completes.
        Keeps OpenAI storage clean — the file is not needed after the response.
        Logs a warning on failure but does not raise (non-critical cleanup).
        """
        try:
            requests.delete(
                f'https://api.openai.com/v1/files/{file_id}',
                headers={'Authorization': f'Bearer {api_key}'},
                timeout=30,
            )
        except Exception as e:
            raise UserError(f'Error: {e}')

    # ── Signal helpers ────────────────────────────────────────────────────────

    def _get_sales_history(self, variant, date_from):
        """
        Returns (total_qty_sold, total_revenue, order_count) for a product
        from date_from up to today, counting only confirmed/done sale orders.
        """
        recent_orders = self.env['sale.order'].sudo().search([
            ('date_order', '>=', date_from),
            ('state', 'in', ['sale', 'done']),
        ])
        lines = self.env['sale.order.line'].sudo().search([
            ('product_id', '=', variant.id),
            ('order_id', 'in', recent_orders.ids),
        ])
        total_qty = sum(lines.mapped('product_uom_qty'))
        total_revenue = sum(l.product_uom_qty * l.price_unit for l in lines)
        order_count = len(set(lines.mapped('order_id').ids))
        return round(total_qty, 4), round(total_revenue, 4), order_count

    def _get_stock_status(self, variant):
        """
        Returns (stock_status_string, qty_on_hand).

        Status logic (compared against reorder point from stock.warehouse.orderpoint,
        falls back to 10 units if no rule is set):
          qty <= 0           → out_of_stock
          qty < reorder      → low_stock
          qty <= reorder * 3 → in_stock
          qty > reorder * 3  → overstock
        """
        quants = self.env['stock.quant'].sudo().search([
            ('product_id', '=', variant.id),
            ('location_id.usage', '=', 'internal'),
        ])
        qty = sum(quants.mapped('quantity'))
        orderpoint = self.env['stock.warehouse.orderpoint'].sudo().search([
            ('product_id', '=', variant.id),
        ], limit=1)
        reorder_qty = orderpoint.product_min_qty if orderpoint else 10.0

        if qty <= 0:
            status = 'out_of_stock'
        elif qty < reorder_qty:
            status = 'low_stock'
        elif qty <= reorder_qty * 3:
            status = 'in_stock'
        else:
            status = 'overstock'

        return status, round(qty, 2)

    def _get_days_no_sale(self, variant):
        """
        Returns the number of days since the last confirmed sale order for the product.
        Returns None if the product has never been sold.
        """
        last_order = self.env['sale.order'].sudo().search([
            ('state', 'in', ['sale', 'done']),
            ('order_line.product_id', '=', variant.id),
        ], order='date_order desc', limit=1)
        if last_order and last_order.date_order:
            return (fields.Date.today() - last_order.date_order.date()).days
        return None

    # =========================================================================
    # PROMPT BUILDER
    # =========================================================================

    def _build_dp_prompt(self, products_data, segments, csv_content=None):
        """
        Builds the full user prompt for a single AI batch call.
        Combines: base prompt, business context, competitor URLs,
        segment rules, product CSV column description, and expected row count.

        products_data: list of data row strings (CSV lines without header) — used only for count.
        segments: list of segment rule dicts from the batch record.
        csv_content: full CSV string (header + rows). When provided (Claude/Gemini),
                     the CSV is embedded directly into the prompt body.
                     When None (OpenAI), prompt references the attached CSV file instead.
        """
        self.ensure_one()
        business = "BUSINESS: " + (self.dp_business_info or "Not provided.")

        company_currency = self.env.company.currency_id.name or 'USD'

        urls_list = json.loads(self.dp_competitor_urls_json or '[]')
        urls = [u.get('url', '').strip() for u in urls_list if u.get('url', '').strip()]

        competitor = (
            "COMPETITOR URLS:\n" + "\n".join(f"  {i + 1}. {u}" for i, u in enumerate(urls))
            if urls else "COMPETITOR URLS: None. Use demand signals only."
        )

        segment_rows = [{
            'segment_name': seg.get('customer_type', 'Unnamed'),
            'min_margin_pct': seg.get('min_margin_pct', self.dp_min_margin_pct or 15.0),
            'max_margin_pct': seg.get('max_margin_pct', self.dp_max_margin_pct or 60.0),
            'max_increase_pct': seg.get('max_increase_pct', self.dp_max_increase_pct or 10.0),
            'max_decrease_pct': seg.get('max_decrease_pct', self.dp_max_decrease_pct or 20.0),
        } for seg in segments]

        segments_block = "SEGMENTS:\n" + json.dumps(segment_rows, indent=2)

        config_header = (
            f"COMPANY CURRENCY: {company_currency}\n"
            f"GLOBAL CONFIG: dead_stock_days={self.dp_dead_stock_days or 45} | "
            f"sales_window_days={self.dp_sales_history_days or 30}"
        )
        col_desc = (
            "Columns: product_id, product_name, category, cost_price, current_price, "
            "avg_qty_per_day, stock_status, qty_on_hand, days_no_sale, dead_stock_days\n"
            "days_no_sale is empty = product never sold."
        )

        if csv_content:
            # Claude / Gemini — embed the full CSV directly in the prompt
            products_block = (
                f"{config_header}\n\n"
                f"PRODUCTS (CSV):\n{csv_content}\n{col_desc}"
            )
        else:
            # OpenAI — CSV is uploaded as a file attachment; reference it here
            products_block = (
                f"{config_header}\n\n"
                "PRODUCTS: provided as attached CSV file (products.csv).\n"
                f"{col_desc}"
            )

        expected = len(products_data) * len(segment_rows)
        reminder = (
            f"Return {expected} rows "
            f"({len(products_data)} products × {len(segment_rows)} segments). "
            "JSON only."
        )

        return "\n\n".join([self.dp_ai_prompt, business, competitor, segments_block, products_block, reminder])

    # =========================================================================
    # AI API CALL
    # =========================================================================

    def _get_dp_ai_config(self):
        """
        Returns the vraja.ai.config record and validates that the active
        provider's API key and model are configured.
        Raises UserError if missing.
        """
        config = self.env['vraja.ai.config'].sudo().search([], limit=1)
        if not config:
            raise UserError(
                'AI configuration not found. '
                'Go to AI Dashboard ▸ Configuration and set up your AI provider.'
            )

        provider = config.ai_provider or 'openai'

        if provider == 'claude' and not ((config.claude_api_key or '').strip() and config.claude_llm_model):
            raise UserError('Claude API key or model is not configured.')
        elif provider == 'gemini' and not ((config.gemini_api_key or '').strip() and config.gemini_llm_model):
            raise UserError('Gemini API key or model is not configured.')
        elif provider == 'openai' and not ((config.openai_api_key or '').strip() and config.llm_model):
            raise UserError('OpenAI API key or model is not configured.')

        return config

    def _call_dp_ai_api(self, system_prompt, user_prompt, file_id=None):
        """
        Sends a single AI request based on the configured provider.

        OpenAI : Responses API (/v1/responses) — CSV delivered via file_id attachment.
        Claude : Messages API (/v1/messages)   — CSV embedded directly in the user prompt.
        Gemini : generateContent REST API      — CSV embedded directly in the user prompt.

        Returns (raw_text_response, total_tokens_used).
        Raises UserError on any failure.
        """
        config = self._get_dp_ai_config()
        provider = config.ai_provider or 'openai'

        # ── Build payload and request params per provider ─────────────────────
        if provider == 'openai':
            req_url = 'https://api.openai.com/v1/responses'
            req_headers = {
                'Authorization': f'Bearer {config.openai_api_key}',
                'Content-Type': 'application/json',
            }
            payload = {
                'model': config.llm_model,
                'instructions': system_prompt,
                'input': [{'role': 'user', 'content': [
                    {'type': 'input_text', 'text': user_prompt},
                    {'type': 'input_file', 'file_id': file_id},
                ]}],
            }

        elif provider == 'claude':
            llm_model = config.claude_llm_model or 'claude-sonnet-4-6'
            _logger.info('Dynamic Pricing [Claude]: model=%s', llm_model)
            req_url = 'https://api.anthropic.com/v1/messages'
            req_headers = {
                'x-api-key': (config.claude_api_key or '').strip(),
                'anthropic-version': '2023-06-01',
                'content-type': 'application/json',
            }
            payload = {
                'model': llm_model,
                'max_tokens': config.claude_max_tokens or 8192,
                'system': system_prompt,
                'messages': [{'role': 'user', 'content': user_prompt}],
            }

        elif provider == 'gemini':
            llm_model = config.gemini_llm_model or 'gemini-flash-latest'
            _logger.info('Dynamic Pricing [Gemini]: model=%s', llm_model)
            gemini_api_key = (config.gemini_api_key or '').strip()
            req_url = (
                f'https://generativelanguage.googleapis.com/v1beta/models/'
                f'{llm_model}:generateContent?key={gemini_api_key}'
            )
            req_headers = {'Content-Type': 'application/json'}
            payload = {
                'system_instruction': {'parts': [{'text': system_prompt}]},
                'contents': [{'parts': [{'text': user_prompt}]}],
                'generationConfig': {'responseMimeType': 'application/json'},
            }

        else:
            raise UserError(f"Unknown AI provider '{provider}' in vraja.ai.config.")

        # ── Single try/except for all providers ───────────────────────────────
        try:
            resp = requests.post(req_url, json=payload, headers=req_headers, timeout=500)
            resp.raise_for_status()
            body = resp.json()

            if provider == 'openai':
                tokens = body.get('usage', {}).get('total_tokens', 0)
                text = None
                for item in body.get('output', []):
                    if item.get('type') == 'message':
                        for block in item.get('content', []):
                            if block.get('type') == 'output_text':
                                text = block.get('text', '')
                                break
                    if text is not None:
                        break

            elif provider == 'claude':
                usage = body.get('usage', {})
                tokens = usage.get('input_tokens', 0) + usage.get('output_tokens', 0)
                _logger.info('Dynamic Pricing [Claude] tokens — input: %s, output: %s',
                             usage.get('input_tokens', 0), usage.get('output_tokens', 0))
                text_blocks = [b for b in body.get('content', []) if b.get('type') == 'text']
                if not text_blocks:
                    raise UserError(
                        f"Claude returned no 'text' block. "
                        f"stop_reason={body.get('stop_reason')}, "
                        f"content_types={[b.get('type') for b in body.get('content', [])]}"
                    )
                text = text_blocks[0]['text'].strip()

            elif provider == 'gemini':
                tokens = body.get('usageMetadata', {}).get('totalTokenCount', 0)
                _logger.info('Dynamic Pricing [Gemini] totalTokenCount: %s', tokens)
                candidates = body.get('candidates', [])
                if not candidates:
                    raise UserError(f'Gemini returned no candidates. Full response: {body}')
                parts = candidates[0].get('content', {}).get('parts', [])
                if not parts or 'text' not in parts[0]:
                    raise UserError(f'Gemini returned unexpected content structure: {candidates[0]}')
                text = parts[0]['text'].strip()

            return text, tokens

        except requests.exceptions.Timeout:
            raise UserError(f'{provider} API timed out. Please try again.')
        except requests.exceptions.ConnectionError:
            raise UserError(f'Cannot connect to {provider} API. Check your internet connection.')
        except requests.exceptions.RequestException as e:
            raise UserError(f'{provider} API request failed: {e}')
        except (KeyError, IndexError, TypeError) as e:
            raise UserError(f'Unexpected response format from {provider}: {e}')

    # =========================================================================
    # RESPONSE PARSER
    # =========================================================================

    def _parse_dp_ai_response(self, raw_text):
        """
        Parses the AI JSON array response.
        Strips markdown code fences if present.
        Returns a list of normalised result dicts, one per product × segment row.
        Raises UserError if the response is not valid JSON or not a list.
        """
        cost_map = {
            p.id: p.standard_price
            for p in self.dp_selected_product_ids
        }
        text = raw_text.strip()

        # Step 1: Strip markdown fences if present
        if text.startswith('```'):
            text = text.split('\n', 1)[-1]
            text = text.rsplit('```', 1)[0].strip()

        # Step 2: Extract only the JSON array (from first [ to last ])
        # Handles trailing text/notes that Claude sometimes adds after the array
        start_idx = text.find('[')
        end_idx = text.rfind(']')
        if start_idx != -1 and end_idx != -1:
            text = text[start_idx:end_idx + 1]

        try:
            items = json.loads(text)
        except json.JSONDecodeError as e:
            raise UserError(
                f'AI returned invalid JSON: {e}\n\nRaw response:\n{raw_text[:500]}'
            )

        if not isinstance(items, list):
            raise UserError('AI response was not a JSON array as required.')

        results = []
        for item in items:
            if not item.get('product_id'):
                continue
            product_id = int(item['product_id'])
            current_price = float(item.get('current_price') or 0)
            suggested_price = float(item.get('suggested_price') or 0)

            decision = (
                'skip' if item.get('decision') == 'skip' or suggested_price <= 0
                else 'increase' if suggested_price > current_price
                else 'decrease' if suggested_price < current_price
                else 'hold'
            )

            show_margin = decision in ('increase', 'decrease')

            results.append({
                'product_id': int(item['product_id']),
                'product_name': item.get('product_name', ''),
                'segment_name': item.get('segment_name', ''),
                'current_price': current_price,
                'suggested_price': suggested_price,
                'cost_price': cost_map.get(product_id, 0.0),
                'decision': decision,
                'margin_before': float(item.get('margin_before') or 0) if show_margin else None,
                'margin_after': float(item.get('margin_after') or 0) if show_margin else None,
                'reason': item.get('reason', ''),
            })
        return results

    @api.model
    def action_delete_dp_result_rows(self, card_id, row_keys):
        """Remove specific rows from dp_result_json by rowKey (product_id_segment_name)."""
        card = self.browse(card_id)
        if not card or not card.dp_result_json:
            return
        existing = json.loads(card.dp_result_json or '[]')
        # rowKey format is: {product_id}_{segment_name}
        filtered = [
            r for r in existing
            if f"{r.get('product_id')}_{r.get('segment_name', '')}" not in row_keys
        ]
        card.sudo().write({'dp_result_json': json.dumps(filtered, ensure_ascii=False, indent=2)})

    # =========================================================================
    # DASHBOARD DATA — JS Interface
    # =========================================================================

    def get_dp_dashboard_data(self):
        """
        Returns all data needed to populate the Dynamic Pricing wizard dashboard.
        Called by JS on initial load and after every save.
        Includes: card config, segment rules, selected products, batches, and CSV info.
        """
        self.ensure_one()
        segment_field = self.fields_get(['dp_segment_type_options'])
        segment_options = segment_field.get('dp_segment_type_options', {}).get('selection', [])

        return {
            'id': self.id,
            'dp_status': self.dp_status,
            'dp_analyzed_on': self.dp_analyzed_on and str(self.dp_analyzed_on) or False,
            'dp_last_tokens': self.dp_last_tokens or 0,
            'dp_min_margin_pct': self.dp_min_margin_pct,
            'dp_max_margin_pct': self.dp_max_margin_pct,
            'dp_max_increase_pct': self.dp_max_increase_pct,
            'dp_max_decrease_pct': self.dp_max_decrease_pct,
            'dp_dead_stock_days': self.dp_dead_stock_days,
            'dp_sales_history_days': self.dp_sales_history_days,
            'dp_auto_apply': self.dp_auto_apply,
            'dp_cron_time': self.dp_cron_time or '02:00 AM',
            'dp_business_info': self.dp_business_info or '',
            'dp_result_json': self.dp_result_json or '',
            'dp_competitor_urls': json.loads(self.dp_competitor_urls_json or '[]'),
            'dp_segment_rules': json.loads(self.dp_segment_rules_json or '[]'),
            'dp_csv_attachment_id': self.dp_csv_attachment_id.id if self.dp_csv_attachment_id else False,
            'dp_batches': self._dp_get_batches(),
            'dp_csv_attachment_url': (
                f'/web/content/{self.dp_csv_attachment_id.id}?download=true'
                if self.dp_csv_attachment_id else ''
            ),
            'dp_segment_type_options': [
                {'value': v, 'label': l} for v, l in segment_options
            ],
            'pricelist_ids': [
                {'id': pl.id, 'name': pl.name} for pl in self.dp_pricelist_ids
            ],
            'selected_products': [
                {'id': p.id, 'name': p.display_name, 'cost_price': p.standard_price}
                for p in self.dp_selected_product_ids
            ],
        }

    def action_save_dp_dashboard_data(self, values):
        """
        Called when the user clicks 'Save & Next' on Step 4 (Configure Settings).
        Persists all wizard form values, regenerates the product CSV,
        creates fresh batches (clearing old ones and Step 6 results),
        and syncs the cron job schedule.

        Flow triggered by this method:
          1. Write scalar fields + M2M relations
          2. _generate_and_save_csv()    → fresh product signals CSV saved as attachment
          3. _create_dp_batches()        → old batches + dp_result_json cleared; new draft batches created
          4. Cron schedule synced if dp_auto_apply or dp_cron_time changed
        """
        self.ensure_one()

        scalar_fields = [
            'dp_min_margin_pct', 'dp_max_margin_pct',
            'dp_max_increase_pct', 'dp_max_decrease_pct',
            'dp_dead_stock_days', 'dp_sales_history_days',
            'dp_auto_apply', 'dp_business_info',
            'dp_competitor_urls_json', 'dp_cron_time',
        ]
        write_vals = {k: v for k, v in values.items() if k in scalar_fields}

        if 'dp_selected_product_ids' in values:
            write_vals['dp_selected_product_ids'] = [(6, 0, values['dp_selected_product_ids'])]
        if 'dp_pricelist_ids' in values:
            write_vals['dp_pricelist_ids'] = [(6, 0, values['dp_pricelist_ids'])]

        if 'dp_segment_rules' in values:
            rules = values['dp_segment_rules']
            # Assign a simple incremental id to any rule missing one
            for i, r in enumerate(rules):
                if not r.get('id'):
                    r['id'] = i + 1
            write_vals['dp_segment_rules_json'] = json.dumps(rules)

        self.sudo().write(write_vals)

        # Regenerate CSV and create batches whenever products are configured
        if values.get('create_batches') and self.dp_selected_product_ids:
            self._generate_and_save_csv()
            self._create_dp_batches(values.get('dp_segment_rules', []))

        # Sync cron job — update active flag and next call time
        if 'dp_auto_apply' in write_vals or 'dp_cron_time' in write_vals:
            schedule_cron = self.env.ref(
                'dynamic_pricing_with_ai.ir_cron_dp_auto_trigger',
                raise_if_not_found=False,
            )
            cron_vals = {'active': bool(self.dp_auto_apply)}

            if self.dp_auto_apply:
                time_str = self.dp_cron_time or '02:00 AM'
                time_str_clean = time_str.strip().split('(')[0].strip()
                t = datetime.strptime(time_str_clean, '%I:%M %p')
                user_tz = self.env.user.tz or 'UTC'
                local_tz = pytz.timezone(user_tz)
                now_local = datetime.now(local_tz)
                next_call_local = now_local.replace(
                    hour=t.hour, minute=t.minute, second=0, microsecond=0
                )
                if next_call_local <= now_local:
                    next_call_local += timedelta(days=1)
                next_call_utc = next_call_local.astimezone(pytz.utc).replace(tzinfo=None)
                cron_vals['nextcall'] = next_call_utc

            if schedule_cron:
                schedule_cron.sudo().write(cron_vals)

        return {'success': True}

    def _dp_get_batches(self):
        """
        Returns the batch list for the Step 5 display.
        Each batch shows: id, name, state, index, totals, product count, and any error.
        """
        self.ensure_one()
        batches = self.env['vraja.dp.batch'].sudo().search(
            [('card_id', '=', self.id)],
            order='batch_index asc',
        )
        return [{
            'id': b.id,
            'name': b.name,
            'state': b.state,
            'batch_index': b.batch_index,
            'total_batches': b.total_batches,
            'products_count': b.products_count,
            'error_message': b.error_message or '',
        } for b in batches]

    def _create_dp_batches(self, segments=None):
        """
        Creates fresh draft batch records from the saved CSV attachment.
        Called automatically from action_save_dp_dashboard_data.

        Before creating new batches:
          - Deletes ALL existing batches for this card
          - Clears dp_result_json (Step 6) so old analysis is removed

        Batch size: up to 100 product×segment rows per batch.
        Each batch stores its own CSV slice and segment rules.

        CSV upload happens LATER — one upload per batch in the cron, not here.
        """
        self.ensure_one()

        # Clear old batches and Step 6 results before creating new ones
        self.env['vraja.dp.batch'].sudo().search(
            [('card_id', '=', self.id)]
        ).unlink()
        self.sudo().write({
            'dp_result_json': False,
            'dp_status': 'idle',
            'dp_last_tokens': 0,
        })

        segments = segments or json.loads(self.dp_segment_rules_json or '[]')
        if not segments:
            return

        if not self.dp_csv_attachment_id:
            return

        csv_bytes = base64.b64decode(self.dp_csv_attachment_id.datas)
        csv_content = csv_bytes.decode('utf-8')

        csv_lines = [l for l in csv_content.splitlines() if l.strip()]
        if len(csv_lines) < 2:
            return

        header = csv_lines[0]
        data_rows = csv_lines[1:]
        total_products = len(data_rows)
        segment_count = len(segments)

        # Calculate how many products fit per batch (target: 100 product×segment rows)
        BATCH_SIZE = 100
        products_per_batch = math.ceil(BATCH_SIZE / segment_count)

        batches = [
            data_rows[i:i + products_per_batch]
            for i in range(0, total_products, products_per_batch)
        ]
        total_batches = len(batches)
        segments_json = json.dumps(segments)

        for idx, batch_rows in enumerate(batches):
            # Each batch gets its own CSV slice (header + data rows)
            batch_csv = header + '\n' + '\n'.join(batch_rows)
            self.env['vraja.dp.batch'].sudo().create({
                'name': f'Batch {idx + 1} of {total_batches}',
                'card_id': self.id,
                'state': 'draft',
                'batch_index': idx + 1,
                'total_batches': total_batches,
                'products_count': len(batch_rows),
                'csv_rows': batch_csv,
                'segment_rules_json': segments_json,
            })

    # =========================================================================
    # APPLY PRICING — writes suggested prices to pricelists only
    # =========================================================================

    def action_apply_dynamic_pricing(self, segments=None, active_rows=None):
        """
        Writes AI suggested prices to the pricelists mapped to each segment.
        Called when the user clicks 'Apply' on Step 6.

        segments: list of segment rule dicts (contains segment_name → pricelist_ids mapping).
        active_rows: filtered list of result rows to apply (deleted rows excluded by JS).

        For each row:
          - 'hold' and 'skip' decisions are skipped.
          - Each pricelist mapped to the segment gets an upserted pricelist item.
        Returns {'applied': N, 'skipped': N, 'errors': N}.
        """
        self.ensure_one()

        if not self.dp_result_json:
            return {'applied': 0}

        segments = segments or []

        # Build label map from selection field
        segment_field = self.fields_get(['dp_segment_type_options'])
        segment_options = segment_field.get('dp_segment_type_options', {}).get('selection', [])
        label_map = {v: l for v, l in segment_options}

        # Build lookup: segment_name → list of pricelist IDs
        seg_map = {}
        for seg in segments:
            key = seg.get('customer_type', '').strip().lower()
            seg_map[key] = seg.get('pricelist_ids', [])

        parsed = active_rows if active_rows is not None else json.loads(self.dp_result_json)
        applied = 0
        skipped = 0
        errors = 0
        log_lines = []

        for row in parsed:
            decision = row.get('decision', 'hold')
            suggested_price = row.get('suggested_price', 0.0)
            segment_name = row.get('segment_name', '')
            product_id = row.get('product_id')

            if not product_id:
                continue

            product = self.env['product.product'].browse(int(product_id))

            # Skip if product no longer exists
            if not product.exists():
                continue

            # Skip hold/skip decisions and zero prices
            if decision in ('hold', 'skip') or not suggested_price:
                skipped += 1
                continue

            # Skip if no pricelist is mapped for this segment
            pricelist_ids = seg_map.get(segment_name, [])
            if not pricelist_ids:
                errors += 1
                continue

            row_has_error = False
            for pl_id in pricelist_ids:
                if isinstance(pl_id, dict):
                    pl_id = pl_id.get('id')
                if not pl_id:
                    continue
                pricelist = self.env['product.pricelist'].browse(pl_id)
                if not pricelist.exists():
                    continue
                try:
                    self._upsert_pricelist_item(pricelist, product, suggested_price)
                except Exception as e:
                    row_has_error = True
                    errors += 1

            if row_has_error:
                continue

            applied += 1
            log_lines.append(self._build_log_line(product, {
                **row,
                'segment_name': label_map.get(segment_name, segment_name),
            }, 'success'))

        # Reset card status after applying
        self.sudo().write({'dp_status': 'idle'})

        # Create one DB log record for all successfully applied lines
        if log_lines:
            self._create_dp_log(status='success',
                                message=(
                                    f'AI Dynamic Pricing applied successfully.\n'
                                    f'{applied} product–segment combination updated across pricelists.\n'
                                    f'{skipped} row skipped.\n'
                                    f'{errors} error encountered.\n'
                                ),
                                log_lines=log_lines, total_tokens=self.dp_last_tokens or 0, applied=True,
                                pricelists_updated=applied)

        return {'applied': applied, 'skipped': skipped, 'errors': errors}

    def _upsert_pricelist_item(self, pricelist, variant, suggested_price):
        """
        Creates or updates the AI pricelist item for a product on a pricelist.
        Uses 'fixed' price when suggested_price >= list_price, 'percentage' otherwise.
        Only touches records flagged with is_ai_price=True to avoid overwriting manual entries.
        """
        original_price = variant.lst_price

        if suggested_price >= original_price:
            price_vals = {
                'compute_price': 'fixed',
                'fixed_price': suggested_price,
            }
        else:
            if original_price > 0:
                percent_price = round((1.0 - suggested_price / original_price) * 100.0, 4)
            else:
                percent_price = 0.0
            price_vals = {
                'compute_price': 'percentage',
                'percent_price': percent_price,
            }

        existing_ai_line = self.env['product.pricelist.item'].sudo().search([
            ('pricelist_id', '=', pricelist.id),
            ('product_id', '=', variant.id),
            ('is_ai_price', '=', True),
        ], limit=1)

        if existing_ai_line:
            existing_ai_line.sudo().write(price_vals)
        else:
            create_vals = {
                'pricelist_id': pricelist.id,
                'applied_on': '0_product_variant',
                'product_tmpl_id': variant.product_tmpl_id.id,
                'product_id': variant.id,
                'is_ai_price': True,
                **price_vals,
            }
            self.env['product.pricelist.item'].sudo().create(create_vals)

    # =========================================================================
    # LOGGING HELPERS
    # =========================================================================

    def _create_dp_log(self, status, message='', total_tokens=0, log_lines=None, applied=False, pricelists_updated=0):
        """Creates a vraja.ai.log record with optional line_ids for the dynamic pricing store."""
        self.ensure_one()
        log_vals = {
            'vraja_common_log_store': 'dynamic_pricing',
            'dp_log_message': message,
            'dp_total_products':len(set(line['dp_product_id'] for line in log_lines)) if log_lines else 0,
            'dp_total_tokens': total_tokens,
            'dp_applied': applied,
            'dp_pricelists_updated': pricelists_updated,
            'status': status,
            'line_ids': [(0, 0, line) for line in (log_lines or [])],
        }
        return self.env['vraja.ai.log'].sudo().create(log_vals)

    def _build_log_line(self, product, result, status, old_price=None):
        """Builds a single log line dict for _create_dp_log."""
        return {
            'dp_product_id': product.id,
            'dp_product_name': product.display_name,
            'dp_segment_name': result.get('segment_name', ''),
            'dp_old_price': old_price or product.lst_price,
            'dp_ai_suggested_price': result.get('suggested_price', 0),
            'dp_decision': result.get('decision', 'hold'),
            'dp_margin_before': result.get('margin_before', 0),
            'dp_margin_after': result.get('margin_after', 0),
            'dp_status': status,
        }

    # =========================================================================
    # CRON — single entry point for all batch processing
    # =========================================================================

    @api.model
    def action_cron_dp_run_analysis(self, batch_id=None):
        """
        Scheduled action — processes all draft batches in order.
        When batch_id is provided (manual run), processes only that specific batch.
        """
        card = self.search([
            ('vraja_common_store', '=', 'dynamic_pricing'),
            ('vraja_common_card_active', '=', True),
        ], limit=1)
        if not card:
            return

        # Validate the active provider's config — raises UserError if misconfigured
        try:
            config = card._get_dp_ai_config()
        except Exception as e:
            card._create_dp_log(
                status='failed',
                message=f'AI configuration error: {str(e)}',
            )
            # Mark all draft batches as error so the UI reflects the failure
            self.env['vraja.dp.batch'].sudo().search([
                ('card_id', '=', card.id),
                ('state', '=', 'draft'),
            ]).write({'state': 'error', 'error_message': str(e)})
            card.sudo().write({'dp_status': 'error'})
            self.env.cr.commit()
            return

        provider = config.ai_provider or 'openai'

        if batch_id:
            batches = self.env['vraja.dp.batch'].sudo().browse(batch_id)
        else:
            batches = self.env['vraja.dp.batch'].sudo().search([
                ('state', '=', 'draft'),
            ], order='card_id asc, batch_index asc')

        if not batches:
            return

        for batch in batches:
            card = batch.card_id
            file_id = None

            try:
                batch.sudo().write({'state': 'running', 'error_message': False})
                self.env.cr.commit()

                segments = json.loads(batch.segment_rules_json or '[]')

                # OpenAI — upload CSV as a file and get file_id
                # Claude / Gemini — skip upload; CSV is embedded in the prompt
                if provider == 'openai':
                    file_id = card._upload_csv_to_openai(batch.csv_rows, config.openai_api_key)
                    batch.sudo().write({'file_id': file_id})

                batch_rows = [l for l in batch.csv_rows.splitlines()[1:] if l.strip()]

                # For Claude/Gemini pass the full CSV so _build_dp_prompt embeds it.
                # For OpenAI pass None — prompt references the uploaded file attachment.
                csv_for_prompt = batch.csv_rows if provider != 'openai' else None
                user_prompt = card._build_dp_prompt(batch_rows, segments, csv_content=csv_for_prompt)

                raw_result, tokens = card._call_dp_ai_api(
                    card.dp_ai_instruction or '',
                    user_prompt,
                    file_id=file_id,
                )

                if provider == 'openai' and file_id:
                    card._delete_openai_file(file_id, config.openai_api_key)
                    file_id = None

                parsed = card._parse_dp_ai_response(raw_result)

                existing = json.loads(card.dp_result_json or '[]')
                existing.extend(parsed)
                card.sudo().write({
                    'dp_result_json': json.dumps(existing, ensure_ascii=False, indent=2),
                    'dp_analyzed_on': fields.Date.today(),
                    'dp_last_tokens': (card.dp_last_tokens or 0) + tokens,
                })

                batch.sudo().write({
                    'state': 'done',
                    'file_id': False,
                    'result_json': json.dumps(parsed, ensure_ascii=False, indent=2),
                })
                self.env.cr.commit()
                remaining = self.env['vraja.dp.batch'].sudo().search_count([
                    ('card_id', '=', card.id),
                    ('state', '!=', 'done'),
                ])
                if not remaining:
                    card.sudo().write({'dp_status': 'done'})
                    self.env.cr.commit()

            except Exception as e:
                batch.sudo().write({
                    'state': 'draft',
                    'error_message': str(e),
                    'file_id': False,
                })
                self.env.cr.commit()
                if card and len(card) == 1:
                    card._create_dp_log(status='failed', message=f'Batch {batch.name} failed: {str(e)}',
                                        log_lines=False,
                                        total_tokens=card.dp_last_tokens or 0, applied=False, pricelists_updated=0)
            finally:
                if file_id and provider == 'openai':
                    card._delete_openai_file(file_id, config.openai_api_key)

    @api.model
    def action_cron_dp_schedule_trigger(self):
        """
        Runs daily at dp_cron_time for cards with dp_auto_apply=True.
        Checks if all batches are done and auto-applies results to Odoo.
        Batch creation is handled manually by the user via Save & Next in Step 4.
        """
        card = self.sudo().search([
            ('vraja_common_store', '=', 'dynamic_pricing'),
            ('dp_auto_apply', '=', True),
            ('vraja_common_card_active', '=', True),
            ('dp_selected_product_ids', '!=', False),
        ], limit=1)

        if not card:
            return

        draft_batch = self.env['vraja.dp.batch'].sudo().search_count([
            ('card_id', '=', card.id),
            ('state', 'in', ['draft', 'running']),
        ])

        if draft_batch:
            self.action_cron_dp_run_analysis()

        card.invalidate_recordset()

        if card.dp_status != 'done' or not card.dp_result_json:
            return

        # Auto-apply results to Odoo
        segments = json.loads(card.dp_segment_rules_json or '[]')
        if not segments:
            return

        card.action_apply_dynamic_pricing(segments=segments, active_rows=json.loads(card.dp_result_json))

    # =========================================================================
    # ANALYSIS DASHBOARD DATA HELPERS
    # =========================================================================

    @api.model
    def action_get_dp_analysis_dashboard_data(self, card_id):
        """
        Returns all data for the Analysis Dashboard (separate from the wizard dashboard).
        Data is sourced from the latest applied log and its line_ids.
        Includes: summary KPIs, per-product rows, alerts, run history, segment performance.
        """
        card = self.sudo().browse(card_id)
        if not card.exists() or card.vraja_common_store != 'dynamic_pricing':
            return {}

        # Use the latest applied log; fall back to latest log with any lines
        latest_log = self.env['vraja.ai.log'].sudo().search([
            ('vraja_common_log_store', '=', 'dynamic_pricing'),
            ('dp_applied', '=', True),
        ], order='create_date desc', limit=1)

        if not latest_log:
            latest_log = self.env['vraja.ai.log'].sudo().search([
                ('vraja_common_log_store', '=', 'dynamic_pricing'),
            ], order='create_date desc', limit=1)

        if not latest_log or not latest_log.line_ids:
            return self._dp_empty_dashboard(card)

        dead_stock_days = card.dp_dead_stock_days or 45

        # Collect unique product template IDs from log lines
        product_variant_ids = list({
            line.dp_product_id.id
            for line in latest_log.line_ids
            if line.dp_product_id
        })
        # Get live stock status for all products in the log
        stock_data = card._dp_get_live_stock(product_variant_ids)

        # Build product rows and alert collections
        product_rows = []
        alerts = {
            'negative_margin': [],
            'dead_stock': [],
            'out_of_stock': [],
            'overstock': [],
        }

        # Group lines by product to show all segments per product
        lines_by_product = defaultdict(list)
        for line in latest_log.line_ids:
            if line.dp_product_id:
                lines_by_product[line.dp_product_id.id].append(line)

        for product_variant_id, lines in lines_by_product.items():
            product = lines[0].dp_product_id
            cost = product.standard_price or 0.0
            original_price = product.lst_price or 0.0
            category = product.categ_id.complete_name or 'Uncategorized'
            stock = stock_data.get(product_variant_id, {'status': 'unknown', 'qty': 0.0})

            alert_flags = []
            if cost > 0 and original_price > 0 and original_price < cost:
                alert_flags.append('negative_margin')
                alerts['negative_margin'].append(product.name)
            if stock['status'] == 'out_of_stock':
                alert_flags.append('out_of_stock')
                alerts['out_of_stock'].append(product.name)
            if stock['status'] == 'overstock':
                alert_flags.append('overstock')
                alerts['overstock'].append(product.name)

            for line in lines:
                ai_price = line.dp_ai_suggested_price or 0.0
                old_price = line.dp_old_price or original_price
                price_delta = round(ai_price - old_price, 2) if ai_price > 0 else 0.0
                price_delta_pct = round(
                    price_delta / old_price * 100, 2
                ) if old_price > 0 and ai_price > 0 else 0.0

                product_rows.append({
                    'product_id': product_variant_id,
                    'product_name': line.dp_product_name or product.name,
                    'category': category,
                    'cost_price': round(cost, 2),
                    'original_price': round(old_price, 2),
                    'ai_price': round(ai_price, 2),
                    'ai_price_active': bool(ai_price and line.dp_decision not in ('hold', 'skip')),
                    'segment': line.dp_segment_name or '',
                    'decision': line.dp_decision or 'hold',
                    'price_delta': price_delta,
                    'price_delta_pct': price_delta_pct,
                    'margin_before': round(line.dp_margin_before or 0.0, 2),
                    'margin_after': round(line.dp_margin_after or 0.0, 2),
                    'margin_delta': round(
                        (line.dp_margin_after or 0.0) - (line.dp_margin_before or 0.0), 2
                    ),
                    'stock_status': stock['status'],
                    'qty_on_hand': stock['qty'],
                    'alert_flags': alert_flags,
                    'log_line_status': line.dp_status or 'success',
                })

        # Summary KPIs
        ai_active_rows = [r for r in product_rows if r['ai_price_active']]
        unique_products = len(lines_by_product)
        avg_margin_before = round(
            sum(r['margin_before'] for r in product_rows) / len(product_rows), 2
        ) if product_rows else 0.0
        avg_margin_after = round(
            sum(r['margin_after'] for r in ai_active_rows) / len(ai_active_rows), 2
        ) if ai_active_rows else 0.0

        summary = {
            'total_products': unique_products,
            'total_rows': len(product_rows),
            'ai_priced_products': len(ai_active_rows),
            'avg_margin_before': avg_margin_before,
            'avg_margin_after': avg_margin_after,
            'avg_margin_lift': round(avg_margin_after - avg_margin_before, 2),
            'increase_count': sum(1 for r in product_rows if r['decision'] == 'increase'),
            'decrease_count': sum(1 for r in product_rows if r['decision'] == 'decrease'),
            'hold_count': sum(1 for r in product_rows if r['decision'] == 'hold'),
            'skip_count': sum(1 for r in product_rows if r['decision'] == 'skip'),
            'negative_margin_count': len(alerts['negative_margin']),
            'dead_stock_count': len(alerts['dead_stock']),
            'out_of_stock_count': len(alerts['out_of_stock']),
            'overstock_count': len(alerts['overstock']),
            'pricelists_updated': latest_log.dp_pricelists_updated or 0,
            'total_tokens': latest_log.dp_total_tokens or 0,
        }

        return {
            'card': {
                'id': card.id,
                'name': card.vraja_common_card_name,
                'status': card.dp_status,
                'analyzed_on': str(card.dp_analyzed_on) if card.dp_analyzed_on else '',
                'applied_on': str(latest_log.create_date)[:16] if latest_log.create_date else '',
                'dead_stock_days': dead_stock_days,
                'log_id': latest_log.id,
            },
            'currency': self.env.company.currency_id.name or 'USD',
            'summary': summary,
            'product_rows': product_rows,
            'alerts': alerts,
            'segment_data': card._dp_get_segment_performance(),
        }

    def _dp_empty_dashboard(self, card):
        """Returns an empty dashboard structure when no log data is available."""
        return {
            'card': {'id': card.id, 'name': card.vraja_common_card_name,
                     'status': card.dp_status, 'analyzed_on': ''},
            'currency': self.env.company.currency_id.name or 'USD',
            'filters': {},
            'summary': {},
            'product_rows': [],
            'alerts': {},
            'segment_data': [],
        }

    def _dp_get_live_stock(self, product_variant_ids):
        """
        Returns {product_template_id: {status, qty}} for all given products.
        Uses stock.quant for quantity and stock.warehouse.orderpoint for reorder levels.
        """
        result = {}
        quants = self.env['stock.quant'].sudo().search([
            ('product_id', 'in', product_variant_ids),
            ('location_id.usage', '=', 'internal'),
        ])
        qty_map = {}
        for q in quants:
            qty_map[q.product_id.id] = qty_map.get(q.product_id.id, 0.0) + q.quantity

        orderpoints = self.env['stock.warehouse.orderpoint'].sudo().search([
            ('product_id', 'in', product_variant_ids),
        ])
        reorder_map = {op.product_id.id: op.product_min_qty for op in orderpoints}

        for pid in product_variant_ids:
            qty = round(qty_map.get(pid, 0.0), 2)
            reorder = reorder_map.get(pid, 10.0)
            if qty <= 0:
                status = 'out_of_stock'
            elif qty < reorder:
                status = 'low_stock'
            elif qty <= reorder * 3:
                status = 'in_stock'
            else:
                status = 'overstock'
            result[pid] = {'status': status, 'qty': qty}
        return result



    def _dp_get_segment_performance(self):
        """
        Returns segment performance metrics from the latest applied log.
        Groups log lines by segment and computes: product count, decision distribution,
        avg margin before/after, and margin improvement.
        """
        self.ensure_one()
        latest_log = self.env['vraja.ai.log'].sudo().search([
            ('vraja_common_log_store', '=', 'dynamic_pricing'),
            ('dp_applied', '=', True),
        ], order='create_date desc', limit=1)

        if not latest_log:
            return []

        segments = defaultdict(lambda: {
            'products': 0, 'increase': 0, 'decrease': 0, 'hold': 0, 'skip': 0,
            'margin_before_sum': 0.0, 'margin_after_sum': 0.0,
        })

        for line in latest_log.line_ids:
            seg = line.dp_segment_name or 'Unknown'
            s = segments[seg]
            s['products'] += 1
            decision = line.dp_decision
            if decision in ('increase', 'decrease', 'hold', 'skip'):
                s[decision] += 1
            s['margin_before_sum'] += line.dp_margin_before or 0.0
            s['margin_after_sum'] += line.dp_margin_after or 0.0

        result = []
        for seg_name, s in segments.items():
            count = s['products'] or 1
            result.append({
                'segment_name': seg_name,
                'products': s['products'],
                'increase': s['increase'],
                'decrease': s['decrease'],
                'hold': s['hold'],
                'skip': s['skip'],
                'avg_margin_before': round(s['margin_before_sum'] / count, 2),
                'avg_margin_after': round(s['margin_after_sum'] / count, 2),
                'margin_improvement': round(
                    (s['margin_after_sum'] - s['margin_before_sum']) / count, 2
                ),
            })
        return sorted(result, key=lambda x: x['products'], reverse=True)
