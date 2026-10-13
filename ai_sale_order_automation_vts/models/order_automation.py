# -*- coding: utf-8 -*-
import base64
import csv
import io
import json
import logging
import re
import unicodedata
import zipfile
import xml.etree.ElementTree as ET
import requests

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# ----------------------------------------------------------------------
# CLAUDE (ANTHROPIC) API — replaces the OpenAI Responses API endpoint.
# ----------------------------------------------------------------------
ANTHROPIC_MESSAGES_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"
MCP_BETA_HEADER = "mcp-client-2025-11-20"

try:
    import openpyxl
except ImportError:
    openpyxl = None
try:
    import pymupdf
except ImportError:
    pymupdf = None
try:
    import extract_msg
except ImportError:
    extract_msg = None

IMAGE_EXTENSIONS = ("jpg", "jpeg", "png", "gif", "webp", "bmp", "heic")
EXCEL_EXTENSIONS = ("xlsx", "xlsm", "xls")
MSG_EXTENSIONS = ("msg",)
ODT_EXTENSIONS = ("odt",)
ODT_CONTENT_TAG_NS = {"p", "h"}
MAX_EXCEL_ROWS = 500
MAX_CSV_LINES = 1000
MAX_PDF_PAGES = 30
PDF_TEXT_MIN_CHARS_PER_PAGE = 100
PDF_ROW_Y_TOLERANCE = 5.0       # points - max drift from a row's running-average y-center before starting a new row
PDF_COLUMN_GAP_THRESHOLD = 8.0  # points - horizontal gap that signals a new column, not just a space
PDF_RENDER_ZOOM = 5.5556

