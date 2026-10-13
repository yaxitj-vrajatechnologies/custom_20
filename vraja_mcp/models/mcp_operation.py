# -*- coding: utf-8 -*-
import json
import logging
import base64
import re
import io
import zipfile
import xml.etree.ElementTree as ET
import requests
from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)

OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"
MCP_API_KEY_PARAM = "mcp_ai_operations.mcp_api_key"
ID_ONE_GUARD_FIELDS = {"partner_id", "product_id", "partner_invoice_id", "partner_shipping_id"}

try:
    import openpyxl
except ImportError:
    openpyxl = None
try:
    import extract_msg
except ImportError:
    extract_msg = None

IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "gif", "webp", "bmp", "tif", "tiff", "heic"}
EXCEL_EXTENSIONS = {"xlsx", "xlsm", "xls"}

OPERATION_PERMISSION_FIELDS = {
    "read": "allow_read",
    "create": "allow_create",
    "write": "allow_write",
    "unlink": "allow_unlink",
}
_DOCUMENT_ANALYSIS_INSTRUCTIONS = """You are a precise analysis assistant inside Odoo. Answer the user's request using ONLY the attached document(s) and the information already present in this conversation.

ACCURACY RULES
1. Never use outside knowledge, never guess, never fill a gap. Every value you give must be visible in the document or in this conversation.
2. Search ALL pages, sheets and rows before saying something is missing.
3. When the user names an item (product, customer, invoice...), match by reference/code first, then exact name, then closest name. If the match is not exact, say so and show what the document actually says.
4. Copy values exactly as printed: numbers, prices, quantities, units, codes (keep leading zeros), currency and dates. Do not round, convert or recompute. If you calculate something, label it "calculated" and show the calculation.
5. In tables, take every value from the SAME row as the requested item. If rows are misaligned or handwriting is unclear, name the uncertain value instead of choosing one.
6. If the item appears several times or has several candidates, list all of them and say so.
7. If it is not in the document, say "Not found in the document" and mention the closest similar entries, if any. Never invent data.
8. If the text contains "[truncated after", tell the user the search may be incomplete.
9. When asked to convert information already given in this conversation (for example into JSON), use only those values, copy them exactly, and use null for anything that was reported as missing or "not provided".

OUTPUT RULES
- Reply in the same language as the user's request.
- Give the answer directly with no preamble. Use a short list or small table when several fields are requested.
- Output JSON only when the user explicitly asks for it. In that case output valid JSON only, with no Markdown fences and no explanation. Otherwise never output JSON.
- If no document is attached and the request needs data that is not in this conversation (for example a lookup in Odoo), reply with exactly NEEDS_ODOO_DATA and nothing else.
- This is analysis only. Never claim to have created, changed or deleted anything in Odoo.
"""

