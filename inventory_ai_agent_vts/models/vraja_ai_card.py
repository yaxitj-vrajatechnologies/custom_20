from odoo import models, api, fields, _
import io
import csv
import requests
from collections import defaultdict
import json
from datetime import datetime, timedelta
from openpyxl import Workbook
from openpyxl.styles import Font
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger("Inventory AI Agent----")

OPENAI_API_BASE_URL = 'https://api.openai.com/v1'


class VrajaAICard(models.Model):
    _inherit = 'vraja.ai.card'

    vraja_common_store = fields.Selection(selection_add=[('ai_low_stock', 'Low Stock')])
    ai_low_stock_instruction = fields.Text("Instructions")
    ai_low_stock_default_prompt = fields.Text("Default Prompt")
    ai_low_stock_attachment_id = fields.Many2one('ir.attachment', string='Stock File', readonly=True)
    ai_low_stock_analysis_result = fields.Text(string='AI Analysis Result', readonly=True)
    ai_low_stock_analysis_error = fields.Text(string='AI Analysis Error', readonly=True)
    ai_low_stock_auto_create_rfq = fields.Boolean(default=False)
    ai_low_stock_company_information = fields.Text('Company Details')
    minimum_stock_threshold = fields.Integer(string='Minimum Stock Threshold', default=10, )
    forecast_period = fields.Selection([('all_data', 'All Time Data'), ('selected_data', 'Preferred Data'), ],
                                       string='Sales Forecast Period', default='selected_data')
    sale_forecast_days = fields.Integer(string='Forecast Days', default=30)
    purchase_forecast_period = fields.Selection([('all_data', 'All Time Data'), ('selected_data', 'Preferred Data'), ],
                                                string='Purchase Forecast Period', default='all_data')
    purchase_forecast_days = fields.Integer(string='Forecast Days', default=30)
    # Datetime
    ai_low_stock_analyzed_on = fields.Datetime(string='AI Analyzed On', readonly=True)

    def action_review_dashboard(self):
        action = super().action_review_dashboard()
        self.ensure_one()
        if self.vraja_common_store == 'ai_low_stock':
            action['tag'] = 'inventory_low_stock_dashboard_template'
            action['name'] = _('AI Inventory Dashboard')

        # EXISTING PARAMS
        params = action.get('params', {})

        # UPDATE PARAMS
        params.update({
            'vraja_common_store': self.vraja_common_store,
            'ai_low_stock_company_information': self.ai_low_stock_company_information,
            'ai_low_stock_instruction': self.ai_low_stock_instruction,
            'ai_low_stock_default_prompt': self.ai_low_stock_default_prompt,
            'ai_low_stock_analysis_result': self.ai_low_stock_analysis_result,
            'ai_low_stock_analysis_error': self.ai_low_stock_analysis_error,
            'ai_low_stock_analyzed_on': self.ai_low_stock_analyzed_on,
            'minimum_stock_threshold': self.minimum_stock_threshold,
            'forecast_period': self.forecast_period,
            'sale_forecast_days': self.sale_forecast_days,
            'purchase_forecast_period': self.purchase_forecast_period,
            'purchase_forecast_days': self.purchase_forecast_days,
            'ai_low_stock_auto_create_rfq': self.ai_low_stock_auto_create_rfq,

            'ai_low_stock_attachment_id': (
                self.ai_low_stock_attachment_id.id
                if self.ai_low_stock_attachment_id
                else False
            ),

            'stock_attachment_name': (
                self.ai_low_stock_attachment_id.name
                if self.ai_low_stock_attachment_id
                else False
            ),
        })

        action['params'] = params

        return action

    def action_log_view(self):
        action = super().action_log_view()
        if self.vraja_common_store == 'ai_low_stock':
            action['name'] = 'Inventory AI Logs'
            action['views'] = [
                (False, 'list'),
                (self.env.ref('inventory_ai_agent_vts.inventory_ai_log_form_vts').id, 'form'),
            ]
            action['domain'] = [('vraja_common_log_store', '=', 'ai_low_stock')]
            action['context'] = {
                **action.get('context', {}),
                'search_default_filter_inventory_ai': 1,
                'create': False,
            }
        return action

    @api.model
    def _default_ai_instruction(self):
        return """
You are an inventory replenishment assistant for an Odoo database.

Use the uploaded workbook to review stock, sales, and purchase history.
Prepare restocking recommendations for products that need a purchase RFQ.
Return a CSV response with the configured columns.
""".strip()

    @api.model
    def _default_ai_prompt(self):
        return self._build_inventory_ai_prompt()

    def _build_inventory_ai_prompt(self):
        """
        Build a controlled prompt for the OpenAI request.

        The dashboard prompt/company fields are editable, so the API request
        uses only validated configuration values to avoid prompt validation
        failures caused by arbitrary saved text.
        """
        record = self[:1]
        minimum_stock_threshold = record.minimum_stock_threshold if record else 10
        forecast_period = record.forecast_period if record else 'selected_data'
        sale_forecast_days = record.sale_forecast_days if record else 30
        purchase_forecast_period = record.purchase_forecast_period if record else 'all_data'
        purchase_forecast_days = record.purchase_forecast_days if record else 30

        forecast_note = (
            f"Use recent sales rows for approximately {sale_forecast_days or 0} days."
            if forecast_period == 'selected_data'
            else "Use the available sales history in the workbook."
        )
        purchase_note = (
            f"Use recent purchase rows for approximately {purchase_forecast_days or 0} days."
            if purchase_forecast_period == 'selected_data'
            else "Use the available purchase history in the workbook."
        )

        return f"""
Review the uploaded inventory workbook. It contains stock, sales, purchase, and vendor pricelist sheets.

Configuration:
- Minimum stock threshold: {int(minimum_stock_threshold or 0)}
- Sales forecast mode: {forecast_period or "all_data"}
- {forecast_note}
- Purchase history mode: {purchase_forecast_period or "all_data"}
- {purchase_note}

Task:
- Use product_id and product_sku from the workbook when matching rows.
- Use available_stock from the stock sheet as provided.
- Estimate average_daily_sales from the sales sheet.
- Estimate forecasted_demand for the selected sales period.
- Recommend a purchase quantity when forecasted_demand is greater than available_stock.
- Select a vendor using purchase history signals such as lead time, delay, reliability, and price.
- Vendor selection priority for every product:
  1. If the product has rows in the Purchase Data sheet, choose the vendor with the lowest average_received_lead_time_days (fastest delivery). If two vendors have the same average_received_lead_time_days or 0, choose the vendor with the highest total_purchase_orders for that product.
  2. If the product has no rows in the Purchase Data sheet, choose the vendor from the Vendor Pricelist sheet with the lowest lead_time_days (fastest delivery). If lead_time_days is the same, then the lowest vendor_price.
  3. Use vendor_id and vendor exactly as given in the workbook, and always fill recommended_vendor_id and recommended_vendor when a vendor exists.
- Include rows only when a purchase RFQ is recommended.

Return CSV text with this exact header:
product_id,product,product_sku,recommended_vendor_id,recommended_vendor,available_stock,forecasted_demand,recommended_order_qty,decision,reason

For recommended rows, set decision to CREATE_RFQ.
Return plain CSV text only, without markdown formatting.
""".strip()

    def _create_find_stock_record(self):
        """
        Create or fetch single inventory AI record.
        """
        stock_record = self.search([], order='id', limit=1)
        if not stock_record:
            stock_record = self.create(
                {'vraja_common_card_name': 'Low Stock Alert',
                 'vraja_common_card_description': 'It will calculate stock data and sales performance & show the products to be restocked with better vendor details.',
                 'ai_low_stock_instruction': self._default_ai_instruction(),
                 'ai_low_stock_default_prompt': self._default_ai_prompt(),
                 'vraja_common_card_active': True,
                 'vraja_common_store': 'ai_low_stock',
                 })
        return stock_record

    @api.model
    def action_ai_inventory_get_default_card_id(self):
        """Return the inventory card id so the dashboard can recover after refresh."""
        return self.sudo()._create_find_stock_record().id

    def generate_ai_inventory_file(self):
        """
        Generate inventory workbook with:
        - Stock Data
        - Sales Data
        - Purchase Data
        """
        if self.env.context.get('from_cron'):
            stock_record = self._create_find_stock_record()
        else:
            self.ensure_one()
            stock_record = self

        # LOAD OR CREATE WORKBOOK
        if stock_record.ai_low_stock_attachment_id:
            stock_record.ai_low_stock_attachment_id.unlink()

        workbook = Workbook()
        if workbook.active:
            workbook.remove(workbook.active)

        # HANDLE SHEETS
        _logger.info("Prepared Stock Data")
        self._prepare_stock_sheet(workbook)

        _logger.info("Prepared Sales Data")
        self._prepare_sales_sheet(workbook)

        _logger.info("Prepared Purchase Data")
        self._prepare_purchase_sheet(workbook)

        _logger.info("Prepared Vendor Pricelist Data")
        self._prepare_vendor_pricelist_sheet(workbook)

        # SAVE FILE
        self._apply_auto_width(workbook)
        output = io.BytesIO()
        workbook.save(output)
        output.seek(0)

        attachment = self.env['ir.attachment'].create({
            'name': stock_record.vraja_common_card_name,
            'type': 'binary',
            'raw': output.read(),
            'mimetype':
                'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            'res_model': stock_record._name,
            'res_id': stock_record.id,
        })

        stock_record.write({'ai_low_stock_attachment_id': attachment.id})

        return stock_record

    # STOCK SHEET
    def _prepare_stock_sheet(self, workbook):
        """
        Prepare stock data sheet.
        """
        headers = [
            'product_id',
            'product_name',
            'product_sku',
            'current_stock',
            'incoming_stock',
            'outgoing_stock',
            'available_stock',
            'updated_on',
        ]

        if 'Stock Data' in workbook.sheetnames:
            del workbook['Stock Data']

        sheet = workbook.create_sheet('Stock Data')
        sheet.append(headers)

        for cell in sheet[1]:
            cell.font = Font(bold=True)

        # STOCK DATA
        products = self.env['product.product'].search([('type', '=', 'consu'), ('active', '=', True)])

        for product in products:
            sku = product.default_code or product.barcode or product.name

            sheet.append([
                product.id,
                product.name,
                sku,
                product.qty_available,
                product.incoming_qty,
                product.outgoing_qty,
                (product.qty_available + product.incoming_qty - product.outgoing_qty),
                datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            ])

    # SALES SHEET
    def _prepare_sales_sheet(self, workbook):
        """
        Prepare aggregated sales history sheet.

        Forecast Logic:
        ----------------
        - all_data:
            Export complete sales history.

        - selected_data:
            Export only recent sales data based on
            configured forecast days.

        Aggregation Logic:
        ------------------
        Combine all sales lines into single product SKU row.

        Example:
            Product A sold:
                Customer 1 -> 20
                Customer 2 -> 15
                Customer 3 -> 5

            Final Export:
                Product A -> 40 Qty
        """

        headers = [
            'product_id',
            'product_name',
            'product_sku',
            'total_sale_qty',
            'total_sale_orders',
            'first_sale_date',
            'last_sale_date',
            'company',
            'forecast_period',
            'forecast_days',
            'exported_on',
        ]

        # GET / CREATE SHEET
        if 'Sales Data' in workbook.sheetnames:
            del workbook['Sales Data']

        sheet = workbook.create_sheet('Sales Data')
        sheet.append(headers)

        for cell in sheet[1]:
            cell.font = Font(bold=True)

        # PREPARE DOMAIN
        domain = [
            ('order_id.state', 'in', ['sale', 'done']),
            ('product_id.type', '=', 'consu')
        ]

        forecast_period = self.forecast_period or 'all_data'
        forecast_days = self.sale_forecast_days or 0

        # FILTER SALES USING FORECAST PERIOD
        if forecast_period == 'selected_data' and forecast_days > 0:
            from_date = datetime.now() - timedelta(days=forecast_days)
            domain.append(('order_id.date_order', '>=', fields.Datetime.to_string(from_date)))

        # FETCH SALES LINES
        sale_lines = self.env['sale.order.line'].search(domain)

        # GROUP SALES BY PRODUCT SKU
        grouped_products = {}

        for line in sale_lines:
            product = line.product_id
            sku = product.default_code or product.barcode or product.display_name

            if sku not in grouped_products:
                grouped_products[sku] = {
                    'product_id': product.id,
                    'product_name': product.name,
                    'product_sku': sku,
                    'total_sale_qty': 0.0,
                    'sale_orders': set(),
                    'first_sale_date': line.order_id.date_order,
                    'last_sale_date': line.order_id.date_order,
                    'company': line.order_id.company_id.name,
                }

            # TOTAL SALE QTY
            grouped_products[sku]['total_sale_qty'] += line.product_uom_qty

            # UNIQUE SALE ORDERS
            grouped_products[sku]['sale_orders'].add(line.order_id.id)

            # FIRST SALE DATE
            if line.order_id.date_order and line.order_id.date_order < grouped_products[sku]['first_sale_date']:
                grouped_products[sku]['first_sale_date'] = line.order_id.date_order

            # LAST SALE DATE
            if line.order_id.date_order and line.order_id.date_order > grouped_products[sku]['last_sale_date']:
                grouped_products[sku]['last_sale_date'] = line.order_id.date_order

        # APPEND FINAL DATA
        for data in grouped_products.values():
            sheet.append([
                data['product_id'],
                data['product_name'],
                data['product_sku'],
                data['total_sale_qty'],
                len(data['sale_orders']),
                data['first_sale_date'],
                data['last_sale_date'],
                data['company'],
                forecast_period,
                (
                    forecast_days
                    if forecast_period == 'selected_data'
                    else 'ALL'
                ),
                datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            ])

    # PURCHASE SHEET
    def _prepare_purchase_sheet(self, workbook):
        """
        Prepare aggregated purchase/vendor performance sheet.

        This sheet stores one line per:
            Product SKU + Vendor

        Multiple purchase lines are merged together to provide:
        - total purchased quantity
        - average price
        - lead time analysis
        - vendor performance
        """
        headers = [
            'product_id',
            'product_name',
            'product_sku',
            'vendor',
            'vendor_id',
            'total_purchase_qty',
            'total_purchase_amount',
            'average_price_unit',
            'total_purchase_orders',
            'first_purchase_date',
            'last_purchase_date',
            'average_lead_time_days',
            'average_delay_days',
            'vendor_reliability',
            'company',
            'exported_on',
            'received_orders',
            'average_received_lead_time_days',
        ]

        # GET / CREATE SHEET
        if 'Purchase Data' in workbook.sheetnames:
            del workbook['Purchase Data']

        sheet = workbook.create_sheet('Purchase Data')
        sheet.append(headers)

        for cell in sheet[1]:
            cell.font = Font(bold=True)

        domain = [
            ('order_id.state', 'in', ['purchase', 'done']),
            ('product_id.type', '=', 'consu'),
        ]

        # OPTIONAL PURCHASE FORECAST FILTER
        if self.purchase_forecast_period == 'selected_data' and self.purchase_forecast_days:
            from_date = datetime.now() - timedelta(days=self.purchase_forecast_days)
            domain.append(('order_id.date_order', '>=', fields.Datetime.to_string(from_date)))

        # FETCH PURCHASE DATA
        purchase_lines = self.env['purchase.order.line'].search(domain)

        # GROUP PURCHASE DATA
        grouped_products = {}

        for line in purchase_lines:

            product = line.product_id
            vendor = line.order_id.partner_id

            sku = product.default_code or product.barcode or product.name

            key = f'{sku}_{vendor.id}'

            receipt = line.order_id.picking_ids.filtered(lambda p: p.state == 'done')[:1]

            receipt_date = receipt.date_done if receipt else False

            lead_time = 0
            delay_days = 0

            if receipt_date:
                lead_time = (receipt_date.date() - line.order_id.date_order.date()).days

                delay_days = (receipt_date.date() - line.date_planned.date()).days

                if delay_days < 0:
                    delay_days = 0

            # CREATE INITIAL DATA
            if key not in grouped_products:
                grouped_products[key] = {
                    'product_id': product.id,
                    'product_name': product.name,
                    'product_sku': sku,
                    'vendor': vendor.name,
                    'vendor_id': vendor.id,
                    'total_purchase_qty': 0.0,
                    'total_purchase_amount': 0.0,
                    'price_units': [],
                    'purchase_orders': set(),
                    'lead_times': [],
                    'delay_days': [],
                    'received_lead_times': [],
                    'first_purchase_date': line.order_id.date_order,
                    'last_purchase_date': line.order_id.date_order,
                    'company': line.order_id.company_id.name,
                }

            grouped_products[key]['total_purchase_qty'] += line.product_qty

            grouped_products[key]['total_purchase_amount'] += line.price_subtotal

            grouped_products[key]['price_units'].append(line.price_unit)

            grouped_products[key]['purchase_orders'].add(line.order_id.id)

            grouped_products[key]['lead_times'].append(lead_time)

            # ONLY RECEIVED LINES HAVE A REAL LEAD TIME
            if receipt_date:
                grouped_products[key]['received_lead_times'].append(lead_time)

            grouped_products[key]['delay_days'].append(delay_days)

            # UPDATE FIRST PURCHASE DATE
            if line.order_id.date_order and line.order_id.date_order < grouped_products[key]['first_purchase_date']:
                grouped_products[key]['first_purchase_date'] = line.order_id.date_order

            # UPDATE LAST PURCHASE DATE
            if line.order_id.date_order and line.order_id.date_order > grouped_products[key]['last_purchase_date']:
                grouped_products[key]['last_purchase_date'] = line.order_id.date_order

        # APPEND FINAL DATA
        for data in grouped_products.values():

            avg_price = (
                sum(data['price_units']) / len(data['price_units'])
                if data['price_units']
                else 0
            )

            avg_lead = (
                sum(data['lead_times']) / len(data['lead_times'])
                if data['lead_times']
                else 0
            )

            avg_delay = (
                sum(data['delay_days']) / len(data['delay_days'])
                if data['delay_days']
                else 0
            )

            # AVERAGE LEAD TIME OF RECEIVED ORDERS ONLY (blank when nothing received yet)
            avg_received_lead = (
                round(sum(data['received_lead_times']) / len(data['received_lead_times']), 2)
                if data['received_lead_times']
                else None
            )

            # SIMPLE RELIABILITY %
            reliability = 100

            if avg_delay > 0:
                reliability = max(0, 100 - (avg_delay * 10))

            sheet.append([
                data['product_id'],
                data['product_name'],
                data['product_sku'],
                data['vendor'],
                data['vendor_id'],
                data['total_purchase_qty'],
                data['total_purchase_amount'],
                round(avg_price, 2),
                len(data['purchase_orders']),
                data['first_purchase_date'],
                data['last_purchase_date'],
                round(avg_lead, 2),
                round(avg_delay, 2),
                f'{round(reliability, 2)}%',
                data['company'],
                datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                len(data['received_lead_times']),
                avg_received_lead,
            ])

    # VENDOR PRICELIST SHEET
    def _prepare_vendor_pricelist_sheet(self, workbook):
        """
        Prepare vendor pricelist sheet from the vendors configured on products
        (Purchase tab > Vendors / product.supplierinfo). Used as the last option
        for vendor selection when a product has no purchase history.
        """
        headers = [
            'product_id',
            'product_name',
            'product_sku',
            'vendor',
            'vendor_id',
            'vendor_priority',
            'vendor_price',
            'min_qty',
            'lead_time_days',
            'exported_on',
        ]

        if 'Vendor Pricelist' in workbook.sheetnames:
            del workbook['Vendor Pricelist']

        sheet = workbook.create_sheet('Vendor Pricelist')
        sheet.append(headers)

        for cell in sheet[1]:
            cell.font = Font(bold=True)

        products = self.env['product.product'].search([('type', '=', 'consu'), ('active', '=', True)])
        today = fields.Date.context_today(self)
        exported_on = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        for product in products:
            sellers = product.product_tmpl_id.seller_ids.filtered(
                lambda s: s.partner_id
                and (not s.product_id or s.product_id == product)
                and (not s.date_start or s.date_start <= today)
                and (not s.date_end or s.date_end >= today)
            ).sorted(lambda s: (s.sequence, s.min_qty, s.price))

            sku = product.default_code or product.barcode or product.name

            for priority, seller in enumerate(sellers, start=1):
                sheet.append([
                    product.id,
                    product.name,
                    sku,
                    seller.partner_id.name,
                    seller.partner_id.id,
                    priority,
                    seller.price,
                    seller.min_qty,
                    seller.delay,
                    exported_on,
                ])

    def _apply_auto_width(self, workbook):
        """
        Auto apply width on all workbook sheets.
        """
        for sheet in workbook.worksheets:
            for column_cells in sheet.columns:
                length = max(len(str(cell.value or '')) for cell in column_cells)
                sheet.column_dimensions[column_cells[0].column_letter].width = length + 5

    def action_run_inventory_ai_analysis(self):
        """
        Button action to run AI inventory analysis.
        """
        self.ensure_one()
        result = self.sudo()._analyze_inventory_with_ai(raise_on_error=False)
        message = 'AI Inventory Analysis Completed.' if result else 'AI Analysis Failed. Check Error Log.'

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Inventory AI Analysis',
                'message': message,
                'type': 'success' if result else 'danger',
                'sticky': False,
            },
        }

    def _get_ai_config(self):
        """Get AI provider config."""
        config = self.env['vraja.ai.config'].sudo().search([], limit=1)
        if not config:
            raise ValueError('AI configuration not found.')
        return config

    # MAIN AI FLOW
    def _analyze_inventory_with_ai(self, raise_on_error=True):
        """
        Main Inventory AI analysis Flow.
        """
        self.ensure_one()
        usages = {}
        try:
            # VALIDATION
            self._validate_ai_analysis_ready()

            # REQUEST AI ANALYSIS (OpenAI / Claude / Gemini)
            provider, response = self._call_inventory_ai_provider()
            _logger.info(f"AI response Data: {response}")
            usages = self._extract_inventory_usage(provider, response)
            _logger.info(f"AI Request Token Usage: {usages}")

            # EXTRACT RESULT
            result_text = self._extract_inventory_output_text(provider, response)

            _logger.info(f"AI response Text: {result_text}")
            if not result_text:
                # raise ValueError('OpenAI did not return analysis text.')
                raise ValueError(f'{provider} did not return analysis text.')

            # JSON RECORDS
            ai_records = self._extract_ai_json_records(result_text)
            _logger.info(f"AI response records: {ai_records}")
            if not ai_records:
                # raise ValueError('OpenAI response did not contain valid CSV recommendation rows.')
                raise ValueError(f'{provider} response did not contain valid CSV recommendation rows.')

            # PROCESS AI RESPONSE
            filtered_records = self._process_ai_analysis_result(ai_records)

            # STORE RESULT
            self.write({
                'ai_low_stock_analysis_result': json.dumps(filtered_records, indent=4),
                'ai_low_stock_analysis_error': False,
                'ai_low_stock_analyzed_on': datetime.now()
            })

            purchase_order_count = 0
            if self.env.context.get('from_cron') and self.ai_low_stock_auto_create_rfq:
                purchase_order_count = len(self._create_rfq_from_ai_records(filtered_records))

            self._create_inventory_ai_log(
                filtered_records, usages,
                status='success',
                purchase_order_count=purchase_order_count,
            )
            return True

        except Exception as error:
            _logger.exception('Failed Inventory AI Analysis')

            self.write({
                'ai_low_stock_analysis_result': False,
                'ai_low_stock_analysis_error': str(error),
            })
            self._create_inventory_ai_log([], usages, status='failed', error_message=str(error))
            if raise_on_error:
                raise
            return False

    # =================================================================================================================
                                        # below of the claude and gemini
    # =================================================================================================================
    def _convert_inventory_excel_to_csv_text(self):
        """Convert inventory Excel attachment to CSV text for Claude and Gemini."""
        self.ensure_one()
        if not self.ai_low_stock_attachment_id or not self.ai_low_stock_attachment_id.raw:
            raise ValueError('No Data File Found.')

        from io import BytesIO, StringIO
        import openpyxl as _openpyxl
        import csv as csv_module

        excel_bytes = self.ai_low_stock_attachment_id.raw
        workbook = _openpyxl.load_workbook(BytesIO(excel_bytes), data_only=True)

        output_parts = []
        for sheet_name in workbook.sheetnames:
            worksheet = workbook[sheet_name]
            output_parts.append(f"\n===== {sheet_name} =====")
            csv_buffer = StringIO()
            writer = csv_module.writer(csv_buffer)
            for row in worksheet.iter_rows(values_only=True):
                writer.writerow(['' if value is None else str(value) for value in row])
            output_parts.append(csv_buffer.getvalue())

        return "\n".join(output_parts)

    def _extract_inventory_output_text(self, provider, response):
        """Extract plain text from provider response."""
        if provider == 'openai':
            return self._extract_openai_output_text(response)

        elif provider == 'claude':
            text_blocks = [b for b in response.get('content', []) if b.get('type') == 'text']
            if not text_blocks:
                raise ValueError(
                    f"Claude returned no text block. "
                    f"stop_reason={response.get('stop_reason')}, "
                    f"content_types={[b.get('type') for b in response.get('content', [])]}"
                )
            return text_blocks[0]['text'].strip()

        elif provider == 'gemini':
            candidates = response.get('candidates', [])
            if not candidates:
                raise ValueError(f'Gemini returned no candidates. Response: {response}')
            parts = candidates[0].get('content', {}).get('parts', [])
            if not parts or 'text' not in parts[0]:
                raise ValueError(f'Gemini returned unexpected content structure: {candidates[0]}')
            return parts[0]['text'].strip()

        raise ValueError(f'Unknown provider: {provider}')

    def _extract_inventory_usage(self, provider, response):
        """Extract token usage from provider response."""
        if provider == 'openai':
            return response.get('usage', {})
        elif provider == 'claude':
            usage = response.get('usage', {})
            total = usage.get('input_tokens', 0) + usage.get('output_tokens', 0)
            return {'total_tokens': total}
        elif provider == 'gemini':
            total = response.get('usageMetadata', {}).get('totalTokenCount', 0)
            return {'total_tokens': total}
        return {}

    def _call_inventory_ai_provider(self):
        """
        Dispatch inventory AI analysis to the configured provider.
        Returns (provider, response_dict).
        """
        config = self._get_ai_config()
        provider = config.ai_provider or 'openai'
        instruction = self._default_ai_instruction()
        prompt = self._build_inventory_ai_prompt()

        if provider == 'openai':
            file_id = self._upload_attachment_to_openai()
            response = self._request_inventory_analysis(file_id)
            return provider, response

        elif provider == 'claude':
            api_key = (config.claude_api_key or '').strip()
            llm_model = config.claude_llm_model or 'claude-sonnet-4-6'
            csv_text = self._convert_inventory_excel_to_csv_text()
            combined_prompt = f"{prompt}\n\nINVENTORY DATA (from Excel, converted to CSV):\n{csv_text}"
            response = requests.post(
                'https://api.anthropic.com/v1/messages',
                headers={
                    'x-api-key': api_key,
                    'anthropic-version': '2023-06-01',
                    'content-type': 'application/json',
                },
                json={
                    'model': llm_model,
                    'max_tokens': config.claude_max_tokens or 8192,
                    'system': instruction,
                    'messages': [{'role': 'user', 'content': combined_prompt}],
                },
                timeout=300,
            )
            if response.status_code >= 400:
                raise ValueError(f'Claude API Error {response.status_code}: {response.text}')
            return provider, response.json()

        elif provider == 'gemini':
            api_key = (config.gemini_api_key or '').strip()
            llm_model = config.gemini_llm_model or 'gemini-flash-latest'
            csv_text = self._convert_inventory_excel_to_csv_text()
            combined_prompt = f"{prompt}\n\nINVENTORY DATA (from Excel, converted to CSV):\n{csv_text}"
            response = requests.post(
                f'https://generativelanguage.googleapis.com/v1beta/models/{llm_model}:generateContent?key={api_key}',
                headers={'Content-Type': 'application/json'},
                json={
                    'system_instruction': {'parts': [{'text': instruction}]},
                    'contents': [{'parts': [{'text': combined_prompt}]}],
                    'generationConfig': {'responseMimeType': 'text/plain'},
                },
                timeout=300,
            )
            if response.status_code >= 400:
                raise ValueError(f'Gemini API Error {response.status_code}: {response.text}')
            return provider, response.json()

        else:
            raise ValueError(f'Unsupported AI provider: {provider}')
  # =================================================================================================================
                                        # above of the claude and gemin
    # =================================================================================================================
    def _create_inventory_ai_log(self, records, usages, status='success', error_message=False, purchase_order_count=0):
        """
        Store inventory AI run details in the shared Vraja AI log model.
        """
        line_vals = []

        for record in records:
            vendor_id = record.get('recommended_vendor_id') or False
            vendor = self.env['res.partner'].browse(int(vendor_id)).exists() if vendor_id else False
            product = self.env['product.product'].browse(record.get('product_id')).exists()

            line_vals.append({
                'inventory_ai_product_id': product.id if product else False,
                'inventory_ai_product_name': record.get('product') or (product.display_name if product else ''),
                'inventory_ai_product_sku': record.get('product_sku') or '',
                'inventory_ai_recommended_order_qty': record.get('recommended_order_qty') or 0.0,
                'inventory_ai_recommended_vendor_id': vendor.id if vendor else False,
                'inventory_ai_recommended_vendor_name': record.get('recommended_vendor') or (
                    vendor.display_name if vendor else ''),
                'inventory_ai_vendor_lead_time_days': record.get('vendor_lead_time_days') or 0.0,
                'inventory_ai_vendor_reliability': record.get('vendor_reliability') or '',
                'inventory_ai_decision': record.get('decision') or '',
                'inventory_ai_reason': record.get('reason') or '',
                'inventory_ai_available_stock': record.get('available_stock') or '',
                'inventory_ai_forecasted_demand': record.get('forecasted_demand') or '',
            })

        return self.env['vraja.ai.log'].sudo().create({
            'vraja_common_log_store': 'ai_low_stock',
            'status': status,
            'inventory_ai_token_usage': usages.get('total_tokens'),
            'inventory_ai_minimum_stock_threshold': self.minimum_stock_threshold,
            'inventory_ai_forecast_period': self.forecast_period,
            'inventory_ai_sale_forecast_days': self.sale_forecast_days,
            'inventory_ai_purchase_forecast_period': self.purchase_forecast_period,
            'inventory_ai_purchase_forecast_days': self.purchase_forecast_days,
            'inventory_ai_auto_create_rfq': self.ai_low_stock_auto_create_rfq,
            'inventory_ai_total_products': len(records),
            'inventory_ai_total_order_qty': sum(record.get('recommended_order_qty') or 0.0 for record in records),
            'inventory_ai_purchase_order_count': purchase_order_count,
            'inventory_ai_error': error_message or False,
            'line_ids': [(0, 0, line) for line in line_vals],
        })

    # VALIDATION
    def _validate_ai_analysis_ready(self):
        """
        Validate AI configuration and workbook.
        """
        config = self._get_ai_config()
        provider = config.ai_provider or 'openai'

        if provider == 'openai' and not (config.openai_api_key and config.llm_model):
            raise ValueError('Missing OpenAI API Key or model.')
        elif provider == 'claude' and not ((config.claude_api_key or '').strip() and config.claude_llm_model):
            raise ValueError('Claude API key or model is not configured.')
        elif provider == 'gemini' and not ((config.gemini_api_key or '').strip() and config.gemini_llm_model):
            raise ValueError('Gemini API key or model is not configured.')

        if not self.ai_low_stock_attachment_id or not self.ai_low_stock_attachment_id.raw:
            raise ValueError('No Data File Found.')

    def _has_generated_inventory_file_for_cron(self):
        """
        Cron analysis should only run when a generated Excel file exists.
        """
        self.ensure_one()
        attachment = self.ai_low_stock_attachment_id
        return bool(attachment and attachment.raw)

    # UPLOAD FILE
    def _upload_attachment_to_openai(self):
        """
        Upload workbook to OpenAI.
        """
        config = self._get_ai_config()
        api_key = config.openai_api_key
        filename = self.ai_low_stock_attachment_id.name or self.vraja_common_card_name or 'low_stock_analysis.xlsx'
        file_data = self.ai_low_stock_attachment_id.raw
        response = requests.post(
            f'{OPENAI_API_BASE_URL}/files',
            headers={'Authorization': f'Bearer {api_key}'},
            data={'purpose': 'user_data'},
            files={
                'file': (
                    filename,
                    file_data,
                    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                ),
            },
            timeout=120,
        )

        self._raise_openai_for_status(response)

        return response.json()['id']

    # OPENAI REQUEST
    def _request_inventory_analysis(self, file_id):
        """
        Request OpenAI Inventory Analysis.
        """
        config = self._get_ai_config()
        api_key = config.openai_api_key
        api_model = config.llm_model
        response = requests.post(
            f'{OPENAI_API_BASE_URL}/responses',
            headers={
                'Authorization': f'Bearer {api_key}',
                'Content-Type': 'application/json',
            },
            json={
                'model': api_model,
                'tools': [{
                    'type': 'code_interpreter',
                    'container': {
                        'type': 'auto',
                        'memory_limit': '4g',
                        'file_ids': [file_id],
                    },
                }],
                'tool_choice': 'required',
                'instructions': self._default_ai_instruction(),
                'input': self._build_inventory_ai_prompt(),
            },
            timeout=300,
        )

        self._raise_openai_for_status(response)
        return response.json()

    def _raise_openai_for_status(self, response):
        """
        Raise formatted OpenAI API errors.
        """
        if response.status_code < 400:
            return
        try:
            error_payload = response.json()
            error_message = (error_payload.get('error', {}).get('message') or response.text)

        except ValueError:
            error_message = response.text

        raise ValueError(f'OpenAI API Error {response.status_code}: {error_message}')

    # EXTRACT RESPONSE TEXT
    def _extract_openai_output_text(self, response):
        """
       Extract output text from OpenAI response.
       """
        if response.get('output_text'):
            return response['output_text']

        output_parts = []

        for item in response.get('output', []):
            if item.get('type') != 'message':
                continue

            for content in item.get('content', []):
                if content.get('type') == 'output_text' and content.get('text'):
                    output_parts.append(content['text'])

        return '\n'.join(output_parts)

    def _process_ai_analysis_result(self, ai_records):
        filtered_records = []

        for record in ai_records:

            # Only RFQ products
            if record.get('decision') != 'CREATE_RFQ':
                continue

            product = self.env['product.product'].browse(record.get('product_id'))

            if not product.exists():
                continue

            filtered_records.append(record)

        return filtered_records

    def _extract_ai_json_records(self, response_text):
        """
        Extract AI CSV response into Python records.
        """
        if not response_text:
            return []

        try:
            # CLEAN RESPONSE
            response_text = response_text.strip()

            # REMOVE MARKDOWN BLOCKS IF EXISTS
            response_text = response_text.replace('```csv', '')
            response_text = response_text.replace('```', '')

            # EXTRACT ONLY CSV PART — find the header line
            csv_header = 'product_id,product,product_sku'
            lines = response_text.splitlines()
            csv_start_index = None

            for i, line in enumerate(lines):
                if line.strip().startswith(csv_header):
                    csv_start_index = i
                    break

            if csv_start_index is None:
                _logger.warning("Could not find CSV header in AI response")
                return []

            # TAKE ONLY CSV LINES FROM HEADER ONWARDS
            csv_lines = lines[csv_start_index:]
            response_text = '\n'.join(csv_lines)

            # CONVERT CSV TEXT TO STREAM
            csv_file = io.StringIO(response_text)

            # READ CSV
            reader = csv.DictReader(csv_file)

            records = []

            for row in reader:
                clean_record = {
                    'product_id': int(float(row.get('product_id') or 0)),
                    'product': row.get('product') or '',
                    'product_sku': row.get('product_sku') or '',
                    'warehouse': row.get('warehouse') or '',

                    'current_stock': float(row.get('current_stock') or 0),
                    'incoming_stock': float(row.get('incoming_stock') or 0),
                    'reserved_stock': float(row.get('reserved_stock') or 0),
                    'available_stock': float(row.get('available_stock') or 0),

                    'average_daily_sales': float(row.get('average_daily_sales') or 0),
                    'forecasted_demand': float(row.get('forecasted_demand') or 0),
                    'recommended_order_qty': float(row.get('recommended_order_qty') or 0),
                    'recommended_vendor': row.get('recommended_vendor') or '',
                    'recommended_vendor_id': int(float(row.get('recommended_vendor_id') or 0)),
                    'vendor_lead_time_days': float(row.get('vendor_lead_time_days') or 0),
                    'vendor_reliability': row.get('vendor_reliability') or '',
                    'decision': row.get('decision') or '',
                    'reason': row.get('reason') or '',
                }

                records.append(clean_record)

            return records

        except Exception as error:
            _logger.exception("Failed to parse AI CSV response")
            return []


    def _create_rfq_from_ai_records(self, ai_records, raise_if_empty=False):
        """
        Create RFQs from processed AI recommendation records.
        """
        grouped_vendors = defaultdict(list)
        products_without_vendor = []

        for record in ai_records:
            if record.get('decision') != 'CREATE_RFQ':
                continue

            product = self.env['product.product'].browse(record.get('product_id'))
            if not product.exists():
                continue

            vendor = False
            if record.get('recommended_vendor_id'):
                vendor = self.env['res.partner'].browse(int(record.get('recommended_vendor_id'))).exists()

            if not vendor and record.get('recommended_vendor'):
                vendor = self.env['res.partner'].search([('name', '=', record.get('recommended_vendor'))], limit=1)

            if record.get('recommended_order_qty', 0) <= 0:
                continue
            if not vendor:
                products_without_vendor.append(product.display_name)
                continue

            grouped_vendors[vendor.id].append({
                'product': product,
                'qty': record.get('recommended_order_qty'),
                'record': record,
            })

        if products_without_vendor:
            _logger.warning(
                "RFQ skipped, no vendor found for: %s", ', '.join(products_without_vendor))

        if not grouped_vendors:
            if raise_if_empty:
                if products_without_vendor:
                    raise UserError(_(
                        'No RFQ could be created because no vendor was found for: %s.\n'
                        'Add a vendor on these products (Purchase tab > Vendors) and try again.',
                        ', '.join(products_without_vendor)))
                raise UserError(_('No RFQ data found.'))
            return self.env['purchase.order']

        return self._create_bulk_rfq(grouped_vendors)

    # CREATE BULK RFQ
    def _create_bulk_rfq(self, grouped_vendors):
        """
        Create RFQs grouped by vendor.
        """
        PurchaseOrder = self.env['purchase.order']
        created_purchase_orders = self.env['purchase.order']

        for vendor_id, items in grouped_vendors.items():
            po = PurchaseOrder.create({
                'partner_id': vendor_id,
                'origin': self.vraja_common_card_name or 'Inventory AI Agent',
            })
            created_purchase_orders |= po
            for item in items:
                product = item['product']

                self.env['purchase.order.line'].create({
                    'order_id': po.id,
                    'product_id': product.id,
                    'name': product.name,
                    'product_qty': item['qty'],
                    'price_unit': product.standard_price or 0,
                    'uom_id': product.uom_id.id,
                    'date_planned': datetime.now(),
                })
        return created_purchase_orders

    def action_create_rfq(self):
        """
        Button action to create RFQs from AI response.
        """
        self.ensure_one()

        if not self.ai_low_stock_analysis_result:
            raise UserError(_('No AI analysis result found.'))

        ai_records = json.loads(self.ai_low_stock_analysis_result)
        purchase_orders = self._create_rfq_from_ai_records(ai_records, raise_if_empty=True)

        return {
            'name': _('Created RFQs'),
            'type': 'ir.actions.act_window',
            'res_model': 'purchase.order',
            'views': [
                [False, 'list'],
                [False, 'form'],
            ],
            'view_mode': 'list,form',
            'domain': [
                ('id', 'in', purchase_orders.ids)
            ],
            'target': 'current',
        }

    # =================================================================================================================
    #                                             CRON SECTION
    # =================================================================================================================

    @api.model
    def action_cron_low_stock_ai_generate_excel(self):
        """Cron job — Auto regenerates Excel for all stock, sales and purchase products AI cards."""
        card = self.search([
            ('vraja_common_store', '=', 'ai_low_stock'),
            ('vraja_common_card_active', '=', True), ], limit=1)
        if not card:
            card = self.sudo()._create_find_stock_record()

        card.generate_ai_inventory_file()
        _logger.info(f'Auto Excel generated for card: {card.vraja_common_card_name}')

    @api.model
    def action_cron_inventory_ai_analysis(self):
        """Cron job — Auto generates Excel, runs AI analysis and applies results if enabled."""
        card = self.search([
            ('vraja_common_store', '=', 'ai_low_stock'),
            ('vraja_common_card_active', '=', True), ], limit=1)
        if not card:
            return

        if not card._has_generated_inventory_file_for_cron():
            _logger.info('Auto AI analysis skipped because no generated inventory Excel file was found.')
            return

        card.with_context(from_cron=True).action_run_inventory_ai_analysis()
        _logger.info(f'Auto AI analysis completed for card: {card.vraja_common_card_name}')