DEFAULT_EXTRACTION_INSTRUCTIONS = """
You are an AI document-processing assistant integrated with Odoo.

Your job is to analyze a customer order document and convert it into structured data that can safely be used to create a **draft Odoo Sale Order**.

The source document may be a PDF, scanned PDF, phone photograph, handwritten order sheet, Excel/CSV spreadsheet, ODT/document, Outlook message, structured purchase order, or free-form customer order. It may be a full product catalogue where only some rows carry a quantity.

Documents may be written in any language. Read labels in the document's own language.

---

# COMPANY CONTEXT

The company that RECEIVES the order is the seller (our company). In the document it may appear as: Supplier, Vendor, Seller, "From", or under the equivalent word in the document's language.

Never identify the seller/supplier as the customer.

The actual customer (the party placing the order) may appear under labels such as: Customer, Client, Buyer, Bill To, Ship To, Deliver To, Store/Site/Branch name, Customer Code, Delivery Address, or the equivalent words in the document's language.

If an ODOO COMPANY block is supplied, use it to recognise which party is our own company.

---

# PRIMARY OBJECTIVE

Extract:

1. Customer
2. Customer code
3. Customer purchase order/reference
4. Order date
5. Requested delivery date
6. Delivery address
7. Ordered products
8. Product reference/code
9. Product description
10. Ordered quantity
11. Unit of measure / packaging
12. Document price information when available
13. Special delivery/order instructions

Then compare the extracted information with the Odoo customer/product candidates supplied in the request (if any).

Never invent an Odoo customer ID, product ID, UoM ID, product reference, price, quantity, or date.

---

# MANDATORY QUANTITY-COLUMN SCAN — DO THIS BEFORE ANYTHING ELSE

Before extracting anything else, do a dedicated first pass whose only job is to find every mark in the quantity column (labelled "Qty", "Quantity", "Ordered", or the equivalent word in the document's language)

1. Go down that column ONE ROW AT A TIME, top to bottom, for every page/image. For each row, look only at that row's own cell and ask: "is there any mark here at all?" — a full digit, a partial digit, a faint pencil stroke, a tick, or anything that is not simply empty paper.
2. On a real order form most rows are blank and only a few carry a number. That sparsity is normal. Do NOT skim: each mark is exactly the data you are here to extract.
3. Marks are often clustered on consecutive rows. When you find one, check every row immediately above and below it individually. Do not assume a cluster shares one quantity — each row's own mark belongs only to that row.
4. Build an internal list of every row where you found a mark. `order_lines` must contain at least one entry for every row on this list.
5. Only then read references, descriptions and UoMs for those rows and classify the remaining rows per the ZERO QUANTITY AND EMPTY ROWS rule.
6. Before returning, re-examine every row you are about to mark `blank_quantity`. Missing a real mark is worse than misreading a digit, because a missed row disappears from the order. If you are genuinely unsure whether a faint mark is a quantity, include the row in `order_lines` with your best reading and add a note flagging the uncertainty. (This does not relax the GOLDEN RULE: the line is "a mark exists but is hard to read", never "no mark exists but a quantity seems plausible".)

---

# ROW COMPLETENESS — MANDATORY RECONCILIATION

No product row may be silently dropped, on any page.

1. Count every row that names a product (with or without quantity) across ALL attached pages/images. Exclude only section headers, blank separators and footer text.
2. Go page by page, top to bottom. Every row with a positive quantity becomes one entry in `order_lines`; every other product row becomes one entry in `ignored_lines`.
3. Every product row must be in exactly one of the two lists.
4. `len(order_lines) + len(ignored_lines)` MUST equal the count from step 1. Report it in `total_source_rows`.
5. If they do not match, find the missing row. An uncertain row still goes in `ignored_lines` with a note in `notes`, never dropped.

---

# GOLDEN RULE — NEVER FABRICATE A QUANTITY

A quantity may only be reported if you can point to actual visual evidence for that exact row: a printed number in the quantity column, or a handwritten mark unambiguously beside that row.

Ask: "what mark did I actually see for THIS row?" If the honest answer is "nothing" or "I'm inferring it because nearby rows have quantities", the row has NO quantity and does not belong in `order_lines`. A product appearing in a catalogue is never, by itself, evidence of an order.

This rule guards against writing a quantity where the cell is genuinely empty. It does not discard a row where a mark plainly exists but is faint or hard to read — such a row stays in `order_lines` with a note.

For every order line, `quantity_raw` must contain the literal text/mark actually seen (e.g. "6", "1 carton", "10"). `quantity` is arithmetic derived from that literal mark and never replaces it. No literal mark = no line.

---

# MOST IMPORTANT RULE

**Only products with an explicitly ordered positive quantity become Sale Order lines.**

* Quantity blank → DO NOT order
* Quantity 0 / "0 kg" / "0 box" → DO NOT order
* Quantity crossed out → DO NOT order
* Quantity written as 6 → quantity_raw "6"
* "3 boxes" → quantity_raw "3 boxes", source_uom "box"
* "20 kg" → quantity_raw "20 kg", source_uom "kg"
* "2 x 12" → keep "2 x 12" in quantity_raw; do not multiply it unless CUSTOMER SPECIFIC INSTRUCTIONS say so
* "1 carton" → quantity_raw "1 carton", source_uom "carton"

Never assume that a blank product row means quantity 1.

---

# HANDWRITTEN / SCANNED DOCUMENT RULES

The printed table can contain dozens of products while the customer writes quantities only beside the ones they want.

1. Read the printed product reference.
2. Read the printed product description.
3. Read the printed UoM.
4. Identify the quantity belonging to that exact row.
5. Never move a quantity to an adjacent product unless the row association is clear.
6. If a mark cannot be confidently associated with a row, report a blocking issue.
7. Never guess unreadable handwriting.
8. Do not include rows with no printed/handwritten positive quantity.
9. `source_description` must contain ONLY the product name exactly as on the document. Never add meta-commentary such as "(handwritten)", "(unclear)", "(bottom of page)" — that text is later used as a product search term. Put such remarks in `notes`.

---

# ROW INTEGRITY — NEVER BLEND TWO ROWS

A row may lack some fields (no reference, no UoM) — leave them null. What is never acceptable is combining fields from two different rows into one line.

Every field you fill (`source_reference`, `source_description`, `quantity`) must come from the same single row. Before finalizing a line, point to the exact row it represents. If a handwritten mark sits between two rows, use the row's printed baseline to decide; if you cannot tell, treat the row as uncertain instead of guessing.

---

# CUSTOMER IDENTIFICATION RULES

Priority:

1. Exact Odoo customer code/reference
2. Explicit customer name
3. Customer email
4. Customer address
5. Customer phone
6. Delivery recipient/name
7. Fuzzy name matching only as a last resort

If an exact customer code corresponds to exactly one Odoo candidate, prefer it.
If more than one customer may match, return `"match_status": "ambiguous"` and do not mark the order ready for creation.
Never use the seller/supplier as the customer.

---

# PRODUCT MATCHING RULES

Priority:

1. Exact internal reference / SKU
2. Exact barcode
3. Known customer-specific product reference
4. Exact supplier/customer reference mapping
5. Exact normalized product name
6. Fuzzy product-name matching only as a fallback

## Reference handling

Preserve references exactly as written: `00303` must stay `00303`, never `303`.

You may test a leading-zero-normalized value only when the exact reference did not match AND the normalized value identifies exactly one Odoo product. Mark such a match as non-exact.

## Odoo IDs

Populate `odoo_product_id`, `odoo_uom_id`, `odoo_default_code` only when present in the Odoo candidate data supplied. Otherwise leave them null. Never invent them.

## Description

Preserve the source description. Return both `source_description` and `odoo_product_name` when a product is matched. Never silently replace the source description.

---

# QUANTITY RULES

Extract both the original quantity text and the normalized number.

| Document says | quantity_raw | quantity | other fields |
|---|---|---|---|
| 6 | "6" | 6 | |
| 20 kg | "20 kg" | 20 | source_uom "kg" |
| 3 boxes | "3 boxes" | 3 | source_uom "box" |
| 2 x 12 | "2 x 12" | 2 | pack_size 12 |

`quantity_raw`, `source_uom` and `pack_size` ALWAYS hold what the customer wrote, unchanged.
`quantity` is the number written, unless CUSTOMER SPECIFIC INSTRUCTIONS define a conversion (see UNIT HANDLING). Never multiply "2 x 12" into 24 on your own.

---

# UOM AND PACKAGING

Preserve the source UoM in `source_uom`, never overwrite it. Common examples: kg, g, L, cl, box, carton, pack, tray, bucket, bag, piece, bottle, can, crate, jar.

Map to an Odoo UoM only when Odoo UoM/product data is supplied.
If the source UoM differs from the product's sale unit, always go with the product's sale unit.
`odoo_uom_id` is always the product's own sale UoM from the Odoo data — never the customer's unit unless they are identical.
Set `requires_uom_validation` to true ONLY when a conversion required by CUSTOMER SPECIFIC INSTRUCTIONS cannot be done safely.

---
# UNIT HANDLING

Never convert units on your own. For every order line:
* `quantity_raw` = the literal text seen, `source_uom` = the unit as written, `quantity` = the number written.
* `pack_size` and `quantity_interpretation` stay null and `requires_uom_validation` stays false.
* If the ordered unit clearly differs from the size shown in the product name (for example "Rice 2.5 kg" ordered as "10 kg"), keep the number as written and add a note: "ordered in <unit>; product name shows <size>; quantity kept as written".
* Apply a unit conversion only if CUSTOMER SPECIFIC INSTRUCTIONS below explicitly describe it. In that case write the full arithmetic in `quantity_interpretation`.
* Document prices are kept exactly as printed.

## Definitions

* ORDERED UNIT = the unit the customer wrote with the quantity; else the unit in that row's UoM column; else the unit in the column header; else the quantity is unit-less.
* PACK CONTENT = the amount contained in one product unit, read only from:
  1. the product name/description on the SAME row, or
  2. the name of the matched Odoo product (when Odoo data is supplied).
  Never take it from another row, from Odoo UoM fields, from guessing, or from "typical" pack sizes.

Reading a size from a name: accept only a number followed by a measurement unit ("250g", "250 gr", "0,25 kg", "75cl", "1 L", "50 m") or a count marker ("x 12", "12 pieces", "box of 12"). Normalize decimal commas. Ignore numbers that are not sizes (product numbers, percentages, years). If the name has more than one possible size (e.g. "6 x 1L"), do not guess: quantity null, requires_uom_validation true, blocking issue.

## MEASURE-ORDERED RULE (MANDATORY)

When the ordered unit is a measure (kg / g / L ...) and the product name on the same row contains a pack size (e.g. "2.5 kg"), the number the customer wrote is the TOTAL amount, not the number of packs.
`quantity` = number written ÷ pack size.
Exception: if CUSTOMER SPECIFIC INSTRUCTIONS below explicitly say how this customer writes such quantities, follow them instead.
## Procedure (for every order line)

1. Read the ordered quantity and ORDERED UNIT exactly as written.
2. Determine PRODUCT UNIT and PACK CONTENT from the allowed sources.
3. Decide:
   a. Quantity is truly unit-less, OR the ordered unit is a measure and the name has no pack size → NO conversion; `quantity` = the number written. (If the ordered unit is kg/g/L and the name has a pack size, apply the MEASURE-ORDERED RULE instead.)
   b. Ordered unit differs from the product unit but measures the same dimension → CONVERT.
   c. Ordered unit is a packaging/count word (carton, bucket, box, tray, bag, piece, bottle ...):
      - If the amount per such unit is stated on the same row (e.g. "Sausage 2,5kg" ordered in "pieces", or "carton of 12") → convert per step 4.
      - If NOT stated → do NOT convert and do NOT leave `quantity` empty: `quantity` = number written, `source_uom` = word as written, requires_uom_validation false, add note "ordered in <word>; amount per <word> not stated, quantity kept as written". No blocking issue.
   d. Ordered unit is a MEASURE but the size in the name is a count or another dimension (e.g. "Eggs x 12" ordered in kg, no weight per piece) → `quantity` null, requires_uom_validation true, blocking issue.
   e. PRODUCT UNIT unknown and name has no pack size → no conversion; `quantity` = number written; add note "product unit not verified".
4. Calculation for (b) and (c): convert the ordered amount into a base unit of its dimension using exact standard factors; convert PACK CONTENT into the same base unit; quantity = ordered amount ÷ PACK CONTENT.
5. Write the full arithmetic in `quantity_interpretation`.
6. Verify by multiplying back: `quantity` × PACK CONTENT must equal the ordered amount exactly. If not, redo it.
7. NEVER round:
   * PRODUCT UNIT is discrete (bag, bottle, piece, box ...) and the result is not whole → quantity null, requires_uom_validation true, exact result in `quantity_interpretation`, blocking issue.
   * PRODUCT UNIT is a continuous measure (per kg, per L, per m) → fractional result is valid; keep exact decimals.
8. If converting between two MEASURE units and you are not 100% sure of the factor → quantity null, requires_uom_validation true, blocking issue. (Does not apply to packaging/count words with no stated content — those follow 3c.)
9. Never convert silently. Whenever `quantity` differs from the number written, `quantity_interpretation` must contain the full arithmetic.

## Examples (illustrative only)

| Row description | Customer wrote | Result |
|---|---|---|
| Dried herb 250 g (bag) | 5 kg | 5000 g ÷ 250 g = 20 → quantity 20 |
| Rice 2.5 kg (pack), UoM column "Kg" | 10 | MEASURE-ORDERED RULE: 10 kg ÷ 2.5 kg = 4 → quantity_raw "10", source_uom "Kg", quantity 4, interpretation "10 kg total; 10 kg ÷ 2.5 kg per pack = 4 packs" |
| Olive oil 75cl | 3 L | 300 cl ÷ 75 cl = 4 → quantity 4 |
| Product sold per kg | 500 g | 0.5 (continuous unit, valid) |
| Sauce 300g | 1 kg | 1000 ÷ 300 = 3.33, not whole → quantity null, blocking issue |
| Butter 250g | 2 cartons (content unknown) | quantity 2 as written + note "ordered in cartons; amount per carton not stated" |
| Eggs x 12 | 2 kg | Measure ordered, count product → quantity null, blocking issue |
| Flour (sold per kg) | 1,000 KG | Same unit → quantity 1 |

## Prices

Do not convert `document_line_total`; keep it as printed.
If a conversion changed the quantity, the printed unit price refers to the customer's unit, not the product unit.
If no conversion was applied, keep `document_unit_price` as printed.

---

# PRICE RULES

Documents may contain unit price, price excl. tax, price incl. tax, line total, VAT, supplier price, or customer PO price.

Extract prices when available, but never assume the document price becomes the Odoo sale price.

```json
{
  "document_unit_price": 9.94,
  "document_line_total": 99.40,
  "currency": "USD"
}
```

The Odoo application decides whether to use the Odoo pricelist price or the customer's document price. Never overwrite an Odoo price because a price exists in the file.

Normalize decimal commas: `9,94` → `9.94`, `9,568` → `9.568`. Thousands separators must not be confused with decimals.

---

# DATE RULES

Normalize all dates to `YYYY-MM-DD`.
Detect the document's date format (e.g. `DD/MM/YYYY`, `MM/DD/YYYY`, or written text such as "Thursday 13 August 2026").

Distinguish between order date, requested delivery date, and document printing date. Never use the printing date as the delivery date unless the document explicitly says so.

---

# ORDER REFERENCE

Extract references such as PO Number, Order No., Customer PO, Reference into `customer_order_reference`. Do not invent one when missing.

---

# DELIVERY INSTRUCTIONS

Extract delivery time windows, receiving hours, unloading instructions, requested delivery date, contact person, phone number, comments/remarks into `special_instructions`. Preserve important wording.

---

# ZERO QUANTITY AND EMPTY ROWS

Rows with blank, null, 0, "0 kg", "0 box", or clearly crossed-out quantity must not become Sale Order lines.
Record every one under `ignored_lines` — mandatory, so the reconciliation count can succeed.

---

# UNMATCHED ORDERED PRODUCTS

Never silently discard a product with a positive ordered quantity.
If the quantity is positive but the product cannot be matched to Odoo: include it in `order_lines`, set `odoo_product_id` null, `match_status` "not_found", and add a blocking issue.

---

# CONFIDENCE RULES

* `1.00` = exact/explicit
* `0.90–0.99` = highly reliable
* `0.70–0.89` = likely but requires checking
* below `0.70` = do not auto-create

Prefer deterministic identifiers over reading confidence alone.

---

# READY TO CREATE RULE

Return `"status": "ready_to_create"` only when:

1. Exactly one customer has been matched.
2. The customer has a valid Odoo partner ID.
3. At least one positive-quantity order line exists.
4. Every positive-quantity product is matched to an Odoo product.
5. Quantities are readable.
6. UoMs are sufficiently validated.
7. Every line needing conversion has `quantity` filled with the verified converted value and full arithmetic in `quantity_interpretation`. No line has `quantity` null.
8. No blocking issues exist.

Otherwise return `"needs_review"`. If no real order is found, return `"no_order_found"`.

---

# DO NOT CONFIRM THE SALE ORDER

The output creates a **draft sale.order / quotation** only. Do not confirm the order, reserve stock, create delivery or invoice.

---

# INPUT PROVIDED BY APPLICATION

The request contains the source document(s). It may also contain an ODOO COMPANY name. Customer candidates, product candidates and Odoo UoM data are NOT provided in this step: perform extraction only, leave all Odoo IDs null, and set match_status to "not_checked".

---

# REQUIRED OUTPUT

Return valid JSON only. No Markdown, no text before or after.

```json
{
  "status": "ready_to_create | needs_review | no_order_found",

  "total_source_rows": 0,

  "document": {
    "document_type": null,
    "language": null,
    "customer_order_reference": null,
    "order_date": null,
    "requested_delivery_date": null,
    "currency": null
  },

  "customer": {
    "source_name": null,
    "customer_code": null,
    "email": null,
    "phone": null,
    "delivery_address": null,
    "odoo_partner_id": null,
    "odoo_customer_name": null,
    "match_status": "matched | not_found | not_checked",
    "match_method": null,
    "match_confidence": 0
  },

  "supplier": {
    "source_name": null,
    "is_our_company": false
  },

  "order_lines": [
    {
      "line_number": 1,

      "source_reference": null,
      "source_description": null,

      "quantity_raw": null,
      "quantity": null,

      "source_uom": null,
      "pack_size": null,
      "quantity_interpretation": null,

      "document_unit_price": null,
      "document_line_total": null,

      "odoo_product_id": null,
      "odoo_default_code": null,
      "odoo_product_name": null,
      "odoo_uom_id": null,
      "odoo_uom_name": null,

      "match_status": "matched | ambiguous | not_found | not_checked",
      "match_method": null,
      "match_confidence": 0,

      "requires_uom_validation": false,
      "notes": []
    }
  ],

  "ignored_lines": [
    {
      "source_reference": null,
      "source_description": null,
      "quantity_raw": null,
      "reason": "blank_quantity | zero_quantity | crossed_out | not_an_order_line"
    }
  ],

  "special_instructions": [],

  "warnings": [],

  "blocking_issues": [],

  "odoo_draft_order": {
    "partner_id": null,
    "client_order_ref": null,
    "requested_delivery_date": null,
    "lines": [
      {
        "product_id": null,
        "quantity": null,
        "uom_id": null
      }
    ]
  }
}
``` 
`quantity` in `order_lines` and `odoo_draft_order.lines[].quantity` are the same final number, expressed in the product's own unit (converted when needed). `uom_id` is the product's own sale UoM from the Odoo data, or null when no Odoo data is supplied.

---

# FINAL VALIDATION BEFORE RETURNING JSON

Verify internally:

* The seller/supplier was not mistaken for the customer.
* Every positive quantity was captured; no blank quantity was turned into 1; zero quantities were excluded.
* Quantities were associated with the correct rows; no output line blends fields from two rows.
* Leading zeros in references were preserved.
* Units were not converted unless CUSTOMER SPECIFIC INSTRUCTIONS explicitly required it.
* No `source_description` contains meta-commentary.
* Every line's ordered unit was compared with its product unit and every needed conversion was performed and verified by multiplying back.
* Pack content came only from the same row or the Odoo candidate.
* No fractional result was rounded for a discrete product unit.
* No `quantity` was set to null just because a packaging/count word had no stated content — the customer's number was kept with a note.
* `odoo_draft_order.lines[].quantity` equals that line's `quantity` in `order_lines`.
* Output contains valid JSON only.
"""