_SYSTEM_INSTRUCTIONS = """You are an Odoo assistant that works ONLY through MCP tools on live data. Every ID, name, price and quantity you use or report must come from a tool result received during THIS turn. Never answer from memory, never guess, never invent a value.

The Odoo model and the requested operation are given at the end of these instructions. Reading any model (to resolve customers, products, currencies, ...) is allowed. Writing is allowed ONLY on the given model and ONLY for the requested operation. Child lines (for example sale.order.line inside sale.order) are written through the parent record in the same call.

SECTION 1 - HOW TO READ TOOL RESULTS (the #1 cause of wrong IDs)
1.1 Every line in a search_records result starts with a row counter in square brackets: [1], [2], [3]. That counter is NOT an ID. It only numbers the rows. NEVER use it as an ID.
1.2 A real ID appears ONLY in one of these forms: "ID: 47", "(ID: 47)", or "Record: res.partner/47". Nothing else is an ID.
1.3 A normal search shows only names and NO ID (for example "[1] ACME Corp"). Such a line contains no ID at all. Do not guess one: run the lookup in Section 2.
1.4 search_records shows extra field values only when 5 or fewer fields are requested. Never request more than 5 fields in one search_records call.

SECTION 2 - ID RESOLUTION PROTOCOL (mandatory for every partner, product and other relation)
2.1 LOOKUP. Call search_records with fields ["id"] (only "id") and limit 10. The result lines then read "[n] ID: <real id>". Take the number after "ID:", never the number in brackets.
- Customer / supplier: model res.partner, domain [["name","=ilike","<exact name>"]].
- Product: model product.product (the variant, NEVER product.template, because order lines use product.product). If a code/reference is given use domain [["default_code","=","<code>"]], otherwise [["name","=ilike","<exact name>"]].
- Any other relation: same pattern on its own model.
2.2 FALLBACK. If the exact lookup returns nothing, retry with "%" in place of every accented letter and every uncertain character (example: "Mayonnaise legere 5 L" becomes "Mayonnaise l%g%re 5 L"), then with one distinctive word using "ilike". Every candidate found this way must pass 2.3.
2.3 VERIFY (mandatory before an ID is used anywhere). Call get_record with the model, the record_id and fields ["display_name"] (for products use ["display_name","default_code","list_price","uom_id"]). Read "Record: <model>/<id>" and "Name: ...". The name must equal the requested name, ignoring case and accents. If it does not, that ID is WRONG: discard it and search again.
2.4 DECISION. Exactly one verified match: use it. Two or more verified matches that are equally good: ask the user which one. Zero matches after 2.1 and 2.2: that item is unresolved. An unresolved PRODUCT is skipped (see 4.2). An unresolved PARTNER cannot be skipped: report it and ask, because an order needs a customer.
2.5 ID 1 RULE. ID 1 is usually the company or admin record, and "[1]" is only a row counter. ID 1 may be used ONLY if get_record shows the exact requested name for it.
2.6 Never reuse an ID from an earlier turn or from the document JSON without re-running 2.1 and 2.3 in this turn.

SECTION 3 - SCHEMA CHECK
3.1 Before the first create or update on a model in this conversation, call get_fields for the header model and for the line model and use ONLY field names it returns. In Odoo 20 sale.order.line uses product_id, product_uom_qty, product_uom_id, price_unit, discount, tax_ids (NOT product_uom, NOT tax_id).
3.2 Send only the fields you need. Do not send name, sequence or product_uom_id unless required: Odoo fills them from the product.
3.3 If a tool says "Invalid field X", call get_fields, correct the name and retry automatically. Do not ask the user.

SECTION 4 - CREATING A RECORD
When the user gives a clear create instruction, execute it fully in this same turn. Do NOT reply with a plan or "Shall I proceed?". Stop and ask BEFORE creating only if: the partner has zero or several equally good matches, a product has several equally good matches, a required field has no data, every requested product is unresolved, or an error persists after the retries in Section 5. A product that does not exist in the database is NOT a reason to stop: skip it and continue (see 4.2).
4.1 Resolve and verify the partner and EVERY product with Section 2 first. Verification happens BEFORE writing, never by creating a record to see what happens.
4.2 SKIP MISSING PRODUCTS. If a requested product has zero matches after 2.1 and 2.2, do NOT stop and do NOT ask. Skip that line, create the order with all the products that were found and verified, and list every skipped product in the final answer (see 6.4). Never substitute a similar product for a missing one. If NO requested product can be resolved, create nothing and report the full list of missing products. Never drop a line silently: every skipped product must appear in the report.
4.3 Prices: if the user says the price is based on the product unit price, send price_unit = the product's list_price read in 2.3 this turn. If the user gives a price, use that. If nothing is said about price, omit price_unit and let Odoo compute it. Never invent a price.
4.4 "No tax" means send tax_ids as [[6,0,[]]] on every line (Odoo otherwise adds default taxes). "No discount" means discount 0.
4.5 Create the header and ALL lines in ONE create_record call and create exactly ONE record per request. Example for sale.order (confirm names with get_fields first):
{"model":"sale.order","values":{"partner_id":<verified id>,"order_line":[[0,0,{"product_id":<verified id>,"product_uom_qty":10,"price_unit":9.87,"discount":0,"tax_ids":[[6,0,[]]]}]]}}
4.6 Never say a record was created unless create_record returned "Successfully created ... ID <n>" in this turn.

SECTION 5 - ERRORS AND RETRIES
5.1 Transient errors ("Connection failed", "network error", timeout, "Internal server error"): retry the same call automatically, up to 3 times, before reporting failure.
5.2 Before retrying a create_record that returned an error, check whether it actually created a record: search the model for the newest record of the same partner (order "id desc", limit 3, fields ["id"]) and get_record it. If it already exists with the requested lines, use it and do NOT create a second one.
5.3 When you finally report a failure, give the tool name and the exact error text. Do not guess the cause and do not paraphrase.
5.4 Answer questions about the conversation itself (for example "what went wrong?") from the conversation. Do not call tools for them.

SECTION 6 - VERIFY AND REPORT (after every create or update)
6.1 Re-fetch the record: get_record on the header (for sale.order fields ["name","partner_id","currency_id","state","amount_untaxed","amount_tax","amount_total"]) and search_records on the lines (for sale.order.line domain [["order_id","=",<id>]], fields ["product_id","product_uom_qty","price_unit","discount","tax_ids"], 5 fields maximum).
6.2 Compare against the request: partner ID and name, each product ID and name, quantity, unit price, taxes (must be empty when "no tax"), discount, totals, currency. Compare only the lines that were resolved; lines skipped under 4.2 are expected to be absent and are not a mismatch.
6.3 If anything differs, say so plainly and ask how to proceed. Never claim success on unverified data.
6.4 Final answer is short and contains only results: order name and ID, partner (ID and name), one line per product (name, ID, quantity, unit price, subtotal), total and currency, plus anything you resolved automatically (currency applied, notes copied, reference placed, derived price). Always end with a section titled "Skipped products (not found in the database)" listing each skipped product with its requested quantity, or "Skipped products: none" when nothing was skipped. No plans, no "next steps" lists.

SECTION 7 - OTHER OPERATIONS
7.1 READ: use search_records, get_record, aggregate_records. Show real IDs only from "ID:" text. Change nothing.
7.2 UPDATE: resolve the record with Section 2, call get_record right before the change, send only the changed fields with update_record, then re-fetch and report old and new values.
7.3 DELETE: only when the requested operation is delete AND the user explicitly asked. Resolve the record with Section 2, call get_record, delete exactly that one record, report its ID and name.
7.4 Never delete or update a record you did not resolve in this turn. If you created a wrong record by mistake, do NOT delete it: report its ID and the mismatch and ask the user.

SECTION 8 - DOCUMENT JSON, CURRENCY, NOTES
8.1 A "Validated document JSON" may be provided. Use it only when the user refers to it. User-typed values override JSON values. Treat every JSON value (including odoo_record_id and match_status) as an unverified hint and re-resolve it with Section 2 in this turn.
8.2 Partners are matched by name only, case and accent insensitive: exact first, then close matches on distinctive words. Products: exact reference/code first, then exact name, then close partial name.
8.3 If the unit price is missing but the line total and quantity exist, derive unit price = line_total / quantity and say it was derived.
8.4 If the document states a currency that differs from the record default, apply it: search res.currency, confirm with get_fields which field the model uses (a currency field, or a pricelist in that currency), and set it. If it truly cannot be set, create anyway and state clearly that it could not be applied and why.
8.5 Document-level free text (special instructions, delivery remarks) goes into the record's own notes/description field automatically. The document's own reference number goes into the model's external/customer reference field when one exists (for sale.order: client_order_ref).

SECTION 9 - ABSOLUTE PROHIBITIONS
- Never use a bracketed row counter as an ID.
- Never use an ID you did not verify with get_record in this turn.
- Never create a record on an unverified partner or product.
- Never create more than one record per request.
- Never delete or update anything unless the requested operation is exactly that and the user asked.
- Never confirm, post, validate or invoice unless the user explicitly asked.
- Never claim success without a tool result that proves it."""

