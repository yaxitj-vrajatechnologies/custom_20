# -*- coding: utf-8 -*-
import logging

from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

TAXONOMY_URL = "https://www.google.com/basepages/producttype/taxonomy-with-ids.en-US.txt"


class ImportGoogleCategoryWizard(models.TransientModel):
    _name = "import.google.category.wizard"
    _description = "Import / Update Google Product Categories"

    state = fields.Selection(
        [
            ("ready", "Ready"),
            ("done", "Done"),
        ],
        default="ready",
    )
    imported_count = fields.Integer(string="Imported", readonly=True)
    updated_count = fields.Integer(string="Updated", readonly=True)
    skipped_count = fields.Integer(string="Skipped (already up-to-date)", readonly=True)
    error_message = fields.Text(string="Error", readonly=True)
    info_message = fields.Text(string="Result", readonly=True)

    def action_import_categories(self):
        """Fetch the Google taxonomy file and upsert into google.product.taxonomy."""
        try:
            import requests  # noqa: PLC0415
        except ImportError as exc:
            raise UserError(
                _("Python library 'requests' is required. Install it with: pip install requests")
            ) from exc

        try:
            response = requests.get(TAXONOMY_URL, timeout=60)
            response.raise_for_status()
        except Exception as exc:
            raise UserError(_("Failed to download taxonomy file:\n%s") % exc) from exc

        Taxonomy = self.env["google.product.taxonomy"]
        path_cache = {}
        imported = updated = skipped = 0

        lines = response.text.splitlines()
        # Filter valid lines: numeric_id SP DASH SP full_path
        data_lines = [l for l in lines if " - " in l and l.split(" - ", 1)[0].strip().isdigit()]

        # ── Pass 1: create/update all records ─────────────────────────────────
        for line in data_lines:
            google_id_str, full_path = line.split(" - ", 1)
            google_id = int(google_id_str.strip())
            full_path = full_path.strip()
            parts = [p.strip() for p in full_path.split(" > ")]
            name = parts[-1]
            parent_path = " > ".join(parts[:-1])

            parent = path_cache.get(parent_path)
            if not parent and parent_path:
                parent = Taxonomy.search([("full_path", "=", parent_path)], limit=1)
                if parent:
                    path_cache[parent_path] = parent

            existing = Taxonomy.search([("google_id", "=", google_id)], limit=1)
            vals = {
                "google_id": google_id,
                "name": name,
                "full_path": full_path,
                "parent_id": parent.id if parent else False,
            }
            if existing:
                if existing.full_path != full_path or existing.name != name:
                    existing.write(vals)
                    updated += 1
                else:
                    skipped += 1
                path_cache[full_path] = existing
            else:
                record = Taxonomy.create(vals)
                path_cache[full_path] = record
                imported += 1

        info = _(
            "Import complete!\n"
            "✔ New categories imported: %d\n"
            "✔ Categories updated: %d\n"
            "— Already up-to-date: %d"
        ) % (imported, updated, skipped)

        self.write({
            "state": "done",
            "imported_count": imported,
            "updated_count": updated,
            "skipped_count": skipped,
            "info_message": info,
        })

        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }
