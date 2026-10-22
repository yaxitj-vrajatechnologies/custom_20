import io
import base64
import logging
import json
import re
import requests
from datetime import datetime, timedelta
from odoo import models, fields, api
from openpyxl import Workbook
from openpyxl.styles import Font
from collections import defaultdict

_logger = logging.getLogger('------------Vendor AI Agent--------------')

OPENAI_API_BASE_URL = 'https://api.openai.com/v1'


class VrajaAICard(models.Model):
    _inherit = 'vraja.ai.card'

    vraja_common_store = fields.Selection(
        selection_add=[('ai_vendor_intel', 'Vendor Intelligence')],
        ondelete={'ai_vendor_intel': 'cascade'}
    )

    def action_review_dashboard(self):
        """
        Opens the Vendor AI Intelligence Dashboard via an ir.actions.client.
        Overrides the base method to specify the custom Vendor AI OWL tag.
        :return: Dictionary representing the client action.
        """
        action = super().action_review_dashboard()
        if self.vraja_common_store == 'ai_vendor_intel':
            action['tag'] = 'vendor_ai_intelligence_dashboard_template'
        return action

    @api.model
    def action_ai_vendor_get_default_card_id(self):
        """
        Retrieves the default ID for the Vendor AI Intelligence card.
        Used to automatically load the correct context into the JS Dashboard.
        :return: Integer ID of the vraja.ai.card, or False if none exists.
        """
        stock_record = self.search([('vraja_common_store', '=', 'ai_vendor_intel')], order='id', limit=1)
        return stock_record.id if stock_record else False

    ai_vendor_company_information = fields.Text(string="Company Information")
    ai_vendor_procurement_process = fields.Text(string="Procurement Process")
    ai_vendor_forecast_period = fields.Selection([
        ('all_data', 'All Time Data'),
        ('selected_data', 'Preferred Data'),
    ], string='Forecast Period', default='all_data')
    ai_vendor_forecast_days = fields.Integer(string="Forecast Days", default=30)

    ai_vendor_instruction = fields.Text(string="AI Instruction (Vendor)")
    ai_vendor_default_prompt = fields.Text(string="AI Prompt (Vendor)")
    ai_vendor_analysis_result = fields.Text(string="AI Analysis Result (Vendor)")
    ai_vendor_analysis_error = fields.Text(string="AI Error (Vendor)")
    ai_vendor_attachment_id = fields.Many2one('ir.attachment', string="Vendor Data Workbook")
    ai_vendor_analyzed_on = fields.Datetime(string="Last Analyzed On")
    ai_vendor_auto_analyze = fields.Boolean(
        string='Auto Run AI Analysis',
        default=False,
        help='If enabled, the scheduled cron job will automatically call the OpenAI API to run the AI analysis. '
             'If disabled, the cron will be skipped even if it is active.'
    )

    def action_log_view(self):
        """
        Opens a window action displaying the history of Vendor AI executions.
        Forces the context to filter specifically for Vendor Intelligence logs.
        :return: Dictionary representing the window action.
        """
        action = super().action_log_view()
        if self.vraja_common_store == 'ai_vendor_intel':
            action['name'] = 'Vendor AI Logs'
            action['views'] = [
                (False, 'list'),
                (self.env.ref('vendor_ai_intelligence_vts.vendor_ai_log_form_vts').id, 'form'),
            ]
            action['domain'] = [('vraja_common_log_store', '=', 'ai_vendor_intel')]
            action['context'] = {
                **action.get('context', {}),
                'search_default_filter_vendor_ai': 1,
                'create': False,
            }
        return action

    def _get_openai_api_key(self):
        """
        Get OpenAI API key from AI configuration.
        """
        config = self.env['vraja.ai.config'].sudo().search([('openai_api_key', '!=', False)], order='id desc', limit=1)

        if not config or not config.openai_api_key:
            raise ValueError('Missing OpenAI API Key.')

        return config.openai_api_key, config.llm_model

    def _upload_vendor_attachment_to_openai(self):
        """
        Uploads the generated Vendor Intelligence Excel workbook to OpenAI.
        This allows the AI's Code Interpreter to execute Python on the raw data.
        :return: String representing the OpenAI File ID.
        :raises ValueError: If the upload request to OpenAI fails.
        """
        api_key, _ = self._get_openai_api_key()
        filename = self.ai_vendor_attachment_id.name or 'vendor_analysis.xlsx'
        file_data = bytes(self.ai_vendor_attachment_id.raw)
        # We must use OPENAI_API_BASE_URL to match exactly how inventory agent uploads
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
        if response.status_code >= 400:
            error_payload = response.json() if response.text.startswith('{') else {}
            raise ValueError(
                f"OpenAI File Upload Error: {error_payload.get('error', {}).get('message') or response.text}")
        return response.json()['id']

    def _request_vendor_analysis(self):
        """
        Sends the uploaded file ID and instructional prompt to OpenAI for analysis.
        Demands the response in a structured JSON format.
        :param file_id: The OpenAI File ID obtained from _upload_vendor_attachment_to_openai.
        :return: Dictionary containing the raw OpenAI API JSON response.
        :raises ValueError: If the analysis request to OpenAI fails.
        """
        # api_key, api_model = self._get_openai_api_key()

        prompt = f"Company Context: {self.ai_vendor_company_information or 'None'}\n"
        prompt += f"Procurement Process Context: {self.ai_vendor_procurement_process or 'None'}\n\n"
        prompt += """You are a Senior Supply Chain and Procurement Analyst. Your role is to review vendor performance data and produce a precise, data-driven JSON analysis report. Follow every rule strictly. Do not use personal judgment where a rule exists.

=== DATA OVERVIEW ===
You have two Excel sheets:
1. 'Vendor Scores' sheet: Pre-computed vendor performance scores calculated by Odoo. Each vendor has one 'All' row (overall score) plus optional category-specific rows.
2. 'Aggregated SKU Summary' sheet: Summarized purchase history with columns: Vendor, SKU, Product, Category, Avg Unit Price, Total Ordered, Total Received, Late Deliveries. Use the SKU column as the primary product identifier. If SKU is blank, use Product Name.

=== SCORE DEFINITIONS (These are pre-calculated by Odoo — DO NOT re-calculate them) ===
- Delivery Score (0-100): % of PO lines received on or before Expected Date. Formula: (On-Time Lines / Total Lines) x 100. Higher = more punctual.
- Fulfillment Score (0-100): % of ordered quantity received. Formula: (Total Received / Total Ordered) x 100, capped at 100. Higher = fewer shortfalls.
- Price Consistency Score (0-100): Price stability per SKU. Calculated as 100 - (CoV x 100) where CoV = StdDev/AvgPrice computed separately for each SKU, then averaged across all SKUs for that vendor. Score 100 = prices never change per item. Score 0 = extreme price volatility per item. This does NOT indicate how cheap or expensive a vendor is.
- Lead Time Score (0-100): Delivery timing accuracy. On-time line = 100 pts. Each day late deducts 10 pts, minimum 0. Final score = average across all lines.
- Overall Score: Weighted composite = (Delivery x 0.35) + (Fulfillment x 0.25) + (Price Consistency x 0.20) + (Lead Time x 0.20).

=== STRICT ANALYTICAL RULES ===

RULE 1 — top_vendors:
- Source: 'Vendor Scores' sheet, ALL rows (including both 'All' rows and category-specific rows).
- Action: Use the Odoo 'Overall Score' as the base analytical score. For vendors with multiple rows (All + categories), consider their category-level performance to validate or adjust the overall score by a maximum of +/- 5 points ONLY if you find clear, specific evidence of hidden risk or strength (cite this in the reason field).
- Requirement: Include EVERY unique vendor present. Sort from highest to lowest score. Do NOT omit any vendor. Use the vendor's 'All' row score as the primary score, supplemented by category rows.

RULE 2 — worst_delays:
- Source: 'Vendor Scores' sheet, rows where Category = 'All' ONLY.
- Action: Rank vendors by the LOWEST combined sum of (Delivery Score + Lead Time Score). Return exactly the TOP 5 worst-performing vendors overall.
- Requirement: For each entry, copy the delivery_score and lead_time_score values DIRECTLY from the sheet. Do not estimate them.

RULE 3 — fastest_delivery:
- Source: 'Vendor Scores' sheet, rows where Category = 'All' ONLY.
- Action: Rank vendors by the HIGHEST combined sum of (Delivery Score + Lead Time Score). Return exactly the TOP 5 best-performing vendors overall.
- Requirement: For each entry, copy the delivery_score and lead_time_score values DIRECTLY from the sheet. Do not estimate them.

RULE 4 — best_rates:
- Source: 'Aggregated SKU Summary' sheet.
- Action: Find SKUs that appear under multiple vendors. For those shared SKUs, compare average Unit Price per vendor. Rank the top 5 vendors by lowest average price across the most shared SKUs.
- Fallback: If no SKUs are shared between vendors, rank by Price Consistency Score from the 'Vendor Scores' sheet instead, and note this in the reason field.
- Requirement: Do NOT use Price Consistency Score as a measure of cheapness — only as a fallback when no shared SKUs exist.

RULE 5 — category_kings:
- Source: 'Vendor Scores' sheet, rows where Category != 'All' ONLY.
- Action: For each unique category, identify the vendor with the highest Overall Score in that category. Copy the score value directly from the sheet.

RULE 6 — red_flags:
- Source: 'Aggregated SKU Summary' sheet only.
- Action: Scan for patterns of repeated failure. Each red flag MUST cite a specific vendor name AND a specific SKU (or Product Name if SKU is blank). Do NOT write generic warnings.
- Example format: "Vendor A — SKU IPHONE-14-BLK: Short-shipped in 3 of the last 5 orders."

RULE 7 — action_plan:
- Action: Provide 3-5 specific, actionable procurement recommendations referencing specific vendors or SKUs where possible.
- Requirement: Avoid generic advice such as "improve communication" or "monitor vendors more closely".

=== OUTPUT RULES ===
- You MUST respond with ONLY a valid JSON object.
- Do NOT include markdown, backticks, code blocks, or any text outside the JSON.
- CRITICAL: Do NOT just print the JSON in the code interpreter. You MUST return the JSON as your final textual response.
- The JSON must strictly follow this structure:
{
  "executive_summary": "Exactly 2 sentences summarizing the overall health of the supply chain and the most critical finding.",
  "worst_delays": [
    {"rank": 1, "vendor": "Name", "delivery_score": 0, "lead_time_score": 0, "reason": "Specific data-driven reason"},
    {"rank": 2, "vendor": "Name", "delivery_score": 0, "lead_time_score": 0, "reason": "Specific data-driven reason"},
    {"rank": 3, "vendor": "Name", "delivery_score": 0, "lead_time_score": 0, "reason": "Specific data-driven reason"},
    {"rank": 4, "vendor": "Name", "delivery_score": 0, "lead_time_score": 0, "reason": "Specific data-driven reason"},
    {"rank": 5, "vendor": "Name", "delivery_score": 0, "lead_time_score": 0, "reason": "Specific data-driven reason"}
  ],
  "fastest_delivery": [
    {"rank": 1, "vendor": "Name", "delivery_score": 0, "lead_time_score": 0, "speed": "Specific performance description"},
    {"rank": 2, "vendor": "Name", "delivery_score": 0, "lead_time_score": 0, "speed": "Specific performance description"},
    {"rank": 3, "vendor": "Name", "delivery_score": 0, "lead_time_score": 0, "speed": "Specific performance description"},
    {"rank": 4, "vendor": "Name", "delivery_score": 0, "lead_time_score": 0, "speed": "Specific performance description"},
    {"rank": 5, "vendor": "Name", "delivery_score": 0, "lead_time_score": 0, "speed": "Specific performance description"}
  ],
  "best_rates": [
    {"rank": 1, "vendor": "Name", "reason": "Specific SKU comparison or fallback reason"},
    {"rank": 2, "vendor": "Name", "reason": "Specific SKU comparison or fallback reason"},
    {"rank": 3, "vendor": "Name", "reason": "Specific SKU comparison or fallback reason"},
    {"rank": 4, "vendor": "Name", "reason": "Specific SKU comparison or fallback reason"},
    {"rank": 5, "vendor": "Name", "reason": "Specific SKU comparison or fallback reason"}
  ],
  "category_kings": [
    {"category": "Name", "vendor": "Name", "score": 92, "reason": "Specific data-driven reason"}
  ],
  "top_vendors": [
    {"name": "Vendor A", "score": 95, "category": "Category or All", "reason": "Specific data-driven reason"},
    {"name": "Vendor B", "score": 88, "category": "Category or All", "reason": "Specific data-driven reason"}
  ],
  "red_flags": ["Vendor + SKU specific warning 1", "Vendor + SKU specific warning 2"],
  "action_plan": ["Specific actionable recommendation 1", "Specific actionable recommendation 2", "Specific actionable recommendation 3"]
}"""

        return prompt

    def action_run_vendor_ai_analysis(self):
        """
        Main execution flow triggered by the "Run AI Analysis" button in the dashboard.
        Orchestrates file upload, API request, JSON extraction, and log generation.

        :return: True if successful, False otherwise.
        """
        self.ensure_one()
        try:
            if not self.ai_vendor_attachment_id:
                raise ValueError("Vendor Data Workbook is missing. Please generate it first.")

            provider, response = self._call_vendor_ai_provider()
            _logger.info(f"Vendor AI Analysis Response [{provider}]: {response}")

            usages = self._extract_vendor_usage(provider, response)
            _logger.info(f"Vendor AI Request Token Usage: {usages}")

            result_text = self._extract_vendor_output_text(provider, response)
            _logger.info(f"Vendor AI Analysis Text Data: {result_text}")

            if not result_text:
                raise ValueError(f"{provider} did not return analysis text.")

            self.write({
                'ai_vendor_analysis_result': result_text,
                'ai_vendor_analysis_error': False,
                'ai_vendor_analyzed_on': fields.Datetime.now(),
            })

            self._create_vendor_ai_log(result_text, usages=usages, status='success')

        except Exception as e:
            self.write({
                'ai_vendor_analysis_error': str(e),
                'ai_vendor_analyzed_on': fields.Datetime.now(),
            })
            self._create_vendor_ai_log(status='failed', error_message=str(e))
        return True

    @api.model
    def action_cron_vendor_ai_generate_excel(self):
        """
        Scheduled action to automatically generate the Vendor Data Workbook.
        """
        card = self.search([('vraja_common_store', '=', 'ai_vendor_intel'), ('vraja_common_card_active', '=', True)],
                           limit=1)
        if card:
            card.generate_ai_vendor_file()

    @api.model
    def action_cron_vendor_ai_analysis(self):
        """
        Scheduled action to automatically run the AI Analysis.
        Only executes if the 'Auto Run AI Analysis' configuration is enabled on the card.
        """
        card = self.search([('vraja_common_store', '=', 'ai_vendor_intel'), ('vraja_common_card_active', '=', True)],
                           limit=1)
        if not card:
            _logger.info("Vendor AI Cron: No active Vendor Intelligence card found. Skipping.")
            return

        if not card.ai_vendor_auto_analyze:
            _logger.info("Vendor AI Cron: 'Auto Run AI Analysis' is disabled on the card. Skipping API call.")
            return

        if not card.ai_vendor_attachment_id:
            _logger.info("Vendor AI Cron: No data workbook found. Please generate the data file first.")
            return

        _logger.info("Vendor AI Cron: Auto Run AI Analysis is enabled. Starting analysis...")
        card.action_run_vendor_ai_analysis()

    # EXTRACT RESPONSE TEXT
    def _extract_openai_output_text(self, response):
        """
        Extracts the final conversational text from the raw OpenAI response payload.
        Handles nested message structures to locate the actual output string.

        :param response: Dictionary representing the raw OpenAI API JSON response.
        :return: String containing the extracted output text.
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

    def _convert_vendor_excel_to_csv_text(self):
        """Convert vendor Excel attachment to CSV text for Claude and Gemini."""
        self.ensure_one()
        if not self.ai_vendor_attachment_id or not self.ai_vendor_attachment_id.raw:
            raise ValueError('Vendor Data Workbook is missing.')

        from io import BytesIO, StringIO
        import openpyxl as _openpyxl
        import csv as csv_module

        excel_bytes = bytes(self.ai_vendor_attachment_id.raw)
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

    def _extract_vendor_output_text(self, provider, response):
        """Extract plain text from provider response."""
        if provider == 'openai':
            result_text = self._extract_openai_output_text(response)
            if not result_text:
                for item in reversed(response.get('output', [])):
                    if item.get('type') == 'code_interpreter_call' and item.get('code'):
                        match = re.search(r'(\{[\s\S]*\})', item['code'])
                        if match:
                            try:
                                json.loads(match.group(1))
                                result_text = match.group(1)
                                break
                            except Exception:
                                pass
            return result_text

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

    def _extract_vendor_usage(self, provider, response):
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

    def _call_vendor_ai_provider(self):
        """Dispatch vendor AI analysis to configured provider. Returns (provider, response)."""
        config = self.env['vraja.ai.config'].sudo().search([], limit=1)
        if not config:
            raise ValueError('AI configuration not found.')
        provider = config.ai_provider or 'openai'

        prompt = f"Company Context: {self.ai_vendor_company_information or 'None'}\n"
        prompt += f"Procurement Process Context: {self.ai_vendor_procurement_process or 'None'}\n\n"
        prompt += self._request_vendor_analysis()

        if provider == 'openai':
            file_id = self._upload_vendor_attachment_to_openai()
            response = requests.post(
                f'{OPENAI_API_BASE_URL}/responses',
                headers={
                    'Authorization': f'Bearer {config.openai_api_key}',
                    'Content-Type': 'application/json',
                },
                json={
                    'model': config.llm_model,
                    'tools': [{
                        'type': 'code_interpreter',
                        'container': {
                            'type': 'auto',
                            'memory_limit': '4g',
                            'file_ids': [file_id],
                        },
                    }],
                    'tool_choice': 'required',
                    'instructions': "You are an expert procurement and supply chain analyst.",
                    'input': prompt,
                },
                timeout=300,
            )
            if response.status_code >= 400:
                error_payload = response.json() if response.text.startswith('{') else {}
                raise ValueError(f"OpenAI API Error: {error_payload.get('error', {}).get('message') or response.text}")
            return provider, response.json()

        elif provider == 'claude':
            csv_text = self._convert_vendor_excel_to_csv_text()
            combined_prompt = f"{prompt}\n\nVENDOR DATA (from Excel, converted to CSV):\n{csv_text}"
            response = requests.post(
                'https://api.anthropic.com/v1/messages',
                headers={
                    'x-api-key': (config.claude_api_key or '').strip(),
                    'anthropic-version': '2023-06-01',
                    'content-type': 'application/json',
                },
                json={
                    'model': config.claude_llm_model,
                    'max_tokens': config.claude_max_tokens or 8192,
                    'system': "You are an expert procurement and supply chain analyst.",
                    'messages': [{'role': 'user', 'content': combined_prompt}],
                },
                timeout=300,
            )
            if response.status_code >= 400:
                raise ValueError(f'Claude API Error {response.status_code}: {response.text}')
            return provider, response.json()

        elif provider == 'gemini':
            csv_text = self._convert_vendor_excel_to_csv_text()
            combined_prompt = f"{prompt}\n\nVENDOR DATA (from Excel, converted to CSV):\n{csv_text}"
            response = requests.post(
                f'https://generativelanguage.googleapis.com/v1beta/models/{config.gemini_llm_model}:generateContent?key={(config.gemini_api_key or "").strip()}',
                headers={'Content-Type': 'application/json'},
                json={
                    'system_instruction': {
                        'parts': [{'text': "You are an expert procurement and supply chain analyst."}]
                    },
                    'contents': [{'parts': [{'text': combined_prompt}]}],
                    'generationConfig': {'responseMimeType': 'application/json'},
                },
                timeout=300,
            )
            if response.status_code >= 400:
                data = json.loads(response.text)
                message = data.get("error", {}).get("message", "")

                raise ValueError(f'Gemini API Error {response.status_code}: {message}')
            return provider, response.json()

    def _create_vendor_ai_log(self, parsed_json=None, usages=None, status='success', error_message=False):
        """
        Creates a tracking log record (vraja.ai.log) for the AI execution.
        Safely parses the JSON string to extract token usage and top vendor stats.

        :param parsed_json: Dictionary or String containing the AI's JSON output.
        :param usages: Dictionary containing OpenAI token usage statistics.
        :param status: String representing the success state ('success', 'failed').
        :param error_message: String containing the error message if status is 'failed'.
        """
        if isinstance(parsed_json, str):
            try:
                match = re.search(r'(\{[\s\S]*\})', parsed_json)
                if match:
                    parsed_json = json.loads(match.group(1))
                else:
                    parsed_json = {}
            except Exception:
                parsed_json = {}

        if parsed_json is None:
            parsed_json = {}
        if not usages:
            usages = {}

        line_vals = []
        if parsed_json and parsed_json.get('top_vendors'):
            for idx, vendor in enumerate(parsed_json.get('top_vendors', [])):
                line_vals.append({
                    'vendor_ai_rank': idx + 1,
                    'vendor_ai_partner_name': vendor.get('name') or '',
                    'vendor_ai_score': vendor.get('score') or 0.0,
                    'vendor_ai_category': vendor.get('category') or '',
                    'vendor_ai_reason': vendor.get('reason') or '',
                })

        config = self.env['vraja.ai.config'].sudo().search([], limit=1)

        # Format additional analysis details — now ranked arrays
        worst_delays = parsed_json.get('worst_delays', [])
        fastest_delivery = parsed_json.get('fastest_delivery', [])
        best_rates = parsed_json.get('best_rates', [])

        # Backward compatibility: if still a dict (old result), wrap in list
        if isinstance(worst_delays, dict):
            worst_delays = [worst_delays]
        if isinstance(fastest_delivery, dict):
            fastest_delivery = [fastest_delivery]
        if isinstance(best_rates, dict):
            best_rates = [best_rates]

        def _render_ranked_rows(items, value_key='reason', color='#6c757d'):
            rows_html = ''
            for item in items:
                rank = item.get('rank') or ''
                vendor = item.get('vendor') or item.get('name') or 'N/A'
                category = item.get('category') or ''
                value = item.get(value_key) or item.get('reason') or ''
                del_score = item.get('delivery_score')
                lt_score = item.get('lead_time_score')
                score_txt = f'Del: {del_score} | LT: {lt_score} — ' if del_score is not None else ''
                cat_badge = f'<span class="badge badge-light border mr-1" style="font-size:10px;">{category}</span>' if category and category.lower() != 'all' else ''
                rows_html += f"""
                <div class="d-flex align-items-start mb-2 pb-2 border-bottom">
                    <span class="badge badge-secondary mr-2 mt-1" style="min-width:22px;">{rank}</span>
                    <div>
                        <div class="font-weight-bold text-dark" style="font-size:13px;">{vendor} - {value}</div>
                    </div>
                </div>"""
            return rows_html or '<p class="text-muted small mb-0">No data</p>'

        worst_delays_html = _render_ranked_rows(worst_delays, value_key='reason')
        fastest_delivery_html = _render_ranked_rows(fastest_delivery, value_key='speed')
        best_rates_html = _render_ranked_rows(best_rates, value_key='reason')

        # Build HTML Report
        html_report = f"""
        <div class="container-fluid py-3">
            <div class="alert alert-info border-0 shadow-sm mb-4" style="background-color: #e8f4f8; border-left: 5px solid #17a2b8 !important;">
                <h4 class="alert-heading text-info mb-2" style="font-weight: bold;"><i class="fa fa-lightbulb-o mr-2"></i>Executive Summary</h4>
                <p class="mb-0 text-dark" style="font-size: 15px;">{parsed_json.get('executive_summary', 'No summary provided.')}</p>
            </div>

            <div class="row mb-4">
                <div class="col-md-4">
                    <div class="card shadow-sm border-0 h-100" style="background-color: #fff5f5; border-left: 4px solid #dc3545 !important;">
                        <div class="card-body p-3">
                            <h5 class="text-danger mb-3" style="font-weight: 600;"><i class="fa fa-clock-o mr-2"></i>Usually Delays (Top {len(worst_delays)})</h5>
                            {worst_delays_html}
                        </div>
                    </div>
                </div>
                <div class="col-md-4">
                    <div class="card shadow-sm border-0 h-100" style="background-color: #f4fbf5; border-left: 4px solid #28a745 !important;">
                        <div class="card-body p-3">
                            <h5 class="text-success mb-3" style="font-weight: 600;"><i class="fa fa-rocket mr-2"></i>Fastest Delivery (Top {len(fastest_delivery)})</h5>
                            {fastest_delivery_html}
                        </div>
                    </div>
                </div>
                <div class="col-md-4">
                    <div class="card shadow-sm border-0 h-100" style="background-color: #f4f8fc; border-left: 4px solid #007bff !important;">
                        <div class="card-body p-3">
                            <h5 class="text-primary mb-3" style="font-weight: 600;"><i class="fa fa-tags mr-2"></i>Best Rates (Top {len(best_rates)})</h5>
                            {best_rates_html}
                        </div>
                    </div>
                </div>
            </div>

            <h4 class="mb-3 text-warning border-bottom pb-2" style="font-weight: bold;"><i class="fa fa-crown mr-2"></i>Category Kings</h4>
            <div class="row mb-4">
        """
        for king in parsed_json.get('category_kings', []):
            html_report += f"""
                <div class="col-md-6 mb-3">
                    <div class="card border-0 shadow-sm" style="background-color: #fffbf2; border-left: 4px solid #ffc107 !important;">
                        <div class="card-body p-3">
                            <div class="d-flex justify-content-between align-items-center mb-2">
                                <div>
                                    <span class="badge badge-warning text-dark mb-1">{king.get('category', 'Category')}</span>
                                    <h6 class="font-weight-bold text-dark mb-0">{king.get('vendor', 'N/A')}</h6>
                                </div>
                                <div class="text-center">
                                    <div class="badge badge-success p-2" style="font-size:14px;">{king.get('score', '0')} / 100</div>
                                </div>
                            </div>
                            <p class="text-muted small mb-0 border-top pt-2 mt-2">{king.get('reason', '')}</p>
                        </div>
                    </div>
                </div>
            """
        html_report += "</div>"

        # Red Flags and Action Plan
        # html_report += """
        #     <div class="row">
        #         <div class="col-md-6">
        #             <div class="card border-0 shadow-sm h-100">
        #                 <div class="card-header bg-white border-bottom-0 pb-0">
        #                     <h5 class="text-danger mb-0" style="font-weight: 600;"><i class="fa fa-exclamation-triangle mr-2"></i>Red Flags</h5>
        #                 </div>
        #                 <div class="card-body pt-2">
        #                     <ul class="list-unstyled mb-0">
        # """
        # for flag in parsed_json.get('red_flags', []):
        #     html_report += f'<li class="mb-2 text-danger"><i class="fa fa-circle mr-2" style="font-size: 8px; position: relative; top: -2px;"></i>{flag}</li>'
        html_report += """
                            </ul>
                        </div>
                    </div>
                </div>
                <div class="col-md-6">
                    <div class="card border-0 shadow-sm h-100">
                        <div class="card-header bg-white border-bottom-0 pb-0">
                            <h5 class="text-success mb-0" style="font-weight: 600;"><i class="fa fa-check-square-o mr-2"></i>Action Plan</h5>
                        </div>
                        <div class="card-body pt-2">
                            <ul class="list-unstyled mb-0">
        """
        for action in parsed_json.get('action_plan', []):
            html_report += f'<li class="mb-2 text-dark"><i class="fa fa-arrow-right mr-2 text-success"></i>{action}</li>'
        html_report += """
                            </ul>
                        </div>
                    </div>
                </div>
            </div>
        </div>
        """

        self.env['vraja.ai.log'].sudo().create({
            'vraja_common_log_store': 'ai_vendor_intel',
            'status': status,
            'vendor_ai_token_usage': str(usages.get('total_tokens') or '0'),
            'vendor_ai_forecast_period': self.ai_vendor_forecast_period,
            'vendor_ai_forecast_days': self.ai_vendor_forecast_days,
            'vendor_ai_total_vendors': len(line_vals),
            'vendor_ai_report_html': html_report,
            'vendor_ai_error': error_message or False,
            'line_ids': [(0, 0, line) for line in line_vals],
        })

    def generate_ai_vendor_file(self):
        """
        Generates the Vendor Intelligence Excel workbook containing pre-calculated
        vendor metrics and raw purchase order history. Attaches it to the card.

        :return: Self
        """
        self.ensure_one()

        self.env['vendor.intelligence.score'].compute_all_scores(
            self.ai_vendor_forecast_period,
            self.ai_vendor_forecast_days,
        )

        if self.ai_vendor_attachment_id:
            self.ai_vendor_attachment_id.unlink()

        workbook = Workbook()
        if workbook.active:
            workbook.remove(workbook.active)

        _logger.info("Prepare Vendor Score File")
        self._prepare_vendor_score_sheet(workbook)

        _logger.info("Prepare Purchase Data File")
        self._prepare_vendor_purchase_sheet(workbook)

        self._apply_auto_width(workbook)
        output = io.BytesIO()
        workbook.save(output)
        output.seek(0)

        attachment = self.env['ir.attachment'].create({
            'name': f"Vendor_Intelligence_Data_{datetime.now().strftime('%Y%m%d')}.xlsx",
            'type': 'binary',
            'raw': output.read(),
            'mimetype': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            'res_model': self._name,
            'res_id': self.id,
        })

        self.write({'ai_vendor_attachment_id': attachment.id})
        return self

    def _prepare_vendor_score_sheet(self, workbook):
        """
        Populates the 'Vendor Scores' sheet within the workbook using data
        from the vendor.intelligence.score model.

        :param workbook: openpyxl.Workbook instance to be modified.
        """
        sheet = workbook.create_sheet('Vendor Scores')
        headers = [
            'Vendor',
            'Category',
            'Delivery Score',
            'Fulfillment Score',
            'Price Consistency Score',
            'Lead Time Score',
            'Overall Score',
        ]
        sheet.append(headers)
        for cell in sheet[1]:
            cell.font = Font(bold=True)

        scores = self.env['vendor.intelligence.score'].search([])
        for s in scores:
            sheet.append([
                s.partner_id.name or '',
                s.category_id.name or 'All',
                s.delivery_score,
                s.fulfillment_score,
                s.price_score,
                s.lead_time_score,
                s.composite_score,
            ])

    def _prepare_vendor_purchase_sheet(self, workbook):
        """
        Populates the 'Aggregated SKU Summary' sheet within the workbook by aggregating
        purchase lines matching the specified forecast period to drastically save AI tokens.

        :param workbook: openpyxl.Workbook instance to be modified.
        """
        sheet = workbook.create_sheet('Aggregated SKU Summary')
        headers = ['Vendor', 'SKU', 'Product', 'Category', 'Avg Unit Price', 'Total Ordered', 'Total Received',
                   'Late Deliveries']
        sheet.append(headers)
        for cell in sheet[1]:
            cell.font = Font(bold=True)

        domain = [('state', 'in', ['purchase', 'done'])]
        if self.ai_vendor_forecast_period == 'selected_data' and self.ai_vendor_forecast_days:
            from_date = fields.Datetime.now() - timedelta(days=max(int(self.ai_vendor_forecast_days), 0))
            domain.append(('date_approve', '>=', fields.Datetime.to_string(from_date)))

        orders = self.env['purchase.order'].search(domain)

        # Aggregation Dictionary
        agg_data = defaultdict(lambda: {'prices': [], 'ordered': 0, 'received': 0, 'late': 0})

        for order in orders:
            vendor_name = order.partner_id.name or ''
            for line in order.order_line:
                if line.product_id.type != 'service':
                    sku = line.product_id.default_code or ''
                    product_name = line.product_id.name or ''
                    category = line.product_id.categ_id.name or ''

                    key = (vendor_name, sku, product_name, category)

                    agg_data[key]['prices'].append(line.price_unit)
                    agg_data[key]['ordered'] += line.product_qty
                    agg_data[key]['received'] += line.qty_received

                    # Check if late
                    actual_date = False
                    if line.move_ids:
                        done_moves = line.move_ids.filtered(lambda m: m.state == 'done')
                        if done_moves:
                            actual_date = max(done_moves.mapped('date'))

                    if line.date_planned and actual_date:
                        if actual_date.date() > line.date_planned.date():
                            agg_data[key]['late'] += 1

        for key, metrics in agg_data.items():
            avg_price = sum(metrics['prices']) / len(metrics['prices']) if metrics['prices'] else 0.0
            sheet.append([
                key[0],  # Vendor
                key[1],  # SKU
                key[2],  # Product
                key[3],  # Category
                round(avg_price, 2),
                metrics['ordered'],
                metrics['received'],
                metrics['late'],
            ])

    def _apply_auto_width(self, workbook):
        """
        Auto apply width on all workbook sheets.
        """
        for sheet in workbook.worksheets:
            for column_cells in sheet.columns:
                length = max(len(str(cell.value or '')) for cell in column_cells)
                sheet.column_dimensions[column_cells[0].column_letter].width = length + 5