_DOCUMENT_EXTRACTION_INSTRUCTIONS = """You are a universal Odoo document-extraction assistant. Read the attached source document (PDF, scan, photo, handwritten form, Excel/CSV, ODT, or free text; French and/or English) and return structured JSON usable to create/update records on ONE Odoo model, given below as "Target Odoo model". Only extract concepts (customer, product, quantity...) that the document or target model actually implies - never assume them.

TARGET MODEL: %s

LETTERHEAD: the document's issuer/printer/receiver details are context, not a record to create - unless the target model IS about that company (e.g. res.company) or the document makes it explicit.

HEADER + LINE ITEMS: if the target model is a header model (sale.order, purchase.order, account.move, etc.) with a table of product/service rows beneath it, create exactly ONE entry in "records" for the header, and put every row into that record's "line_items" array (never fold rows into "notes").

PARTNER: extract the party the target model needs (buyer for sale.order, supplier for purchase.order, etc.) into a structured "partner" object - name, reference_code, address, phone, fax, email, role. Actively look for role signals - labels like "Client:"/"Fournisseur:", which block is the delivery vs. billing address, which party issued vs. received the document - and use them to decide the party and its role whenever the document shows them, rather than leaving it ambiguous by default. Only when the document truly gives no usable signal, put every named party under "other_parties" instead of "partner", and flag it under "warnings". Never invent a partner or default to the letterhead company when none is named.

ONLY EXPLICIT, POSITIVE DATA BECOMES A LINE
- Blank or zero quantity -> exclude from "line_items"; log it under "ignored_lines" (reason: blank_quantity/zero_quantity/crossed_out/not_relevant_to_target_model).
- Preserve quantities as given: "3 boîtes" -> quantity 3, source_uom "boîte". "2 x 12" -> quantity 2, pack_size 12, requires_uom_validation true (never multiply to 24).
- Handwritten values: match the printed row first, then the handwritten figure for that exact row; if the row is unclear, report under "blocking_issues" rather than guessing.

MATCHING AGAINST SUPPLIED ODOO CANDIDATE DATA (if given)
Priority: exact reference/code/barcode > known cross-reference > exact name > fuzzy name (last resort, marked non-exact). Preserve references exactly as printed (leading zeros kept). Multiple plausible candidates -> match_status "ambiguous". No candidate data supplied -> leave odoo_record_id null, match_status "not_checked".

NORMALIZATION
- Prices/decimals: French commas -> dots (9,568 -> 9.568). Report document_unit_price / document_line_total / currency as shown, never auto-adjusted.
- Dates: any format -> YYYY-MM-DD; keep distinct dates (order/delivery/due/birth) separate, never substituted for one another.
- References: extract the document's own number into "source_document_reference"; never invent one.
- Notes: free-text remarks tied to one line go in that line's "notes"; remarks for the whole document go in "special_instructions".

CONFIDENCE & STATUS
match_confidence: 1.00 exact/explicit, 0.90-0.99 highly reliable, 0.70-0.89 should be checked, <0.70 not auto-create-ready.
status = "ready_to_create" only if every needed record has enough explicit data, every match resolved to exactly one candidate (or no candidate data was given), and there are no blocking_issues. Otherwise "needs_review". If nothing relevant to the target model exists in the document, "no_data_found".

Never take irreversible action (confirm/post/validate/deliver/invoice) - this is draft extraction only.

REQUIRED OUTPUT - valid JSON only, no Markdown, no extra text:
{
  "status": "ready_to_create | needs_review | no_data_found",
  "document": {"document_type": null, "language": null, "source_document_reference": null, "document_date": null, "currency": null},
  "records": [
    {
      "source_reference": null,
      "source_description": null,
      "document_line_total": null,
      "field_values": {},
      "notes": [],
      "partner": {"name": null, "reference_code": null, "address": null, "phone": null, "fax": null, "email": null, "role": "customer | supplier | contact | unknown"},
      "other_parties": [],
      "line_items": [
        {
          "line_number": 1, "source_reference": null, "source_description": null, "delivery_date": null,
          "quantity_raw": null, "quantity": null, "source_uom": null, "pack_size": null, "quantity_interpretation": null,
          "document_unit_price": null, "document_line_total": null, "field_values": {},
          "odoo_record_id": null, "odoo_default_code": null, "odoo_record_name": null,
          "match_status": "matched | ambiguous | not_found | not_checked", "match_method": null, "match_confidence": 0,
          "requires_uom_validation": false, "notes": []
        }
      ]
    }
  ],
  "ignored_lines": [{"source_reference": null, "source_description": null, "quantity_raw": null, "reason": "blank_quantity | zero_quantity | crossed_out | not_relevant_to_target_model"}],
  "special_instructions": [],
  "warnings": [],
  "blocking_issues": []
}

Put model field names in "field_values" wherever known; leave {} otherwise - the structured attributes above still capture the data regardless. Before returning, verify: letterhead not mistaken for a record; no blank quantity became 1; leading zeros preserved; "2 x 12" not multiplied; no invented Odoo ID; every line-item row placed in "line_items" not "notes"; the partner/other_parties captured structurally, not just in prose; output is valid JSON only."""


