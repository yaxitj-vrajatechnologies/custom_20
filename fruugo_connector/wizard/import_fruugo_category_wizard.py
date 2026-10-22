# -*- coding: utf-8 -*-
import logging

from odoo import models, fields, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class ImportFruugoCategoryWizard(models.TransientModel):
    _name = 'import.fruugo.category.wizard'
    _description = 'Import / Update Fruugo Categories'

    state = fields.Selection(
        [
            ('ready', 'Ready'),
            ('done', 'Done'),
        ],
        default='ready',
    )
    imported_count = fields.Integer(string='Imported', readonly=True)
    skipped_count = fields.Integer(string='Skipped (already up-to-date)', readonly=True)
    info_message = fields.Text(string='Result', readonly=True)

    def action_import_categories(self):
        """Fetch the Google taxonomy or custom Fruugo taxonomy standard."""
        try:
            import requests  # noqa: PLC0415
        except ImportError as exc:
            raise UserError(
                _("Python library 'requests' is required. Install it with: pip install requests")
            ) from exc

        url = self.env['ir.config_parameter'].sudo().get_str(
            'fruugo.category.sync.url',
            'https://www.google.com/basepages/producttype/taxonomy-with-ids.en-US.txt'
        )

        try:
            response = requests.get(url, timeout=60)
            response.raise_for_status()
        except Exception as exc:
            raise UserError(_("Failed to download taxonomy file:\n%s") % exc)

        FruugoCategory = self.env['fruugo.category']
        imported = skipped = 0

        lines = response.text.splitlines()
        existing_records = FruugoCategory.search([])
        path_cache = {rec.full_path: rec for rec in existing_records}
        
        imported = updated = skipped = 0

        for line in lines:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            
            if ' - ' in line and line.split(' - ')[0].isdigit():
                full_path = line.split(' - ', 1)[1].strip()
            else:
                full_path = line
                
            if not full_path:
                continue

            parts = [p.strip() for p in full_path.split(" > ")]
            name = parts[-1]
            parent_path = " > ".join(parts[:-1])

            parent = path_cache.get(parent_path)
            if not parent and parent_path:
                parent = FruugoCategory.search([("full_path", "=", parent_path)], limit=1)
                if parent:
                    path_cache[parent_path] = parent

            existing = path_cache.get(full_path)
            vals = {
                "name": name,
                "full_path": full_path,
                "parent_id": parent.id if parent else False,
            }

            if existing:
                if existing.name != name or existing.parent_id.id != vals['parent_id']:
                    existing.write(vals)
                    updated += 1
                else:
                    skipped += 1
            else:
                record = FruugoCategory.create(vals)
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