DEFAULT_CREATION_INSTRUCTIONS = """
You are an Odoo data assistant. You act only through the connected MCP tools against live data. Never answer from memory or guesswork - every fact, ID, name, or amount must come from a tool call you actually made this conversation.
The company receiving the order is our own company (the seller). If it appears as supplier/vendor/seller in the source data, it must never be selected as the customer. This only applies to the customer-search path (Rule 3) - it does not apply when partner_id_hint is provided (Rule 2).

Make every tool call the rules below require, including all create_record calls in Rule 8 and the read-back in Rule 9. Never skip a required call to save time, and never write the final JSON before the required calls are done. Do not add calls beyond what the rules ask for.
Rules:

1. NEVER WRITE A PLACEHOLDER: never write a generic, sample, or placeholder value (such as "demo", "test", "sample", "example", "n/a", or similar) into any output field - not as a customer name, product name, reference, or anything else - unless a tool call you made this turn genuinely and verifiably returned that exact value as the real record's own stored name. This applies with full force to product matching in Rule 4: a product literally named "demo", "test product", "sample product", or anything else generic is NEVER a valid match for a real order line unless the source_description you were given also explicitly says that. If you notice you are about to write something that looks like a placeholder rather than a value taken directly from a tool result, stop and treat that line/field as unresolved instead.

2. CUSTOMER - HINT PROVIDED = ALWAYS USE IT, NO CHECKS: if partner_id_hint is provided, use it directly as the customer id. Do NOT search for it, do NOT verify it, do NOT check its supplier rank, customer rank, company, or any other field - take the id exactly as given and proceed straight to Rule 4 (product matching). Do not overwrite partner_id_hint with anything else, and never skip creating the sale order because of anything related to this customer id - a provided hint is always sufficient to proceed.

3. CUSTOMER - NO HINT PROVIDED: only if partner_id_hint is NOT provided: take the name to search from partner_name_hint if given, otherwise from customer.source_name. Never read customer.source_name when partner_name_hint is present. Search res.partner for that name, case/accent/spacing-insensitive. If an exact search finds nothing, retry once with a partial/contains-style search on the same name (matching the first word, or dropping legal suffixes like "Ltd", "Inc", "LLC") Only after both attempts genuinely return nothing (or return several equally plausible candidates with no way to tell them apart) conclude the customer is not found. If the search does not produce exactly one confident match, you have NO valid customer id: do NOT write any partner_id, do NOT write id 1, the current company's own partner, or any other record as a stand-in. The only two valid outcomes are: (a) exactly one verified match -> use its real id, or (b) no confident match -> status "customer_not_found", customer_match.found = false, customer_match.odoo_partner_id = null, no Sale Order created.

4. PRODUCTS - MATCH EACH LINE (fast path): process every order_lines entry with quantity greater than 0 (entries with a null quantity are not searched - they go to skipped_products per Rule 6). All text comparisons in this rule are case-insensitive and accent-insensitive (é = e, À = a, etc.) - never reject a match purely because of case or accent differences. For each line, follow in order and stop at the first step that produces a match:

   4a. CODE MATCH (fastest, try first when source_reference is present): search product.product for default_code equal to source_reference, case-insensitive, but preserve digits and leading zeros exactly as written (00303 stays 00303 - a search for "00303" must not match a product coded "303" or vice versa). If exactly one product has that code, take it directly as matched for this line and move to the next line - no further search or verification needed for this line.

   4b. DESCRIPTION MATCH (when there is no source_reference, or 4a found no code match): run one search on product.product name using ilike against the full source_description (one call, limit 30, no category/company/sale_ok filter). From the results:
      - If a candidate's name is effectively a 100% match to the description (same words, ignoring case, accents, punctuation, spacing, and word order) -> take it directly.
      - Else, if a candidate's name is a close match - roughly 90% similar, meaning it shares all the core identifying words (the product's actual name/flavor/type) and differs only in minor ways (extra packaging word, brand suffix, spacing, word order, an abbreviation) -> take that candidate. Example: source_description "Tomato paste 2.5kg" and Odoo product "Tomato Paste 2,5 kg" share every core word and differ only in case and spacing -> match.
      - If more than one candidate clears the 90% bar, take the one closest to the full description; if genuinely tied with no way to prefer one, treat the line as ambiguous (Rule 5).
      - If no candidate clears even the 90% bar, no match was found for this line (Rule 5).

   4c. NEVER FILL A GAP: never use a random, first, default, or id = 1 product for a line, and never write a product id you did not copy from an actual row returned by a tool call in 4a or 4b. Never reuse the same odoo_product_id for two different order_lines unless you independently searched each one and both searches genuinely returned that same id - if you catch yourself about to write the same id twice for two different source_description values, stop and re-run each search rather than writing it. If the 4b search returns zero rows, or returns rows but none of their names share any real words with source_description, that line has NO match - it goes to skipped_products (Rule 5), full stop. Do not then substitute the only product in the catalog, id 1, or any other product as a stand-in "best effort" - an empty or irrelevant search result is not license to guess, it is the signal to skip the line.

   4d. THE ROW NUMBER IS NOT AN ID: search results print rows as "[1]", "[2]", ... - that bracketed number is only the position of the row in the result list, NOT the record id. A product id is valid only if the tool output explicitly shows it as the record's id (for example "id: 123" or a record header such as "product.product/123"). If a search result does not show the numeric id of the row you want, you do NOT have an id for that product yet: obtain it with another tool call that displays the id explicitly, and if that is impossible, the line goes to skipped_products with the reason "product id not returned by tool". Never guess an id, never take one from your memory, and never take one from an earlier unrelated call.

5. PRODUCTS - AMBIGUOUS OR MISSING: if a line is genuinely ambiguous between candidates (per 4b) or no candidate matched at all, skip that line - it goes into skipped_products only, with a reason naming what was searched (e.g. "no match: searched default_code '00303' (0 results) and description ilike 'vegetable stock' (0 candidates >= 90%)"). Never put a guessed, placeholder, or unverified id into matched_products.

6. QUANTITY AND PRICE - USE AS GIVEN: for every matched line, use quantity and document_unit_price exactly as provided in the input - never look up, recalculate, or invent a price. Do not resolve or validate unit of measure - let the product's own default apply.

7. DECIDE THE OUTCOME: no customer resolved -> status "customer_not_found", no Sale Order, fill failure_reason with why. Customer resolved but zero products matched -> status "no_products_matched", no Sale Order, fill failure_reason with why. Customer resolved (whether via hint or search) and at least one product matched -> proceed to create the order using only the matched lines; unresolved lines go to skipped_products and do not block creation. You are NOT allowed to report status "created" as an intention, plan, or assumption - only report "created" once the create tool call in Rule 8 has actually returned a real order id AND the read-back in Rule 9 has genuinely confirmed that order exists with at least one order line. If the create tool call errors, is refused, times out, or is never actually made, or if the Rule 9 read-back cannot confirm the order, set status to "creation_failed" instead (never "created", never leave it ambiguous, never leave sale_order.created as false while status says "created") and put the exact, specific reason - including the tool's own error text if there was one - in failure_reason.

8. CREATE THE SALE ORDER (TWO STEPS - THIS IS HOW THE ODOO MCP TOOL WORKS):
   Step 8a - create the order HEADER only: call create_record on model sale.order with ONLY these values: partner_id = the resolved customer's real id from Rule 2 or Rule 3 (never an unverified value, never id 1 unless it was genuinely and verifiably resolved as the correct match via Rule 3); client_order_ref = the extraction's customer_order_reference (document.customer_order_reference) if present, otherwise omit it; commitment_date = the requested delivery date (document.requested_delivery_date, format YYYY-MM-DD) if present, otherwise omit it. The field "requested_delivery_date" does NOT exist on sale.order - never send it, the correct field is commitment_date. NEVER pass order_line inside the sale.order create call: nested line objects are rejected by this tool with the error "unhashable type: 'dict'".
   Step 8b - create each line separately: for every matched product make one create_record call on model sale.order.line with values order_id = the id returned by step 8a, product_id = the verified numeric id from Rule 4, product_uom_qty = quantity, price_unit = document_unit_price when given (otherwise omit it so Odoo's default applies). Never pass a product or customer by name - always the verified numeric id. Keep the order in draft/quotation state - never confirm it.

9. VERIFY WHAT WAS ACTUALLY CREATED - MANDATORY, ONE CALL ONLY: after the lines are created, make a single read call that returns, for that exact sale.order id, its real partner_id and its real order lines (for example search_records on sale.order.line with domain order_id = that id and fields product_id, name, product_uom_qty). Report the real, just-read values in verification.actual_partner_id and verification.actual_order_line_count - never the values you intended to write, only what this read-back returned. Compare each read-back line's product name with the source_description you meant to order: if a line shows an unrelated or generic product name, say so plainly in failure_reason (and set status "creation_failed"). If the create tool call itself returned an error or no id, do not attempt this read-back at all - go straight to status "creation_failed" and put the tool's own error text in failure_reason. If the read-back fails, returns no record, or shows zero order lines, the order was NOT actually created correctly: set status to "creation_failed" (never "created") and state exactly what the read-back returned in failure_reason. This is the only verification call required - do not add further read-back or re-confirmation calls beyond this one.

10. NEVER FABRICATE: never invent an id, name, price, quantity, or date - only report what a tool call actually returned. Never default to record id 1, the current company, or "the first record" when a name or hint is given - always resolve it through a real, verified search, or use the hint directly per Rule 2, never guess.

11. IF BLOCKED: if the create action fails or is blocked by a tool error, stop and report that tool's own error in the order note rather than working around it silently or guessing an alternative action.

12. FINAL ANSWER FORMAT: your very last message must be ONLY the JSON object matching the required schema - no text before it, no text after it, no markdown fences. Any narration you write while working must come before the tool calls, never in the final message.

13. EMPTY VALUES IN THE JSON: the output schema does not allow null. Every field must always be present. When a text value is unknown or not applicable write "" (empty string); when a number, quantity or id is unknown or not applicable write 0. Examples: failure_reason "" when nothing failed; sale_order.sale_order_id 0 and sale_order.sale_order_name "" when no order was created; customer_match.odoo_partner_id 0 when the customer was not found; uom_id 0 and uom_name "" when not known. A 0 or "" never means a real record - real ids are always positive integers obtained from a tool call. A line whose odoo_product_id would be 0 must NEVER be listed in matched_products - it goes to skipped_products. Status "created" is only allowed when sale_order.created is true and sale_order.sale_order_id is a real positive id returned by the create_record tool call; otherwise use "creation_failed" (or "no_products_matched" when no line has a real product id).

Required output: return valid JSON matching the schema exactly, no extra text, no explanations before or after. Every id in matched_products and in the created sale_order must be a real integer obtained from a tool call this turn (or, for the customer, from partner_id_hint per Rule 2) - never null, never a placeholder. Any line that could not be resolved that way belongs only in skipped_products.
"""