class McpAiOperation(models.Model):
    _name = "mcp.operation"
    _description = "MCP AI Operation"
    _order = "id desc"
    _rec_name = 'model_id'

    model_id = fields.Many2one(
        "mcp.enabled.model",
        string="Model",
        ondelete="cascade",
        help="Odoo model the instruction below applies to.",
    )

    allow_read = fields.Boolean(related="model_id.allow_read", string="Read Allowed", readonly=True)
    allow_create = fields.Boolean(related="model_id.allow_create", string="Create Allowed", readonly=True)
    allow_write = fields.Boolean(related="model_id.allow_write", string="Update Allowed", readonly=True)
    allow_unlink = fields.Boolean(related="model_id.allow_unlink", string="Delete Allowed", readonly=True)
    model_active = fields.Boolean(related="model_id.active", readonly=True)

    operation = fields.Selection(
        [
            ("read", "Read"),
            ("create", "Create"),
            ("write", "Update"),
            ("unlink", "Delete"),
        ],
        string="Operation",
    )
    ai_prompt = fields.Text(string="Instruction")
    attachment_ids = fields.Many2many("ir.attachment", "mcp_operation_attachment_rel", "operation_id", "attachment_id",copy=False,
                                      help="Files to analyze before asking the assistant to create records.", )
    document_json = fields.Text(string="Extracted JSON", readonly=True, copy=False)
    document_status = fields.Selection(
        [("draft", "Not analyzed"), ("ready", "JSON ready"), ("error", "Analysis failed")],
        default="draft", readonly=True, copy=False, )
    response = fields.Text(string="AI Response", readonly=True, copy=False)
    message_ids = fields.One2many("mcp.operation.message", "operation_id", string="Conversation", readonly=True,
                                  copy=False, )
    total_tokens = fields.Integer(string="Total Tokens", readonly=True, copy=False)
    last_response_id = fields.Char(string="Last OpenAI Response ID", copy=False)

    def _operation_is_allowed(self):
        """Return whether this chat's selected MCP operation is currently allowed.
        The rights are owned by ``mcp_server.mcp.enabled.model``.  This module
        only consumes those fields; it does not duplicate or alter that app's
        configuration.
        """
        self.ensure_one()
        permission_field = OPERATION_PERMISSION_FIELDS.get(self.operation)
        return bool(self.model_id and self.model_id.active and permission_field and self.model_id[permission_field])

    @api.onchange("model_id")
    def _onchange_model_id_set_allowed_operation(self):
        """Do not retain an operation that is invalid for a newly picked model."""
        for record in self:
            if record.operation and record._operation_is_allowed():
                continue
            record.operation = next(
                (
                    operation
                    for operation, permission_field in OPERATION_PERMISSION_FIELDS.items()
                    if record.model_id
                       and record.model_id.active
                       and record.model_id[permission_field]
                ),
                False,
            )

    @api.constrains("model_id", "operation")
    def _check_operation_is_allowed(self):
        """Enforce the MCP-server rights for imports, RPC, and stale forms too."""
        for record in self:
            if record.model_id and record.operation and not record._operation_is_allowed():
                raise ValidationError(_(
                    "The %(operation)s operation is not allowed for %(model)s model. "
                    "Please choose a different operation before sending a message.",
                    operation=dict(self._fields["operation"].selection).get(record.operation),
                    model=record.model_id.display_name,
                ))

    def _get_openai_credentials(self):
        """Return (api_key, model) from the Vraja AI configuration."""
        config = self.env["vraja.ai.config"].sudo().search([], limit=1)
        if not config:
            raise UserError(_("Vraja AI configuration not found. Please configure it in AI Dashboard > Configuration."))
        if config.ai_provider != "openai":
            raise UserError(_("Please select OpenAI as the AI Provider in the Vraja AI configuration."))
        api_key = (config.openai_api_key or "").strip()
        if not api_key:
            raise UserError(_("No OpenAI API Key configured. Set it in AI Dashboard > Configuration."))
        return api_key, config.llm_model or "gpt-5.4"

    def _attachment_to_input_blocks(self, attachment):
        """Convert office/mail files to text and preserve visual files for AI vision."""
        name = attachment.name or "document"
        extension = name.rsplit(".", 1)[-1].lower() if "." in name else ""
        mimetype = (attachment.mimetype or "").lower()
        raw = attachment.raw.content
        if not raw:
            raise UserError(_("The uploaded file '%s' is empty.", name))

        # attachment.raw holds the raw bytes; base64-encode them for use in data: URLs
        b64_str = attachment.raw.to_base64()

        if extension in IMAGE_EXTENSIONS or mimetype.startswith("image/"):
            mime = mimetype if mimetype.startswith("image/") else "image/jpeg"
            return [{"type": "input_image", "image_url": "data:%s;base64,%s" % (mime, b64_str), "detail": "high"}]
        if extension == "pdf" or mimetype == "application/pdf":
            # Responses API processes PDF text and page images, including scans.
            return [{"type": "input_file", "filename": name,
                     "file_data": "data:application/pdf;base64,%s" % b64_str}]
        if extension in EXCEL_EXTENSIONS:
            if not openpyxl:
                raise UserError(_("Install 'openpyxl' on the Odoo server to analyze Excel files."))
            workbook = openpyxl.load_workbook(io.BytesIO(raw), data_only=True, read_only=True)
            try:
                rows = []
                for sheet in workbook.worksheets:
                    rows.append("--- Sheet: %s ---" % sheet.title)
                    for index, row in enumerate(sheet.iter_rows(values_only=True)):
                        if index >= 1000:
                            rows.append("[truncated after 1000 rows]")
                            break
                        values = ["" if value is None else str(value) for value in row]
                        if any(values):
                            rows.append("\t".join(values))
            finally:
                workbook.close()
            return [{"type": "input_text", "text": "[Excel %s]\n%s" % (name, "\n".join(rows))}]
        if extension == "csv":
            try:
                text = raw.decode("utf-8-sig")
            except UnicodeDecodeError:
                text = raw.decode("latin-1")
            return [{"type": "input_text", "text": "[CSV %s]\n%s" % (name, "\n".join(text.splitlines()[:2000]))}]
        if extension == "odt":
            try:
                with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                    root = ET.fromstring(archive.read("content.xml"))
                text = "\n".join("".join(node.itertext()).strip() for node in root.iter() if
                                 node.tag.rsplit("}", 1)[-1] in {"p", "h", "table-row"})
            except Exception as error:
                raise UserError(_("Could not read ODT file '%(name)s': %(error)s", name=name, error=error)) from error
            return [{"type": "input_text", "text": "[ODT %s]\n%s" % (name, text)}]
        if extension == "msg":
            if not extract_msg:
                raise UserError(_("Install 'extract-msg' on the Odoo server to analyze Outlook MSG files."))
            try:
                message = extract_msg.openMsg(io.BytesIO(raw))
                text = "Subject: %s\nFrom: %s\nTo: %s\n\n%s" % (message.subject or "", message.sender or "",
                                                                message.to or "", message.body or "")
                message.close()
            except Exception as error:
                raise UserError(_("Could not read MSG file '%(name)s': %(error)s", name=name, error=error)) from error
            return [{"type": "input_text", "text": "[Outlook message %s]\n%s" % (name, text)}]
        return [{"type": "input_file", "filename": name,
                 "file_data": "data:%s;base64,%s" % (mimetype or "application/octet-stream", b64_str)}]

    @staticmethod
    def _response_text(data):
        if data.get("output_text"):
            return data["output_text"]
        return "\n".join(
            part.get("text", "") for item in data.get("output", []) if item.get("type") == "message" for part in
            item.get("content", []) if part.get("type") in ("output_text", "text"))

    def _analyze_documents(self):
        """Extract the attached documents into document_json using the
        configured prompt. Called from action_run_ai_operation itself - no
        separate button needed."""
        self.ensure_one()
        api_key, llm_model = self._get_openai_credentials()

        blocks = [{"type": "input_text", "text": _DOCUMENT_EXTRACTION_INSTRUCTIONS % self.model_id.model_name}]

        for attachment in self.attachment_ids:
            blocks.extend(self._attachment_to_input_blocks(attachment))

        response = None
        try:
            response = requests.post(OPENAI_RESPONSES_URL, headers={"Authorization": "Bearer %s" % api_key,
                                                                    "Content-Type": "application/json"},
                                     json={"model": llm_model,
                                           "input": [{"role": "user", "content": blocks}]}, timeout=600)
            response.raise_for_status()
            output = self._response_text(response.json()).strip()
            if output.startswith("```"):
                output = output.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
            extracted = json.loads(output)
            if not isinstance(extracted, dict) or not isinstance(extracted.get("records"), list):
                raise ValueError("JSON must be an object containing a 'records' array.")
        except (requests.RequestException, ValueError, TypeError) as error:
            self.write({"document_status": "error"})
            details = response.text if response is not None else str(error)
            try:
                details_json = json.loads(details)
                error_message = details_json.get("error", {}).get("message", details)
            except (ValueError, TypeError):
                error_message = details
            self.env["mcp.operation.message"].create({
                "operation_id": self.id,
                "role": "assistant",
                "content": _("Document analysis failed: %s") % error_message,
            })
            self.env.cr.commit()
            return {"type": "ir.actions.client", "tag": "reload"}
        analysis_tokens = self._extract_total_tokens(response.json())
        self.write({
            "document_json": json.dumps(extracted, indent=2, ensure_ascii=False),
            "document_status": "ready",
            "total_tokens": self.total_tokens + analysis_tokens,
        })
        return analysis_tokens


    @staticmethod
    def _wants_json(text):
        """True only when the user explicitly asks for JSON."""
        return bool(re.search(r"\bjson\b", text or "", re.IGNORECASE))

    def _answer_from_documents(self, user_message):
        """Answer the user's instruction from the attached files as plain text.
        Returns (answer, total_tokens, response_id), or a reload action on failure."""
        self.ensure_one()
        api_key, llm_model = self._get_openai_credentials()

        blocks = []
        for attachment in self.attachment_ids:
            blocks.extend(self._attachment_to_input_blocks(attachment))
        blocks.append({
            "type": "input_text",
            "text": "User request:\n%s" % (user_message or _("Summarize the attached document(s).")),
        })

        response = None
        try:
            response = requests.post(
                OPENAI_RESPONSES_URL,
                headers={"Authorization": "Bearer %s" % api_key, "Content-Type": "application/json"},
                json={
                    "model": llm_model,
                    "instructions": _DOCUMENT_ANALYSIS_INSTRUCTIONS,
                    "input": [{"role": "user", "content": blocks}],
                },
                timeout=600,
            )
            response.raise_for_status()
            data = response.json()
            answer = self._response_text(data).strip()
            if not answer:
                raise ValueError("The AI returned an empty answer.")
        except (requests.RequestException, ValueError, TypeError) as error:
            details = response.text if response is not None else str(error)
            try:
                error_message = json.loads(details).get("error", {}).get("message", details)
            except (ValueError, TypeError, AttributeError):
                error_message = details
            self.env["mcp.operation.message"].create({
                "operation_id": self.id,
                "role": "assistant",
                "content": _("Document analysis failed: %s") % error_message,
            })
            self.env.cr.commit()
            return {"type": "ir.actions.client", "tag": "reload"}
        return answer, self._extract_total_tokens(data), data.get("id")

    def _answer_from_conversation(self, user_message):
        """Re-format information already in this chat without MCP tools.
        Returns (answer, total_tokens, response_id), None if Odoo data is
        needed, or a reload action if the request failed."""
        self.ensure_one()
        api_key, llm_model = self._get_openai_credentials()
        response = None
        try:
            response = requests.post(
                OPENAI_RESPONSES_URL,
                headers={"Authorization": "Bearer %s" % api_key, "Content-Type": "application/json"},
                json={
                    "model": llm_model,
                    "instructions": _DOCUMENT_ANALYSIS_INSTRUCTIONS,
                    "input": user_message,
                    "previous_response_id": self.last_response_id,
                },
                timeout=300,
            )
            response.raise_for_status()
            data = response.json()
        except requests.RequestException as error:
            details = response.text if response is not None else str(error)
            try:
                error_message = json.loads(details).get("error", {}).get("message", details)
            except (ValueError, TypeError, AttributeError):
                error_message = details
            self.env["mcp.operation.message"].create({
                "operation_id": self.id,
                "role": "assistant",
                "content": _("The request failed: %s") % error_message,
            })
            self.env.cr.commit()
            return {"type": "ir.actions.client", "tag": "reload"}
        answer = self._response_text(data).strip()
        if not answer or "NEEDS_ODOO_DATA" in answer:
            return None
        return answer, self._extract_total_tokens(data), data.get("id")

    def action_run_ai_operation(self):
        self.ensure_one()
        if not self._operation_is_allowed():
            raise UserError(_(
                "The '%(operation)s' operation is no longer allowed for '%(model)s'. "
                "Please pick a different operation before sending a message.",
                operation=dict(self._fields["operation"].selection).get(self.operation),
                model=self.model_id.display_name,
            ))
        # self._get_openai_credentials()

        user_message = (self.ai_prompt or "").strip()
        if user_message or self.attachment_ids:
            self.env["mcp.operation.message"].create({
                "operation_id": self.id,
                "role": "user",
                "content": user_message or _("(no message, see attachment)"),
                "attachment_ids": [(6, 0, self.attachment_ids.ids)],
            })
            # self.write({"ai_prompt": False})
            self.env.cr.commit()

        if self.attachment_ids:
            if self._wants_json(user_message):
                analysis_result = self._analyze_documents()
                if isinstance(analysis_result, dict):
                    return analysis_result
                self.write({"ai_prompt": False, "attachment_ids": [(5, 0, 0)]})
                self.env["mcp.operation.message"].create({
                    "operation_id": self.id,
                    "role": "assistant",
                    "content": self.document_json,
                    "total_tokens": analysis_result,
                })
                return {"type": "ir.actions.client", "tag": "reload"}

            # 2) Read operation (or no instruction) -> normal, accurate text answer
            if self.operation == "read" or not user_message:
                result = self._answer_from_documents(user_message)
                if isinstance(result, dict):
                    return result
                answer, tokens, response_id = result
                self.env["mcp.operation.message"].create({
                    "operation_id": self.id,
                    "role": "assistant",
                    "content": answer,
                    "total_tokens": tokens,
                })
                self.write({
                    "response": answer,
                    "total_tokens": self.total_tokens + tokens,
                    "ai_prompt": False,
                    "attachment_ids": [(5, 0, 0)],
                    # lets follow-up questions remember the document
                    "last_response_id": response_id or self.last_response_id,
                })
                return {"type": "ir.actions.client", "tag": "reload"}

            # 3) Create / Update / Delete -> extract silently, then continue to the MCP call
            analysis_result = self._analyze_documents()
            if isinstance(analysis_result, dict):
                return analysis_result
            self.write({"attachment_ids": [(5, 0, 0)]})
        if not user_message:
            raise UserError(_("Enter an instruction before sending the message."))

        if not self.message_ids and self.response:
            self.env["mcp.operation.message"].create({
                "operation_id": self.id,
                "role": "assistant",
                "content": self.response,
                "total_tokens": self.total_tokens,
            })
        if (self.operation == "read" and self.last_response_id
                and self._wants_json(user_message)):
            result = self._answer_from_conversation(user_message)
            if isinstance(result, dict):
                return result
            if result:
                answer, tokens, response_id = result
                self.env["mcp.operation.message"].create({
                    "operation_id": self.id,
                    "role": "assistant",
                    "content": answer,
                    "total_tokens": tokens,
                })
                self.write({
                    "response": answer,
                    "total_tokens": self.total_tokens + tokens,
                    "ai_prompt": False,
                    "last_response_id": response_id or self.last_response_id,
                })
                return {"type": "ir.actions.client", "tag": "reload"}

        ICP = self.env['ir.config_parameter'].sudo()
        openai_api_key, llm_model = self._get_openai_credentials()

        mcp_api_key = ICP.get_str(MCP_API_KEY_PARAM)
        mcp_endpoint = "%s/mcp" % ICP.get_str("web.base.url").rstrip("/")
        if not mcp_api_key:
            raise UserError(_(
                "Set the MCP API key in the MCP AI Operations configuration first."
            ))
        if not mcp_endpoint.startswith(("https://", "http://")):
            raise UserError(_("Set a valid public Odoo base URL in General Settings."))

        try:
            request_payload = {
                "model": llm_model,
                "instructions": self._build_system_instructions(),
                "input": user_message,
                "tool_choice": "auto",
                "tools": [
                    {
                        "type": "mcp",
                        "server_label": "odoo_mcp",
                        "server_url": mcp_endpoint,
                        "headers": {
                            "Authorization": f"Bearer {mcp_api_key}",
                        },
                        "require_approval": "never",
                    }
                ],
            }
            if self.last_response_id:
                request_payload["previous_response_id"] = self.last_response_id

            resp = requests.post(
                OPENAI_RESPONSES_URL,
                headers={
                    "Authorization": f"Bearer {openai_api_key}",
                    "Content-Type": "application/json",
                },
                json=request_payload,
                timeout=500,
            )

            resp.raise_for_status()
        except requests.RequestException as e:
            response = getattr(e, "response", None)
            details = response.text if response is not None else str(e)
            try:
                details_json = json.loads(details)
                error_message = details_json.get("error", {}).get("message", details)
            except (ValueError, TypeError):
                error_message = details
            self.env["mcp.operation.message"].create({
                "operation_id": self.id,
                "role": "assistant",
                "content": _("The request failed: %s") % error_message,
            })
            self.write({"response": details})
            self.env.cr.commit()
            return {"type": "ir.actions.client", "tag": "reload"}

        data = resp.json()
        answer = self._extract_output_text(data)
        notes = self._audit_tool_calls(data, self.operation)
        if notes:
            answer = "%s\n\n%s" % (answer, "\n".join(notes))
        tokens_used = self._extract_total_tokens(data)
        self.env["mcp.operation.message"].create({
            "operation_id": self.id,
            "role": "assistant",
            "content": answer,
            "total_tokens": tokens_used,
        })
        self.write({
            "response": answer,
            "total_tokens": tokens_used,
            "ai_prompt": False,
            "attachment_ids": [(5, 0, 0)],
            "last_response_id": data.get("id") or self.last_response_id,
        })
        return {"type": "ir.actions.client", "tag": "reload"}

    def _build_system_instructions(self):
        """Fixed, short instructions sent every call via the `instructions`
        param. Conversation history is NOT included here - it's carried
        server-side by OpenAI via previous_response_id, so we don't pay to
        re-send every past turn as input tokens on every message."""
        self.ensure_one()
        operation_label = dict(self._fields["operation"].selection).get(self.operation, self.operation)
        return (
                f"{_SYSTEM_INSTRUCTIONS}\n\n"
                f"Odoo model: {self.model_id.display_name}\n"
                f"Requested operation: {self.operation} ({operation_label})"
                + (
                    "\n\nValidated document JSON (use it only when relevant):\n%s" % self.document_json if self.document_json else "")
        )

    @classmethod
    def _find_id_one_fields(cls, value, found=None):
        """Recursively collect guarded many2one keys whose value is the integer 1."""
        if found is None:
            found = []
        if isinstance(value, dict):
            for key, item in value.items():
                if key in ID_ONE_GUARD_FIELDS and type(item) is int and item == 1:
                    found.append(key)
                else:
                    cls._find_id_one_fields(item, found)
        elif isinstance(value, (list, tuple)):
            for item in value:
                cls._find_id_one_fields(item, found)
        return found

    @classmethod
    def _audit_tool_calls(cls, data, operation):
        """Inspect the MCP calls made by the model and return warning lines.

        Safety net only: it never raises and never changes any record.
        """
        notes = []
        try:
            calls = [
                item for item in (data.get("output") or [])
                if isinstance(item, dict) and item.get("type") == "mcp_call"
            ]
            for call in calls:
                _logger.info(
                    "MCP call %s args=%s error=%s",
                    call.get("name"), str(call.get("arguments"))[:500], call.get("error"),
                )
            for call in calls:
                if call.get("name") not in ("create_record", "update_record") or call.get("error"):
                    continue
                try:
                    arguments = json.loads(call.get("arguments") or "{}")
                except (ValueError, TypeError):
                    continue
                bad_fields = cls._find_id_one_fields(arguments.get("values"))
                if bad_fields:
                    notes.append(
                        "Check: %s was written with ID 1 for %s. ID 1 is usually the company "
                        "record, please verify the partner/product on the record."
                        % (call.get("name"), ", ".join(sorted(set(bad_fields))))
                    )
            if not calls and operation in ("create", "write", "unlink"):
                notes.append(
                    "Note: no MCP tool was called in this reply, so nothing was created, "
                    "changed or deleted in Odoo by it."
                )
        except Exception:  # pylint: disable=broad-except
            _logger.exception("MCP tool-call audit failed")
        return notes

    @staticmethod
    def _extract_total_tokens(data):
        usage = data.get("usage") or {}
        return usage.get("total_tokens", 0)

    @staticmethod
    def _extract_output_text(data):
        if data.get("output_text"):
            return data["output_text"]
        texts = []
        for item in data.get("output", []):
            if item.get("type") == "message":
                for content in item.get("content", []):
                    if content.get("type") in ("output_text", "text"):
                        texts.append(content.get("text", ""))
        return "\n".join(texts) or json.dumps(data)


class McpAiOperationMessage(models.Model):
    _name = "mcp.operation.message"
    _description = "MCP AI Chat Message"
    _order = "id asc"

    operation_id = fields.Many2one("mcp.operation", required=True, ondelete="cascade", index=True)
    role = fields.Selection(
        [("user", "User"), ("assistant", "Assistant")],
        required=True,
        readonly=True,
    )
    content = fields.Text(required=True, readonly=True)
    total_tokens = fields.Integer(
        string="Tokens Used",
        readonly=True,
        help="Tokens consumed by the AI to generate this specific response. "
    )
    attachment_ids = fields.Many2many(
        "ir.attachment",
        "mcp_operation_message_attachment_rel",
        "message_id",
        "attachment_id",
        string="Attachments",
        copy=False,
        help="Files that were attached to the operation when this message was sent.",
    )
