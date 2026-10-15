import logging
import requests
import re
import html
from odoo import api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class AiEmailGenerateWizard(models.TransientModel):
    _name = 'ai.email.generate.wizard'
    _description = 'AI Email Template Generate Wizard'

    mailing_id = fields.Many2one(
        comodel_name='mailing.mailing',
        string="Mailing",
        required=True,
        ondelete='cascade',
    )

    prompt = fields.Text(
        string="Describe the email you want",
        placeholder="e.g. 30% off VIP exclusive sale for loyal customers, "
                    "festive tone, include a coupon code",
        required=True,
    )

    output_type = fields.Selection(
        selection=[
            ('text_only', 'Text Only'),
            ('full_design', 'Full Design'),
        ],
        string="Generation Type",
        default='text_only',
        required=True,
    )

    state = fields.Selection(
        selection=[
            ('draft', 'Idle'),
            ('running', 'Running'),
            ('done', 'Done'),
            ('failed', 'Error'),
        ],
        default='draft',
        string="Status",
    )

    active_provider_display = fields.Char(
        string="Active Provider",
        compute='_compute_active_provider_display',
    )
    preview_html = fields.Html(
        string="Generated Preview",
        sanitize=False,
    )

    @api.depends('mailing_id')
    def _compute_active_provider_display(self):
        """Read the active ai.provider.config and return a human-readable
        label for the currently selected provider. Falls back to a helpful
        message if no config is found yet.
        """
        provider_labels = {
            'openai': 'OpenAI (ChatGPT)',
            'anthropic': 'Anthropic (Claude)',
            'gemini': 'Google Gemini',
        }
        config = self.env['ai.provider.config'].sudo().search([], limit=1)
        label = provider_labels.get(config.ai_provider, 'Not configured') if config else 'Not configured'
        for rec in self:
            rec.active_provider_display = label

    # ------------------------------------------------------------
    # Public actions
    # ------------------------------------------------------------
    def action_generate_template(self):
        """Main button action.
        1. Read active configuration and validate API key.
        2. Call the right provider helper.
        3. Write result on mailing.
        4. Reopen the mailing form so the user sees the result.
        """
        self.ensure_one()
        self.state = 'running'
        self.env.cr.commit()

        config = self.env['ai.provider.config'].sudo().search([], limit=1)
        api_key, llm_model = config.get_provider_credential()
        if not api_key:
            self.state = 'draft'
            raise UserError(
                f"No API key configured for provider '{config.ai_provider}'. "
                "Please set it in AI Configuration > AI Provider."
            )
        generated_html = self._call_ai_provider(config, api_key, llm_model)

        self.env.cr.commit()

        self.preview_html = generated_html
        self.env.cr.commit()
        self.state = 'done'
        return {
            'type': 'ir.actions.act_window',
            'name': 'Generate Email Template with AI',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
            'context': self.env.context,
        }

    def action_confirm_template(self):
        self.ensure_one()
        if not self.preview_html:
            raise UserError("No preview to apply. Please generate first.")
        self._apply_result_to_mailing(self.preview_html)
        self.env.cr.commit()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'mailing.mailing',
            'res_id': self.mailing_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_regenerate(self):
        self.ensure_one()
        self.preview_html = False
        self.state = 'draft'
        self.env.cr.commit()
        return self.action_generate_template()

    def _build_full_prompt(self):
        company = self.env.company
        base_url = self.env['ir.config_parameter'].sudo().get_str('web.base.url')
        company_info = (
            f"COMPANY DETAILS (use these in the template where appropriate):\n"
            f"- Company Name: {company.name or ''}\n"
            f"- Email: {company.email or ''}\n"
            f"- Website: {company.website or ''}\n"
            f"- Logo URL: {base_url}/web/image/res.company/{company.id}/logo\n\n"
            "RULES FOR USING COMPANY DETAILS:\n"
            "- Use Company Name where a brand/company name appears.\n"
            "- Use Logo URL only in <img> tags where a logo is shown.\n"
            "- Use Website URL for CTA buttons or 'visit us' links.\n"
            "- Use Email only in footer/contact sections.\n"
            "- Do NOT repeat the same detail in multiple places.\n"
            "- If a section does not need company info, do NOT add it.\n\n"
        )

        ODOO_CSS_RULES = (
            "CRITICAL CSS RULES (must follow):\n"
            "- box-shadow and text-shadow: ALWAYS use format 'Xpx Ypx Zpx color/rgba(...)' — NEVER put color/rgba() first.\n"
            "- Do NOT use 'display: flex', 'display: grid', 'position: absolute/relative/fixed' in inline styles.\n"
            "- Do NOT use CSS variables (--variable-name) inside inline style attributes — only inside the <style> block.\n"
            "- Do NOT use 'vw', 'vh', 'em', 'rem' units in inline styles — use only 'px' or '%'.\n\n"
        )

        ODOO_STRUCTURE_RULES = (
            "CRITICAL STRUCTURE RULES (must follow):\n"
            "- ALWAYS use <section>...</section> tags for every block — NEVER use <div> as a block container.\n"
            "- Every <section> MUST have: data-snippet='s_*', data-name='...', data-vxml='001', "
            "classes 'o_mail_snippet_general o_colored_level'.\n"
            "- Use Bootstrap grid inside sections: "
            "<div class='container'> > <div class='row'> > <div class='col-md-*'>.\n"
            "- NEVER use <tr>, <td>, <table> as block containers — only use them for email-safe layouts inside sections.\n\n"
        )

        if self.output_type == 'full_design':
            return (
                    "You are creating a FULL REDESIGN of an existing Odoo "
                    "mass-mailing HTML template, based on the campaign "
                    "described in the USER REQUEST below. Selecting Full "
                    "Design mode IS the redesign instruction - always "
                    "meaningfully rework the layout, section structure, and "
                    "colors to fit the campaign, even if the USER REQUEST "
                    "only describes the offer/content and never uses the "
                    "word 'redesign'.\n\n"
                    "This template uses Odoo's snippet system - every section "
                    "has data-snippet, data-name, and data-vxml attributes, plus "
                    "classes like o_mail_snippet_general and o_colored_level, and "
                    "is wrapped in o_layout/o_mail_wrapper containers with CSS "
                    "custom properties for theming.\n\n"
                    "CRITICAL RULES (technical - must follow regardless of the "
                    "request):\n"
                    "- Do NOT remove, rename, or alter any data-snippet, data-name, "
                    "or data-vxml attribute.\n"
                    "- Do NOT remove or rename o_mail_snippet_general, "
                    "o_colored_level, o_layout, o_mail_wrapper, or o_mail_wrapper_td "
                    "classes.\n"
                    "- Do NOT remove the <style id=\"design-element\"> block.\n"
                    "- You may freely add, remove, or reorder sections to fit "
                    "the campaign - every section (new or existing) must "
                    "still follow the Odoo snippet structure rules below "
                    "(data-snippet, data-name, data-vxml attributes and the "
                    "required classes).\n\n"
                    + ODOO_STRUCTURE_RULES
                    + ODOO_CSS_RULES
                    + "WHAT TO CHANGE (this is a redesign - change freely, "
                      "don't just tweak):\n"
                      "- CSS variable VALUES inside the <style id=\"design-element\"> "
                      "block (colors, font sizes, font families, spacing, border "
                      "styles) - change the values, but keep the variable names.\n"
                      "- Inline style=\"...\" attribute values already present on "
                      "sections (e.g. background-color, padding).\n"
                      "- Bootstrap spacing/utility classes already used in the "
                      "template (e.g. pt16, pb24, mb0) - you may adjust these "
                      "values for better visual balance.\n"
                      "- Text content, image src/alt, link hrefs.\n"
                      "- The sections themselves: add, remove, reorder, or "
                      "rewrite them to best present the campaign.\n\n"
                      "EXISTING TEMPLATE:\n"
                      f"{self.mailing_id.body_arch}\n\n"
                    + company_info
                    + "USER REQUEST (the campaign content to redesign for):\n"
                      f"{self.prompt}\n\n"
                      "Return ONLY the complete updated HTML fragment - do NOT "
                      "include <!DOCTYPE>, <html>, <head>, or <body> tags. Do NOT "
                      "include an XML declaration such as <?xml version=\"1.0\"?> "
                      "at the top of the response.\n"
                      "No explanation, no commentary, no markdown code fences."
            )
        else:
            return (
                    "You are adding a new text section to an existing Odoo "
                    "mass-mailing HTML template. The template uses Odoo's snippet "
                    "system - sections have data-snippet, data-name, and data-vxml "
                    "attributes, plus classes like o_mail_snippet_general and "
                    "o_colored_level.\n\n"
                    "Generate ONE new <section> for the requested content (a short "
                    "headline, one short paragraph, and a call to action button), "
                    "following the SAME conventions as the sections already present "
                    "in the template below - reuse a similar data-snippet value "
                    "style (e.g. s_title or s_text), include o_mail_snippet_general "
                    "and o_colored_level classes, and rely on the template's "
                    "existing CSS variables for fonts/colors instead of introducing "
                    "new ones.\n\n"
                    "IMPORTANT: Do NOT include a new <style> tag - the parent "
                    "template already has one. Do NOT modify or repeat any existing "
                    "section from the template below; only output the new section "
                    "you are adding.\n\n"
                    + ODOO_STRUCTURE_RULES
                    + ODOO_CSS_RULES
                    + "REFERENCE TEMPLATE (for snippet conventions only - do not "
                      "repeat this back):\n"
                      f"{self.mailing_id.body_arch}\n\n"
                    + company_info
                    + "USER REQUEST:\n"
                      f"{self.prompt}\n\n"
                      "Return ONLY the new <section>...</section> HTML - output literal "
                      "'<' and '>' characters for tags, NOT escaped entities like "
                      "'&lt;' or '&gt;'. Do NOT include an XML declaration such as "
                      "<?xml version=\"1.0\"?> at the top of the response.\n"
                      "No explanation, no commentary, no markdown code fences."
            )

    # ------------------------------------------------------------
    # Internal helpers (one small method per concern)
    # ------------------------------------------------------------
    def _call_ai_provider(self, config, api_key, llm_model):
        """Route the call to the right provider-specific method, then
        clean the raw text response so only the actual HTML fragment
        remains. Captures token usage and writes a log record via the
        shared _create_log helper, regardless of success or failure.
        """
        self.env.cr.commit()
        full_prompt = self._build_full_prompt()

        try:
            if config.ai_provider == 'openai':
                raw_result, total_tokens = self._generate_with_openai(full_prompt, api_key, llm_model)
            elif config.ai_provider == 'anthropic':
                raw_result, total_tokens = self._generate_with_anthropic(full_prompt, api_key, llm_model,
                                                                         config.claude_max_tokens)
            else:
                raw_result, total_tokens = self._generate_with_gemini(full_prompt, api_key, llm_model)

            self.env.cr.commit()

            cleaned_html = self._extract_html(raw_result)
            self._create_log(
                config=config, llm_model=llm_model, state='success',
                generated_html=cleaned_html, total_tokens=total_tokens,
                log_message="Email Template Generated Successfully",
            )
            return cleaned_html

        except UserError as error:
            self.state = 'draft'
            self.env.cr.commit()
            raise UserError(error)

    def _create_log(self, config, llm_model, state, generated_html=None,
                    total_tokens=0, log_message=None):
        self.env['ai.email.tmpl.log'].sudo().create({
            'mailing_id': self.mailing_id.id,
            'provider': config.ai_provider,
            'llm_model': llm_model,
            'output_type': self.output_type,
            'generated_html': generated_html,
            'total_tokens': total_tokens,
            'state': state,
            'log_message': log_message,
        })

    def _extract_html(self, text):
        """Cleans the raw AI response so only the inner HTML fragment
        remains - strips markdown code fences and any full-document
        wrapper tags (<!DOCTYPE>, <html>, <head>, <body>) that the
        model may have added, since the mailing editor expects only
        the fragment that goes inside the body.
        """
        if not text:
            return text

        text = text.strip()
        text = html.unescape(
            text)  # Converts HTML entities like &lt; and &gt; back into real < > tags, in case the AI escaped its HTML output
        text = re.sub(r'<\?xml.*?\?>', '', text, flags=re.IGNORECASE | re.DOTALL).strip()

        # ADDED: strip ```html ... ``` markdown fences if the model wrapped the output
        fence_match = re.search(r'```(?:html)?\s*(.*?)```', text, re.DOTALL | re.IGNORECASE)
        if fence_match:
            text = fence_match.group(1).strip()

        # ADDED: if a full HTML document was returned, pull out just the <body> contents
        body_match = re.search(r'<body[^>]*>(.*?)</body>', text, re.DOTALL | re.IGNORECASE)
        if body_match:
            return body_match.group(1).strip()

        # ADDED: fallback - strip stray <!DOCTYPE>, <html>, <head>...</head> tags if present
        # (covers cases where the model used these tags without a matching <body>)
        text = re.sub(r'<!DOCTYPE[^>]*>', '', text, flags=re.IGNORECASE)  # Remove the syntax from the response
        text = re.sub(r'</?html[^>]*>', '', text, flags=re.IGNORECASE)
        text = re.sub(r'<head[^>]*>.*?</head>', '', text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'</?body[^>]*>', '', text, flags=re.IGNORECASE)
        text = re.sub(r'<\?xml.*?\?>', '', text, flags=re.IGNORECASE | re.DOTALL).strip()

        # Existing-style fallback: slice from first '<' to last '>'
        start_idx = text.find('<')
        end_idx = text.rfind('>')
        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
            return text[start_idx:end_idx + 1].strip()

        return text.strip()

    def _apply_result_to_mailing(self, generated_html):
        """Writes the AI result into the mailing body field.
        Text Only mode nests the generated <section> inside the existing
        wrapper structure so it stays a child of the mailing's o_layout
        container; Full Design mode replaces the whole body directly.
        """
        if not generated_html:
            raise UserError("The AI provider did not return any content.")

        if self.output_type == 'full_design':
            self.mailing_id.body_arch = generated_html
        else:
            self.mailing_id.body_arch = (
                '<div data-name="Mailing" class="o_layout oe_unremovable oe_unmovable o_basic_theme">'
                '<div class="oe_structure">'
                f'{generated_html}'
                '<p><br/><a href="/unsubscribe_from_list">Unsubscribe</a></p>'
                '</div></div>'
            )

    # ------------------------------------------------------------
    # Provider specific calls
    # Each one is intentionally short: build payload, call API,
    # extract text, return it. No retries or advanced error
    # handling, as requested - just enough to work reliably.
    # ------------------------------------------------------------
    def _generate_with_openai(self, prompt, api_key, model):
        url = "https://api.openai.com/v1/chat/completions"
        payload = {
            "model": model or "gpt-4.1-mini",
            "messages": [{"role": "user", "content": prompt}],
        }
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }
        data = self._post_json(url, payload, headers, provider='OpenAI')
        tokens = data.get('usage', {}).get('total_tokens', 0)
        return data["choices"][0]["message"]["content"], tokens

    def _generate_with_anthropic(self, prompt, api_key, model, max_tokens):
        req_url = 'https://api.anthropic.com/v1/messages'
        payload = {
            "model": model or "claude-sonnet-4-6",
            "max_tokens": max_tokens or 8001,
            "messages": [{"role": "user", "content": prompt}],
        }

        headers = {
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        }
        data = self._post_json(req_url, payload, headers, provider='Claude')
        usage = data.get('usage', {})
        tokens = usage.get('input_tokens', 0) + usage.get('output_tokens', 0)
        return data["content"][0]["text"], tokens

    def _generate_with_gemini(self, prompt, api_key, model):
        model_name = model or "gemini-2.5-flash"
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model_name}:generateContent?key={api_key}"
        )
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
        }
        headers = {"Content-Type": "application/json"}
        data = self._post_json(url, payload, headers, provider='Gemini')
        tokens = data.get('usageMetadata', {}).get('totalTokenCount', 0)
        return data["candidates"][0]["content"]["parts"][0]["text"], tokens

    def _post_json(self, url, payload, headers, provider):
        """Single shared helper to perform a POST request and return
        the parsed JSON response. Centralising this avoids repeating
        the same request/response code in every provider method.
        """
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=300)
            if response.status_code != 200:
                self.state = 'failed'
                response.raise_for_status()

            return response.json()
        except requests.exceptions.HTTPError as error:
            _logger.error("AI provider call failed: %s", error.response.text if error.response is not None else error)
            self.state = 'failed'
            raise UserError(
                "The AI provider returned an error. Please check the "
                f"{error}"
            )
        except requests.exceptions.Timeout:
            raise UserError(f'{provider} API timed out. Please try again.')
        except requests.exceptions.ConnectionError:
            raise UserError(f'Cannot connect to {provider} API. Check your internet connection.')
        except requests.exceptions.RequestException as error:
            raise UserError(f'{provider} API request failed: {error}')