PRODUCT_MAPPING_RULE_ANCHOR = "4. PRODUCTS - MATCH EACH LINE"

PRODUCT_MAPPING_RULE_INSERT = """0. KNOWN PRODUCT MAPPINGS - MANDATORY, CHECK THIS BEFORE RULE 4 (HIGHEST PRIORITY): the user payload includes a `known_product_mappings` field containing CSV text (header row + one row per mapping) with columns: source_product_name, odoo_product_id, odoo_product_name. For EVERY order line, before doing anything in Rule 4 below, first compare that line's source_description (and source_reference, if present) against the source_product_name column of known_product_mappings - case/accent/spacing-insensitive, allowing minor spelling/punctuation/word-order differences. If it matches, take that row's odoo_product_id DIRECTLY as the matched product for this line and put it straight into matched_products - do NOT run a product.product search tool call for it, do NOT second-guess it, do NOT apply Rule 4's own matching logic to it, and do NOT skip it into skipped_products for any reason once a mapping row matches. This mapping was confirmed by a human and overrides catalogue search entirely. Only when a line's source_description does not reasonably match ANY row in known_product_mappings do you fall through to Rule 4 below and search the catalogue normally for that line.
0a. MAPPING QUANTITY - MANDATORY, OVERRIDES RULE 6 AND RULE 8b FOR MAPPED LINES: `mapping_quantity` is the number of units of the mapped Odoo product that make up ONE unit of the source product exactly as written on the document. For every line matched through a known_product_mappings row you MUST compute: final_quantity = (the line's `quantity` from the extraction) x mapping_quantity. Use final_quantity in EVERY place that line's quantity is written: as product_uom_qty in that line's sale.order.line create_record call (Rule 8b), as `quantity` in matched_products, and as `quantity` in sale_order.order_lines. This overrides the "use quantity exactly as provided" wording of Rule 6 and the `product_uom_qty = quantity` wording of Rule 8b, for these lines only. Example: the document line is "Soap 5kg" with extraction quantity 5, the mapping row maps it to the Odoo product "Soap 2.5kg" with mapping_quantity 2 -> final_quantity = 5 x 2 = 10, so product_uom_qty = 10. Do the multiplication exactly, keep decimals, never round. If mapping_quantity is 1, empty or missing, the quantity is unchanged. A line whose extraction quantity is null or 0 is not multiplied. Lines that were NOT matched through a known_product_mappings row are never multiplied.

0b. PRICE FOR MAPPED LINES - OVERRIDES RULE 8b price_unit FOR MAPPED LINES: when the mapping_quantity of the matched row is not 1, document_unit_price refers to the source product's unit, not to the Odoo product's unit, so do NOT send price_unit in that line's create_record call (omit it so Odoo's own price applies). When mapping_quantity is 1, handle the price as Rule 8b says.

0c. MAPPING CHECK: before writing the final JSON, confirm for every mapped line that final_quantity = extraction quantity x mapping_quantity, that the same number was sent as product_uom_qty in the create_record call, and that the read-back in Rule 9 shows that same product_uom_qty. If any of these differ, fix it (or report it in failure_reason) instead of silently keeping the unmultiplied quantity.
"""

PRODUCT_MAPPING_INSTRUCTIONS = """
---

# KNOWN PRODUCT MAPPINGS - HIGHEST PRIORITY FOR PRODUCT MATCHING

The user payload includes a `known_product_mappings` field containing CSV
text (header row + one row per mapping) with columns:
source_product_name, odoo_product_id, odoo_product_name.

Each row means: "When the source document names a product matching that
row's source_product_name (exactly, or with only minor spelling/case/
spacing differences), use that row's odoo_product_id as the Odoo product
for that line - do not search the catalogue or pick a different product
for it."

These mappings were confirmed by a human who manually corrected the AI's
product matching before, so they are more reliable than a fresh catalogue
search. For every order line, first check whether it reasonably matches a
row in `known_product_mappings`; only if none does, fall back to the
normal product-matching rules (Rule 4) below.

## MAPPING QUANTITY (0a) - MANDATORY

`mapping_quantity` is the number of units of the mapped Odoo product that
make up ONE unit of the source product exactly as written on the document.
For every line matched through a known_product_mappings row:

final_quantity = (the line's `quantity` from the extraction) x mapping_quantity

Use final_quantity as product_uom_qty when creating the sale.order.line, as
`quantity` in matched_products and as `quantity` in sale_order.order_lines.
This overrides the "use quantity exactly as provided" rule for these lines
only.

Example: the document line is "Soap 5kg" with extraction quantity 1 (one
5 kg pack); the mapping row maps "Soap 5kg" to the Odoo product
"Soap 2.5kg" with mapping_quantity 2 -> final_quantity = 1 x 2 = 2, so 2
units of "Soap 2.5kg" are added instead of 1. With an extraction quantity
of 3 the final quantity is 3 x 2 = 6.

If mapping_quantity is 1, empty or missing, the quantity is unchanged.
Do the multiplication exactly, keep decimals, never round. A line whose
extraction quantity is null is not multiplied. Lines that were not matched
through known_product_mappings are never multiplied.

## PRICE FOR MAPPED LINES (0b)

When the mapping_quantity of the matched row is not 1, the
document_unit_price refers to the source product's unit, not to the mapped
Odoo product's unit, so do NOT send price_unit for that line (omit it so
Odoo's own price applies).
"""

CUSTOMER_INSTRUCTION_START = "### CUSTOMER SPECIFIC INSTRUCTIONS - START ###"
CUSTOMER_INSTRUCTION_END = "### CUSTOMER SPECIFIC INSTRUCTIONS - END ###"
CUSTOMER_INSTRUCTION_RE = re.compile(
    r"\n*" + re.escape(CUSTOMER_INSTRUCTION_START)
    + r".*?" + re.escape(CUSTOMER_INSTRUCTION_END) + r"\n*",
    re.DOTALL,
)


def _safe_text(value, max_len=None):
    """Coerce any AI-returned value into a safe display string.
    Prevents crashes when the AI returns a dict/list/number instead
    of a plain string for a field we expect to be text."""
    if value is None or value is False:
        text = ""
    elif isinstance(value, str):
        text = value
    elif isinstance(value, dict):
        text = (
            value.get("message")
            or value.get("reason")
            or value.get("text")
            or value.get("description")
            or json.dumps(value, ensure_ascii=False)
        )
    elif isinstance(value, (list, tuple)):
        text = "; ".join(_safe_text(v) for v in value if v)
    else:
        text = str(value)
    return text[:max_len] if max_len else text


def _normalize_words(text):
    """Lowercase, strip accents/punctuation, and return the set of
    words (3+ chars) in `text`. Used only as a lightweight, independent
    sanity check that a real Odoo product name has SOME real overlap
    with what was actually ordered - never trusts the AI's own claim
    that a match is correct."""
    text = _safe_text(text).lower()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return {w for w in re.findall(r"[a-z0-9]+", text) if len(w) >= 3}


class AiSaleOrderDraft(models.Model):
    _name = "order.automation"
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = "AI Sale Order Draft"
    _order = "create_date desc"

    name = fields.Char(default=lambda self: _("New"), copy=False, readonly=True)
    partner_id = fields.Many2one(
        "res.partner",
        string="Customer",
        required=True,
        tracking=True,
    )
    use_selected_partner = fields.Boolean(
        string="Create Using Selected Customer",
        help="When enabled, the Sale Order is created for the Customer "
             "selected above. When disabled, the AI looks up the customer "
             "name detected from the document instead.",
        default=True
    )
    attachment_ids = fields.Many2many(
        "ir.attachment",
        "ai_sale_order_draft_attachment_rel",
        "draft_id",
        "attachment_id",
        string="Source Files",
        help="Upload images, PDF, Excel/CSV files, or capture a photo. "
             "Any number of files - they are treated as one combined order.",
    )
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("analyzed", "Analyzed"),
            ("done", "Sale Order Created"),
            ("error", "Error"),
        ],
        default="draft",
        tracking=True,
        copy=False,
    )
    auto_create_sale_order = fields.Boolean(
        string="Auto-Create Sale Order",
        help="When enabled, 'Analyze with AI' becomes a single step: as "
             "soon as the AI JSON is parsed, the matched lines are immediately "
             "sent to Odoo via MCP to create the sale order, with no manual "
             "review in between. When disabled (default), analysis and "
             "creation stay two separate steps so you can review/correct "
             "matches first.",
    )
    extraction_instructions = fields.Text(
        string="Document Extraction Prompt",
        default=lambda self: self.env["ai.prompt"].get_prompt_text("extraction_instructions"),
        copy=False,
        help="The exact instructions sent to the AI when 'Analyze with AI' "
             "runs. Editable - any change made here is used as-is the next "
             "time this draft is analyzed.",
    )
    creation_instructions = fields.Text(
        string="Sale Order Creation Prompt",
        default=lambda self: self.env["ai.prompt"].get_prompt_text("creation_instructions"),
        help="The exact instructions sent to the AI when 'Create Sale "
             "Order' runs. Editable - any change made here is used as-is "
             "the next time this draft's sale order is created.",
    )
    ai_raw_response = fields.Text(
        string="AI JSON Response",
        readonly=True,
        copy=False,
        help="The exact structured JSON returned by the extraction call. "
             "This is what actually gets sent, unmodified, to the MCP creation "
             "call - the lines below are only a human-readable view of it.",
    )
    detected_customer_name = fields.Char(readonly=True, copy=False)
    ai_customer_match_status = fields.Selection(
        [
            ("matched", "Matched"),
            ("not_found", "Not Found"),
        ],
        string="Customer Match (from MCP creation)",
        readonly=True,
        copy=False,
    )
    extraction_status = fields.Selection(
        [
            ("ready_to_create", "Ready to Create"),
            ("needs_review", "Needs Review"),
            ("no_order_found", "No Order Found"),
        ],
        string="Extraction Status",
        readonly=True,
        copy=False,
        help="Status returned by the AI after analyzing the document.",
    )
    creation_status = fields.Selection(
        [
            ("created", "Created"),
            ("customer_not_found", "Customer Not Found"),
            ("no_products_matched", "No Products Matched"),
            ("creation_failed", "Creation Failed"),
        ],
        string="Creation Status",
        readonly=True,
        copy=False,
        help="Status returned by the AI after creating the sale order.",
    )

    ai_create_response = fields.Text(
        string="MCP Creation Response",
        readonly=True,
        copy=False,
        help="The structured JSON returned by the sale-order-creation call "
             "(including which lines it matched/created and which it could "
             "not match).",
    )
    error_message = fields.Text(readonly=True, copy=False)
    sale_order_id = fields.Many2one(
        "sale.order", readonly=True, copy=False, tracking=True
    )
    line_ids = fields.One2many("ai.sale.order.draft.line", "draft_id", string="Lines")
    ignored_line_ids = fields.One2many(
        "ai.sale.order.draft.ignored.line", "draft_id", string="Ignored Lines"
    )

    # ------------------------------------------------------------------
    # Token usage tracking (Logs tab)
    # ------------------------------------------------------------------
    llm_model_used = fields.Char(readonly=True, string="LLM Model", copy=False)
    extraction_input_tokens = fields.Integer(readonly=True, string="Extraction Input Tokens", copy=False)
    extraction_output_tokens = fields.Integer(readonly=True, string="Extraction Output Tokens", copy=False)
    extraction_total_tokens = fields.Integer(readonly=True, string="Extraction Total Tokens", copy=False)
    creation_input_tokens = fields.Integer(readonly=True, string="Creation Input Tokens",copy=False)
    creation_output_tokens = fields.Integer(readonly=True, string="Creation Output Tokens", copy=False)
    creation_total_tokens = fields.Integer(readonly=True, string="Creation Total Tokens", copy=False)
    total_tokens = fields.Integer(readonly=True,string="Total Tokens",copy=False,compute="_compute_total_tokens",store=True,help="Extraction call tokens + Sale Order creation call tokens, for this draft.",)

    @api.depends("extraction_total_tokens", "creation_total_tokens")
    def _compute_total_tokens(self):
        for draft in self:
            draft.total_tokens = ((draft.extraction_total_tokens or 0)+ (draft.creation_total_tokens or 0))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", _("New")) == _("New"):
                vals["name"] = (self.env["ir.sequence"].next_by_code("order.automation")or _("New"))
        return super().create(vals_list)

    def unlink(self):
        attachments = self.mapped("attachment_ids")
        result = super().unlink()

        if attachments:
            attachments.unlink()
        return result

    # ------------------------------------------------------------------
    # Customer specific instructions
    # ------------------------------------------------------------------
    @staticmethod
    def _apply_customer_instruction(prompt_text, partner):
        """Return `prompt_text` with the customer-specific instruction block
        of `partner` added at the end.

        Any block added earlier (for a previously selected customer) is
        removed first, so changing the customer never stacks instructions
        and every other manual edit of the prompt is preserved."""
        prompt_text = CUSTOMER_INSTRUCTION_RE.sub("", prompt_text or "")
        instruction = (partner.ai_order_instruction or "").strip() if partner else ""
        if not instruction:
            return prompt_text
        block = (
            "%s\n"
            "The following instructions are specific to the customer \"%s\". "
            "Apply them in addition to all the rules above.\n\n"
            "%s\n"
            "%s\n"
        ) % (
            CUSTOMER_INSTRUCTION_START,
            partner.display_name,
            instruction,
            CUSTOMER_INSTRUCTION_END,
        )
        return "%s\n\n%s" % (prompt_text.rstrip(), block)

    @api.onchange("partner_id")
    def _onchange_partner_id_customer_instruction(self):
        prompt_model = self.env["ai.prompt"]
        for draft in self:
            for field_name in ("extraction_instructions", "creation_instructions"):
                base_text = draft[field_name] or prompt_model.get_prompt_text(field_name)
                draft[field_name] = self._apply_customer_instruction(
                    base_text, draft.partner_id)

    # ------------------------------------------------------------------
    # Settings / MCP helpers
    # ------------------------------------------------------------------
    def _get_settings(self):
        icp = self.env["ir.config_parameter"].sudo()
        ai_config = self.env['vraja.ai.config'].sudo().search([], limit=1)
        if not ai_config:
            raise UserError(_('Vraja AI configuration not found. Please configure it in AI Dashboard > Configuration.'))
        if ai_config.ai_provider != 'claude':
            raise UserError(_('Please select Claude as the AI Provider in the Vraja AI configuration.'))
        claude_api_key = (ai_config.claude_api_key or '').strip()
        if not claude_api_key:
            raise UserError(_('No Claude API Key configured. Set it in AI Dashboard > Configuration.'))
        claude_key = ai_config.claude_api_key
        model = ai_config.claude_llm_model or "claude-sonnet-4-6"
        max_tokens = ai_config.claude_max_tokens or 8192
        mcp_key = icp.get_str("ai_sale_order_automation_vts.mcp_api_key")
        base_url = icp.get_str("web.base.url")
        if not mcp_key:
            raise UserError(_(
                    "No Odoo MCP API key configured. Generate one from My "
                    "Profile > Account Security > New API Key (scope 'MCP "
                    "only'), then paste it into Settings > General Settings > "
                    "AI Sale Order Creator."
                ))
        if not base_url:
            raise UserError(_(
                "The 'web.base.url' system parameter is empty; it is "
                "required to build the MCP endpoint URL."
            ))
        return claude_key, model, max_tokens, mcp_key, base_url.rstrip("/")

    @staticmethod
    def _mcp_tool_def(mcp_key, base_url):
        server_def = {
            "type": "url",
            "url": f"{base_url}/mcp",
            "name": "odoo_mcp",
            "authorization_token": mcp_key,
        }
        toolset_def = {
            "type": "mcp_toolset",
            "mcp_server_name": "odoo_mcp",
        }
        return server_def, toolset_def

    @staticmethod
    def _build_mapping_csv(product_mappings):
        """Serialize ai.product.mapping records as CSV text (header + rows)
        instead of a JSON array of objects."""
        if not product_mappings:
            return ""

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "source_product_name",
            "odoo_product_id",
            "odoo_product_name",
            "mapping_quantity",
        ])
        for mapping in product_mappings:
            writer.writerow([
                mapping.source_product_name or "",
                mapping.product_id.id,
                mapping.product_id.display_name or "",
                mapping.quantity or 1.0,
            ])
        return output.getvalue()

    # ------------------------------------------------------------------
    # File -> AI input content blocks
    # ------------------------------------------------------------------
    def _prepare_image_b64(self, datas, mimetype):
        """Prepare image for vision analysis while preserving handwriting quality.
        Unchanged - this only produces a base64 string; provider-specific
        wrapping happens in _attachment_to_content_blocks / _pdf_to_content_blocks."""
        try:
            raw = base64.b64decode(datas)

            # Only resize very large images.
            # Preserve original image whenever possible.
            if len(raw) > 20_000_000:
                from odoo.tools import image_process

                resized = image_process(datas,size=(4500, 4500),)

                if resized:
                    return (resized.decode()if isinstance(resized, bytes)else resized)

        except Exception:
            _logger.warning(
                "AI Sale Order Creator: image resize failed, using original.",
                exc_info=True,
            )
        return datas.decode() if isinstance(datas, bytes) else datas
    def _excel_to_text(self, raw_bytes, filename):
        if openpyxl is None:
            raise UserError(
                _(
                    "The 'openpyxl' Python library is required to read Excel "
                    "file '%s'. Please ask your administrator to install it "
                    "(pip install openpyxl) on the Odoo server.",
                    filename,
                )
            )
        try:
            workbook = openpyxl.load_workbook(
                io.BytesIO(raw_bytes), data_only=True, read_only=True
            )
        except Exception as exc:
            raise UserError(
                _(
                    "Could not read Excel file '%(name)s': %(err)s",
                    name=filename,
                    err=str(exc),
                )
            ) from exc

        lines = []
        for sheet in workbook.worksheets:
            lines.append(f"--- Sheet: {sheet.title} ---")
            for i, row in enumerate(sheet.iter_rows(values_only=True)):
                if i >= MAX_EXCEL_ROWS:
                    lines.append(f"... [truncated after {MAX_EXCEL_ROWS} rows]")
                    break
                cells = ["" if c is None else str(c) for c in row]
                if any(cell.strip() for cell in cells):
                    lines.append("\t".join(cells))
        workbook.close()
        return "\n".join(lines)

    @staticmethod
    def _csv_to_text(raw_bytes):
        try:
            text = raw_bytes.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = raw_bytes.decode("latin-1")
        lines = text.splitlines()
        if len(lines) > MAX_CSV_LINES:
            lines = lines[:MAX_CSV_LINES] + [
                f"... [truncated after {MAX_CSV_LINES} lines]"
            ]
        return "\n".join(lines)

    def _msg_to_text(self, raw_bytes, filename):
        if extract_msg is None:
            raise UserError(_(
                "The 'extract-msg' Python library is required to read Outlook "
                "message file '%s'. Please ask your administrator to install it "
                "(pip install extract-msg) on the Odoo server.",
                filename,
            ))
        try:
            msg = extract_msg.openMsg(io.BytesIO(raw_bytes))
            try:
                parts = [
                    f"Subject: {msg.subject or ''}",
                    f"From: {msg.sender or ''}",
                    f"To: {msg.to or ''}",
                    f"Date: {msg.date or ''}",
                    "",
                    msg.body or "",
                ]
            finally:
                msg.close()
        except Exception as exc:
            raise UserError(_(
                "Could not read Outlook message file '%(name)s': %(err)s",
                name=filename, err=str(exc),
            )) from exc
        return "\n".join(parts)

    def _odt_to_text(self, raw_bytes, filename):
        try:
            with zipfile.ZipFile(io.BytesIO(raw_bytes)) as archive:
                xml_bytes = archive.read("content.xml")
            root = ET.fromstring(xml_bytes)
        except Exception as exc:
            raise UserError(_(
                "Could not read OpenDocument file '%(name)s': %(err)s",
                name=filename, err=str(exc),
            )) from exc

        lines = []
        for elem in root.iter():
            tag = elem.tag.rsplit("}", 1)[-1]
            if tag in ODT_CONTENT_TAG_NS:
                text = "".join(elem.itertext()).strip()
                if text:
                    lines.append(text)
        return "\n".join(lines)

    @staticmethod
    def _pdf_page_to_row_text(page):
        words = page.get_text("words")
        if not words:
            return ""

        words = sorted(words, key=lambda w: ((w[1] + w[3]) / 2, w[0]))

        rows = []
        current_row = []
        row_y_sum = 0.0
        row_y_count = 0
        for w in words:
            y_center = (w[1] + w[3]) / 2
            if current_row and abs(y_center - (row_y_sum / row_y_count)) > PDF_ROW_Y_TOLERANCE:
                rows.append(current_row)
                current_row = []
                row_y_sum = 0.0
                row_y_count = 0
            current_row.append(w)
            row_y_sum += y_center
            row_y_count += 1
        if current_row:
            rows.append(current_row)

        lines = []
        for row in rows:
            row_sorted = sorted(row, key=lambda w: w[0])
            parts = []
            prev_x1 = None
            for x0, y0, x1, y1, text, *rest in row_sorted:
                if prev_x1 is not None and (x0 - prev_x1) > PDF_COLUMN_GAP_THRESHOLD:
                    parts.append(" | ")
                elif parts:
                    parts.append(" ")
                parts.append(text)
                prev_x1 = x1
            lines.append("".join(parts))
        return "\n".join(lines)

    @staticmethod
    def _pdf_page_image_bytes(page):
        """Return PNG bytes for a page with no text layer, rendered through
        PyMuPDF's normal page-rendering pipeline at a fixed high DPI. This
        was chosen over extracting an embedded image directly: some scanned
        PDFs stack multiple images on one page (e.g. a faint/blank base
        layer plus the real content layer on top), and picking 'the image
        covering the most area' silently grabbed the wrong (blank) layer
        on a real document. get_pixmap() composites every layer exactly
        as a normal PDF viewer would, so the correct visible content
        always comes through - while still rendering at a resolution WE
        control, avoiding an LLM provider's own internal PDF-to-image
        downsampling that caused a misread digit on a separate,
        single-image page."""
        matrix = pymupdf.Matrix(PDF_RENDER_ZOOM, PDF_RENDER_ZOOM)
        pix = page.get_pixmap(matrix=matrix)
        return pix.tobytes("png"), "png"

    def _pdf_to_content_blocks(self, raw_bytes, name):
        """Born-digital PDFs (exported from an ERP/Excel/Word - selectable
        text) are read as structured tables via PyMuPDF's find_tables(),
        which extracts cells by their actual grid position (row/column)
        rather than the PDF's internal reading order. Plain get_text("text")
        was tried first but silently scrambled row associations on wide
        multi-column tables - quantities ended up detached from the
        product row they belonged to, so the AI could only see 3 of 8
        ordered rows. Table-position extraction keeps every reference /
        description / quantity locked to its real row, the same guarantee
        the Excel path already has. Falls back to plain text extraction
        if no table is detected on a page, and to sending page images
        only if the file has no embedded text layer at all - i.e. an
        actual scan/photo.

        Scanned pages are returned as Claude image blocks
        ({"type": "image", "source": {"type": "base64", ...}}).
        """
        if pymupdf is None:
            raise UserError(_(
                "The 'pymupdf' Python library is required to read PDF file "
                "'%s'. Please ask your administrator to install it "
                "(pip install pymupdf) on the Odoo server.", name,
            ))

        try:
            doc = pymupdf.open(stream=raw_bytes, filetype="pdf")
        except Exception as exc:
            raise UserError(_(
                "Could not read PDF file '%(name)s': %(err)s", name=name, err=str(exc)
            )) from exc

        page_count = min(len(doc), MAX_PDF_PAGES)
        page_texts = [doc[i].get_text("text") for i in range(page_count)]
        has_text_layer = all(
            len(text.strip()) >= PDF_TEXT_MIN_CHARS_PER_PAGE for text in page_texts
        )

        if not has_text_layer:
            image_blocks = []
            for i in range(page_count):
                img_bytes, ext = self._pdf_page_image_bytes(doc[i])
                mime = f"image/{ext}" if ext else "image/png"
                b64 = base64.b64encode(img_bytes).decode()
                image_blocks.append({
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": mime,
                        "data": b64,
                    },
                })
            doc.close()
            return image_blocks

        row_texts = [self._pdf_page_to_row_text(doc[i]) for i in range(page_count)]
        doc.close()

        combined = "\n".join(
            f"--- Page {i + 1} ---\n{text}" for i, text in enumerate(row_texts)
        )
        return [{
            "type": "text",
            "text": (
                f"[PDF file '{name}' extracted content - each line is one "
                f"visual row on the page, reconstructed from exact word "
                f"positions; ' | ' marks a likely column boundary]"
                f"\n{combined}"
            ),
        }]

    def _attachment_to_content_blocks(self, attachment):
        mimetype = (attachment.mimetype or "").lower()
        name = attachment.name or "file"
        ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""

        raw = bytes(attachment.raw or b"")
        if not raw:
            raise UserError(_("The attachment '%s' is empty or could not be read.", name))

        if mimetype.startswith("image/") or ext in IMAGE_EXTENSIONS:
            b64 = self._prepare_image_b64(base64.b64encode(raw), mimetype or "image/jpeg")
            data_mime = mimetype if mimetype.startswith("image/") else "image/jpeg"
            return [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": data_mime,
                        "data": b64,
                    },
                }
            ]

        if mimetype == "application/pdf" or ext == "pdf":
            return self._pdf_to_content_blocks(raw, name)

        if ext in EXCEL_EXTENSIONS or "spreadsheet" in mimetype or mimetype == "application/vnd.ms-excel":
            table_text = self._excel_to_text(raw, name)
            return [{
                    "type": "text",
                    "text": f"[Excel file '{name}' content, tab-separated]\n{table_text}",
                }]

        if ext == "csv" or mimetype == "text/csv":
            table_text = self._csv_to_text(raw)
            return [{
                "type": "text",
                "text": f"[CSV file '{name}' content]\n{table_text}",
            }]

        if ext in MSG_EXTENSIONS or mimetype == "application/vnd.ms-outlook":
            msg_text = self._msg_to_text(raw, name)
            return [{
                "type": "text",
                "text": f"[Outlook message '{name}' content]\n{msg_text}",
            }]

        if ext in ODT_EXTENSIONS or mimetype == "application/vnd.oasis.opendocument.text":
            odt_text = self._odt_to_text(raw, name)
            return [{
                "type": "text",
                "text": f"[OpenDocument file '{name}' content]\n{odt_text}",
            }]

        raise UserError(_(
            "Unsupported file type for '%(name)s' (%(mime)s). Supported "
            "types: images (jpg/png/...), PDF, Excel (xlsx/xls), CSV, "
            "Outlook (.msg) and OpenDocument Text (.odt).",
            name=name,
            mime=mimetype or ext or "unknown",
        ))

    # ------------------------------------------------------------------
    # Claude (Anthropic) call plumbing
    # ------------------------------------------------------------------
    def _call_openai(self, api_key, payload, use_mcp=False):
        """POST `payload` to the Claude Messages API (with the MCP beta
        header when use_mcp is True) and return the parsed result.
        A 200 response is still rejected when stop_reason is "max_tokens"
        (truncated output) or "refusal" (the model declined)."""
        headers = {
            "x-api-key": api_key,
            "anthropic-version": ANTHROPIC_VERSION,
            "Content-Type": "application/json",
        }
        if use_mcp:
            headers["anthropic-beta"] = MCP_BETA_HEADER

        try:
            response = requests.post(
                ANTHROPIC_MESSAGES_URL,
                headers=headers,
                json=payload,
                timeout=600,
            )
        except requests.exceptions.RequestException as exc:
            raise UserError(_("Could not reach the Claude (Anthropic) API: %s", str(exc))) from exc

        try:
            result = response.json()
        except ValueError as exc:
            raise UserError(_(
                    "The Claude API returned an invalid response (HTTP %s).",
                    response.status_code,
                )) from exc

        if response.status_code != 200:
            err = None
            if isinstance(result, dict):
                err = (result.get("error") or {}).get("message")
            raise UserError(_(
                    "Claude API error (HTTP %(code)s): %(msg)s",
                    code=response.status_code,
                    msg=err or str(result),
                ))

        stop_reason = result.get("stop_reason")
        if stop_reason == "max_tokens":
            raise UserError(_(
                    "The AI response was cut off after reaching the "
                    "'Max Tokens' limit. Try again, perhaps with fewer or "
                    "smaller files, or raise 'Max Tokens' on the AI "
                    "Configuration record."
                ))
        if stop_reason == "refusal":
            raise UserError(_("The AI declined to process this request."))

        return result

    @staticmethod
    def _extract_usage(result):
        """Pull {input_tokens, output_tokens, total_tokens} out of a
        Claude Messages API result, defaulting every value to 0 so
        callers can always write it straight into the Integer fields
        without a crash.

        Cache token counts (normally 0) are folded into the input side."""
        usage = result.get("usage") or {}
        input_tokens = (
            (usage.get("input_tokens") or 0)
            + (usage.get("cache_creation_input_tokens") or 0)
            + (usage.get("cache_read_input_tokens") or 0)
        )
        output_tokens = usage.get("output_tokens") or 0
        return {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
        }

    @staticmethod
    def _safe_int(value):
        """Coerce an AI-returned id into an int, or None if it plainly
        isn't one (never raises) - so a stray string/dict from the model
        degrades to 'not resolved' instead of crashing the whole action
        with int(): invalid literal / int() argument errors."""
        if value is None or value is False:
            return None
        if isinstance(value, bool):
            return None
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return int(value)
        if isinstance(value, str):
            match = re.search(r"-?\d+", value)
            if match:
                return int(match.group(0))
            return None
        return None

    @staticmethod
    def _safe_float(value):
        try:
            return float(value)
        except (TypeError, ValueError):
            match = re.search(r"-?\d+(?:[.,]\d+)?", str(value))
            return float(match.group(0).replace(",", ".")) if match else 0.0

    @staticmethod
    def _tool_trace(result):
        content = result.get("content", []) or []
        results = {b.get("tool_use_id"): b for b in content if b.get("type") == "mcp_tool_result"}
        lines = [f"stop_reason: {result.get('stop_reason')}"]
        for b in content:
            if b.get("type") != "mcp_tool_use":
                continue
            r = results.get(b.get("id")) or {}
            raw = r.get("content")
            if isinstance(raw, list):
                raw = " ".join(p.get("text", "") for p in raw if isinstance(p, dict))
            lines.append(
                f"CALL {b.get('name')} {json.dumps(b.get('input'), ensure_ascii=False)}\n"
                f"  -> is_error={r.get('is_error')} {str(raw)}"
            )
        if len(lines) == 1:
            lines.append("(no MCP tool calls were made)")
        return "\n".join(lines)

    def _call_with_continuation(self, api_key, payload, use_mcp=True, max_rounds=8):
        """Keeps calling while the API says the turn is unfinished (pause_turn)."""
        messages = list(payload["messages"])
        all_content, in_tok, out_tok = [], 0, 0
        for _round in range(max_rounds):
            result = self._call_openai(api_key, dict(payload, messages=messages), use_mcp=use_mcp)
            all_content += result.get("content", []) or []
            usage = result.get("usage") or {}
            in_tok += usage.get("input_tokens") or 0
            out_tok += usage.get("output_tokens") or 0
            if result.get("stop_reason") != "pause_turn":
                break
            messages.append({"role": "assistant", "content": result["content"]})
        result["content"] = all_content
        result["usage"] = {"input_tokens": in_tok, "output_tokens": out_tok}
        return result

    @staticmethod
    def _parse_json_text(text):
        """Try to turn ONE piece of text into a JSON object. Returns the
        parsed object, or None if this text is not a JSON document."""
        text = (text or "").strip()
        if not text:
            return None

        fence_match = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
        if fence_match:
            text = fence_match.group(1).strip()

        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                return parsed
        except (ValueError, TypeError):
            pass

        start = text.find("{")
        if start == -1:
            return None
        try:
            obj, _end = json.JSONDecoder().raw_decode(text, start)
            return obj if isinstance(obj, dict) else None
        except (ValueError, TypeError):
            return None

    @classmethod
    def _parse_structured_output(cls, result):
        """The final JSON is always in the LAST text block, so try the text
        blocks from last to first, and only as a final fallback all of
        them joined together."""
        texts = []
        for block in result.get("content", []) or []:
            if block.get("type") == "text" and block.get("text"):
                texts.append(block["text"])

        if not texts:
            raise UserError(_("The AI did not return any structured result. Please try again."))

        candidates = list(reversed(texts))
        if len(texts) > 1:
            candidates.append("\n".join(texts))

        for candidate in candidates:
            parsed = cls._parse_json_text(candidate)
            if parsed is not None:
                return parsed

        raise UserError(_(
            "The AI response could not be parsed as JSON: %s", texts[-1],
        ))

    @staticmethod
    def _extract_created_order_id(result):
        """Only trust an order id that we can verify came from an actual
        write/create MCP tool call against sale.order in this response.
        Never trust the model's self-reported sale_order_id alone.

        FIX: the Odoo MCP create_record tool answers in plain text
        ("Successfully created sale.order record with ID 116"), not
        JSON, so that pattern is now recognised as well.
        """
        content = result.get("content", []) or []
        results_by_id = {
            block.get("tool_use_id"): block
            for block in content
            if block.get("type") == "mcp_tool_result"
        }

        for block in content:
            if block.get("type") != "mcp_tool_use":
                continue
            name = (block.get("name") or "").lower()
            if not any(k in name for k in ("create", "write")):
                continue

            arguments = block.get("input") or {}
            model_name = (arguments.get("model") or arguments.get("res_model") or "").lower()
            if model_name and model_name != "sale.order":
                continue

            tool_result = results_by_id.get(block.get("id"))
            if not tool_result or tool_result.get("is_error"):
                continue

            raw_content = tool_result.get("content")
            if isinstance(raw_content, str):
                output_text = raw_content
            else:
                output_text = "\n".join(
                    part.get("text", "")
                    for part in (raw_content or [])
                    if isinstance(part, dict) and part.get("type") == "text"
                )
            if not output_text:
                continue

            try:
                parsed = json.loads(output_text)
            except (ValueError, TypeError):
                match = re.search(r"record with ID\s+(\d+)", output_text, re.IGNORECASE)
                if match:
                    return int(match.group(1))
                match = re.search(r'"id"\s*:\s*(\d+)', output_text)
                if match:
                    return int(match.group(1))
                continue
            if isinstance(parsed, dict):
                record = parsed.get("record") or (
                        parsed.get("structuredContent") or {}
                ).get("record")
                if isinstance(record, dict) and record.get("id"):
                    return int(record["id"])
                if parsed.get("id"):
                    return int(parsed["id"])
        return None

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------
    def action_reset_instructions(self):
        """Reload both prompts from the common AI Prompt record and add the
        selected customer's instruction."""
        prompt_model = self.env["ai.prompt"]
        for draft in self:
            draft.extraction_instructions = self._apply_customer_instruction(
                prompt_model.get_prompt_text("extraction_instructions"),
                draft.partner_id,
            )
            draft.creation_instructions = self._apply_customer_instruction(
                prompt_model.get_prompt_text("creation_instructions"),
                draft.partner_id,
            )

        return True

    def action_analyze(self):
        self.ensure_one()
        if self.state == "done":
            raise UserError(_("This draft already has a confirmed sale order (%s).",self.sale_order_id.display_name,))

        if not self.attachment_ids:
            raise UserError(_("Please upload at least one image, PDF or Excel/CSV file first."))

        claude_key, model, max_tokens, mcp_key, base_url = self._get_settings()
        if not self.extraction_instructions:
            raise UserError(_(
                "The 'Document Extraction Prompt' field is empty. Please "
                "set it before analyzing."
            ))

        content_blocks = [
            {
                "type": "text",
                 "text": "%s\n\nODOO COMPANY:\n%s" % (
                    self.extraction_instructions,
                    self.env.company.name,
                ),
            }
        ]
        for attachment in self.attachment_ids:
            content_blocks += self._attachment_to_content_blocks(attachment)

        payload = {
            "model": model,
            "max_tokens": max_tokens,
            "temperature": 1,
            "messages": [{"role": "user", "content": content_blocks}],
        }

        try:
            result = self._call_openai(claude_key, payload)
            data = self._parse_structured_output(result)

            raw_json = json.dumps(data, indent=2, ensure_ascii=False)

            lines_vals = []
            for index, line in enumerate(data.get("order_lines", []), start=1):
                lines_vals.append(
                    (0, 0, {
                        "line_number": self._safe_int(line.get("line_number")) or index,
                        "source_reference": _safe_text(line.get("source_reference"), 200),
                        "source_description": _safe_text(line.get("source_description"), 500),
                        "source_quantity": self._safe_float(line.get("quantity_raw")),
                        "quantity": self._safe_float(line.get("quantity")),
                        "source_uom": _safe_text(line.get("source_uom"), 100),
                        "document_unit_price": self._safe_float(line.get("document_unit_price")),
                    })
                )

            ignored_vals = []
            for ignored in data.get("ignored_lines", []):
                ignored_vals.append(
                    (0, 0, {
                        "source_reference": _safe_text(ignored.get("source_reference"), 200),
                        "source_description": _safe_text(ignored.get("source_description"), 500),
                        "quantity_raw": _safe_text(ignored.get("quantity_raw"), 200),
                    })
                )

            customer = data.get("customer") or {}

            usage = self._extract_usage(result)

            self.line_ids.unlink()
            self.ignored_line_ids.unlink()
            self.write(
                {
                    "line_ids": lines_vals,
                    "ignored_line_ids": ignored_vals,
                    "detected_customer_name": customer.get("source_name") or "",
                    "ai_customer_match_status": False,
                    "ai_create_response": False,
                    "ai_raw_response": raw_json,
                    "state": "analyzed",
                    "error_message": False,
                    "llm_model_used": model,
                    "extraction_input_tokens": usage["input_tokens"],
                    "extraction_output_tokens": usage["output_tokens"],
                    "extraction_total_tokens": usage["total_tokens"],
                    "extraction_status": data.get("status"),
                    "creation_status": False,
                }
            )
        except UserError as exc:
            self.write({"state": "error", "error_message": str(exc)})
            raise

        if self.auto_create_sale_order and self.state == "analyzed":
            if not (data.get("order_lines") or []):
                self.message_post(
                    body=_("Auto-create is enabled but no order lines were extracted, so nothing was sent to Odoo."))
            else:
                try:
                    self.action_create_sale_order()
                except UserError as exc:
                    self.write({"error_message": str(exc)})

        return True

    def _mark_lines_added(self, data, order):
        """Colour-status for each extracted line, based on what REALLY exists
        on the created sale order (checked via ORM), not on the AI's claim."""
        added_product_ids = set(order.order_line.mapped("product_id").ids)

        # Queue of not-yet-claimed sale.order.line records per product, so
        # that when the same product appears on several lines each draft
        # line still gets linked to its own distinct sale.order.line.
        so_lines_by_product = {}
        for so_line in order.order_line:
            so_lines_by_product.setdefault(so_line.product_id.id, []).append(so_line)

        product_by_line = {}
        for m in data.get("matched_products") or []:
            ln = self._safe_int(m.get("line_number"))
            if ln:
                product_by_line[ln] = self._safe_int(m.get("odoo_product_id"))

        for line in self.line_ids:
            pid = product_by_line.get(line.line_number)
            if pid and pid in added_product_ids:
                queue = so_lines_by_product.get(pid) or []
                so_line = queue.pop(0) if queue else False
                line.write({
                    "sale_order_status": "added",
                    "odoo_product_id": pid,
                    "sale_order_line_id": so_line.id if so_line else False,
                })
            else:
                line.write({
                    "sale_order_status": "not_added",
                    "odoo_product_id": False,
                    "sale_order_line_id": False,
                })

    def action_create_sale_order(self):
        self.ensure_one()
        if self.state == "done":
            raise UserError(
                _(
                    "A sale order has already been created for this draft: %s",
                    self.sale_order_id.display_name,
                )
            )
        if self.state not in ("analyzed", "error"):
            raise UserError(_("Please run 'Analyze' first."))
        if not self.ai_raw_response:
            raise UserError(_("No extracted JSON found for this draft. Please run 'Analyze with AI' first."))

        extraction = json.loads(self.ai_raw_response)

        if not extraction.get("order_lines"):
            raise UserError(_("The extracted JSON has no order lines to create a sale order from."))

        claude_key, model, max_tokens, mcp_key, base_url = self._get_settings()

        if self.use_selected_partner:
            partner_id_hint = self.partner_id.id
            partner_name_hint = self.partner_id.display_name
        else:
            partner_id_hint = None if self.detected_customer_name else self.partner_id.id
            partner_name_hint = self.detected_customer_name if self.detected_customer_name else self.partner_id.display_name

        product_mappings = self.env["ai.product.mapping"].sudo().search([])
        known_product_mappings_csv = self._build_mapping_csv(product_mappings)

        user_payload = {
            "partner_id_hint": partner_id_hint,
            "partner_name_hint": partner_name_hint,
            "known_product_mappings": known_product_mappings_csv,
            "extraction": extraction,
            "instruction": (
                "Execute the creation now: call create_record for the sale.order "
                "header, then one create_record per sale.order.line, then one "
                "read-back. Do not produce the final JSON before those tool calls "
                "are done."
            ),
        }
        if not self.creation_instructions:
            raise UserError(
                _("The 'Sale Order Creation Prompt' field is empty. Please set it before creating a sale order."))

        system_prompt = self.creation_instructions
        if product_mappings:
            if PRODUCT_MAPPING_RULE_ANCHOR in system_prompt:
                system_prompt = system_prompt.replace(
                    PRODUCT_MAPPING_RULE_ANCHOR,
                    PRODUCT_MAPPING_RULE_INSERT + PRODUCT_MAPPING_RULE_ANCHOR,
                    1,
                )
            else:
                system_prompt = "%s\n\n%s" % (
                    system_prompt.rstrip(),
                    PRODUCT_MAPPING_INSTRUCTIONS.strip(),
                )
        server_def, toolset_def = self._mcp_tool_def(mcp_key, base_url)
        payload = {
            "model": model,
            "max_tokens": max_tokens,
            "system": system_prompt,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(user_payload),
                        }
                    ],
                }
            ],
            "mcp_servers": [server_def],
            "tools": [toolset_def],
            "temperature": 0,
        }

        try:
            result = self._call_with_continuation(claude_key, payload, use_mcp=True)
        except UserError as exc:
            self.write(
                {
                    "ai_create_response": "(Claude API call failed before returning a response)\n%s" % str(exc),
                    "state": "error",
                    "error_message": str(exc),
                }
            )
            self.env.cr.commit()
            raise

        usage = self._extract_usage(result)
        usage_vals = {
            "creation_input_tokens": usage["input_tokens"],
            "creation_output_tokens": usage["output_tokens"],
            "creation_total_tokens": usage["total_tokens"],
        }

        try:
            data = self._parse_structured_output(result)
            trace = self._tool_trace(result)
            self.write({"ai_create_response": trace})
        except UserError as exc:
            raw_text = json.dumps(result, indent=2, ensure_ascii=False)
            self.write(
                {
                    "ai_create_response": "%s\n\n(Could not parse AI output as JSON)\n%s" % (trace, raw_text),
                    "state": "error",
                    "error_message": str(exc),
                    **usage_vals,
                }
            )
            return True

        try:
            customer_match = data.get("customer_match") or {}
            match_status = ("matched" if customer_match.get("found") is True
                            else "not_found" if customer_match.get("found") is False else False)

            self.write(
                {
                    "ai_create_response": json.dumps(data, indent=2, ensure_ascii=False),
                    "ai_customer_match_status": match_status,
                    "creation_status": data.get("status"),
                    **usage_vals,
                }
            )
            sale_order_data = data.get("sale_order") or {}
            order_id = sale_order_data.get("sale_order_id") or data.get("sale_order_id")
            verified_id = self._extract_created_order_id(result)
            if verified_id:
                order_id = verified_id

            if not order_id:
                status = data.get("status")
                failure_reason = _safe_text(data.get("failure_reason"))
                if status == "customer_not_found":
                    message = _("Customer '%s' was not found in Odoo, so no sale order was created.",(data.get("customer_match") or {}).get("source_name") or self.partner_id.display_name,)
                elif status == "no_products_matched":
                    message = _("The customer was found, but none of the ordered products matched an Odoo product, so no sale order was created.")
                elif failure_reason:
                    message = _("No sale order was created: %s",failure_reason,)
                else:
                    message = _("The AI did not confirm that a sale order was created.")

                extra_vals = {}
                if status == "created":
                    extra_vals["creation_status"] = "creation_failed"
                self.write({"state": "error", "error_message": message, **extra_vals, **usage_vals})
                return True

            safe_order_id = self._safe_int(order_id)
            if safe_order_id is None:
                message = _("The AI reported sale order ID '%s', which is not a usable numeric id. Please check manually before retrying.",order_id,)
                self.write({"state": "error", "error_message": message, **usage_vals})
                return True
            self.env.cr.commit()

            order = self.env["sale.order"].sudo().browse(safe_order_id)
            if not order.exists():
                message = _("The AI reported sale order ID %s but it could not be found in Odoo. Please check manually before retrying.",safe_order_id,)
                self.write({"state": "error", "error_message": message, **usage_vals})
                return True

            self._mark_lines_added(data, order)
            matched_products = data.get("matched_products") or []
            expected_line_count = len(matched_products)
            actual_line_count = len(order.order_line)
            expected_partner_id = self._safe_int(customer_match.get("odoo_partner_id"))

            mismatch_notes = []
            if expected_partner_id and order.partner_id.id != expected_partner_id:
                mismatch_notes.append(_("AI reported customer id %(expected)s but the created sale order's actual customer is %(actual)s (%(name)s).",expected=expected_partner_id,
                        actual=order.partner_id.id,name=order.partner_id.display_name,))
            if expected_line_count and actual_line_count == 0:
                mismatch_notes.append(_("AI reported %s matched product(s) but the created sale order has no order lines - it was likely created empty.",expected_line_count,))
            elif expected_line_count and actual_line_count < expected_line_count:
                mismatch_notes.append(_("AI reported %(expected)s matched product(s) but the created sale order only has %(actual)s order line(s).",expected=expected_line_count,actual=actual_line_count,))

            requested_word_sets = [
                _normalize_words(line.get("source_description"))
                for line in (extraction.get("order_lines") or [])
                if line.get("source_description")
            ]
            requested_word_sets = [w for w in requested_word_sets if w]
            if requested_word_sets:
                unrelated_lines = []
                for order_line in order.order_line:
                    product_words = _normalize_words(order_line.product_id.display_name)
                    if not product_words:
                        continue
                    if not any(product_words & req for req in requested_word_sets):
                        unrelated_lines.append(order_line.product_id.display_name)
                if unrelated_lines:
                    mismatch_notes.append(_("The created sale order contains product(s) that share no wording with anything in the source document, which usually means no real match was found and a generic/placeholder product was used "
                            "instead: %s.",
                            ", ".join(sorted(set(unrelated_lines))),
                        )
                    )

            if mismatch_notes:
                message = _("Sale order %s was created, but it does not match what the AI reported - please review it manually before sending it to the customer:\n%s",order.display_name,"\n".join(mismatch_notes),)
                self.write({"sale_order_id": order.id,"state": "error","error_message": message,**usage_vals,})
                return True

            self.write({"sale_order_id": order.id,"state": "done","error_message": False,**usage_vals,})
        except Exception as exc:
            self.write(
                {
                    "ai_create_response": json.dumps(data, indent=2, ensure_ascii=False)
                    if isinstance(data, dict) else str(exc),
                    "state": "error",
                    "error_message": str(exc),
                    **usage_vals,
                }
            )
            return True

        return {
            "type": "ir.actions.act_window",
            "res_model": "sale.order",
            "res_id": self.sale_order_id.id,
            "view_mode": "form",
            "target": "current",
        }

    def action_update_sale_order(self):
        """Apply the product mappings set on the 'Extracted Lines' tab to
        the already-created sale order.

        For every extracted line that has an Odoo Product set:
        - if it is already linked to a sale.order.line (sale_order_line_id),
          that exact line is updated in place (product/quantity) instead of
          creating a duplicate;
        - otherwise a new sale.order.line is created on the sale order and
          linked back to the extracted line.

        The quantity applied is the editable 'Quantity' of the extracted
        line (not the read-only 'Source Quantity').

        Every mapped product/description pair is also saved (or refreshed)
        in ai.product.mapping, so future documents reuse the same match.
        """
        self.ensure_one()
        if not self.sale_order_id:
            raise UserError(_(
                "There is no sale order linked to this draft yet. Please "
                "run 'Create Sale Order' first."
            ))

        order = self.sale_order_id
        mapping_model = self.env["ai.product.mapping"].sudo()
        updated_count = 0
        created_count = 0

        for line in self.line_ids:
            if not line.odoo_product_id:
                continue

            quantity = line.quantity or 0.0
            so_line = line.sale_order_line_id
            if so_line and so_line.order_id == order:
                if (so_line.product_id.id != line.odoo_product_id.id
                        or so_line.product_uom_qty != quantity):
                    so_line.write({
                        "product_id": line.odoo_product_id.id,
                        "product_uom_qty": quantity,
                    })
                    updated_count += 1
            else:
                create_vals = {
                    "order_id": order.id,
                    "product_id": line.odoo_product_id.id,
                    "product_uom_qty": quantity,
                }
                if line.document_unit_price:
                    create_vals["price_unit"] = line.document_unit_price
                so_line = self.env["sale.order.line"].create(create_vals)
                line.sale_order_line_id = so_line.id
                created_count += 1

            line.sale_order_status = "added"

            if line.source_description:
                mapping_model.upsert_mapping(
                    line.source_description, line.odoo_product_id
                )

        if not updated_count and not created_count:
            raise UserError(_(
                "No mapped products found to update. Please set an Odoo "
                "Product on at least one line in the 'Extracted Lines' "
                "tab first."
            ))

        self.message_post(body=_(
            "Sale order updated from mapped extracted lines: %(updated)s "
            "line(s) updated, %(created)s line(s) added.",
            updated=updated_count, created=created_count,
        ))

        return {
            "type": "ir.actions.act_window",
            "res_model": "sale.order",
            "res_id": order.id,
            "view_mode": "form",
            "target": "current",
        }

    def action_view_sale_order(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "res_model": "sale.order",
            "res_id": self.sale_order_id.id,
            "view_mode": "form",
            "target": "current",
        }
