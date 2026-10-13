# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from .order_automation import (
    DEFAULT_CREATION_INSTRUCTIONS,
    DEFAULT_EXTRACTION_INSTRUCTIONS,
)


class AiPrompt(models.Model):
    """Common (company-wide) prompts used by the Sale Order Automation.

    There is exactly ONE record of this model. Every new 'order.automation'
    record fetches its two prompts from here and keeps its own editable copy,
    so editing a prompt on a single order never changes this common record.
    """
    _name = "ai.prompt"
    _description = "AI Prompt"

    name = fields.Char(
        string="Name",
        required=True,
        default=lambda self: _("AI Prompt"),
    )
    extraction_instructions = fields.Text(
        string="Document Extraction Prompt",
        default=lambda self: DEFAULT_EXTRACTION_INSTRUCTIONS,
        help="Instructions sent to the AI when 'Analyze with AI' runs. "
             "Every new Sale Order Automation record starts with a copy of "
             "this text.",
    )
    creation_instructions = fields.Text(
        string="Sale Order Creation Prompt",
        default=lambda self: DEFAULT_CREATION_INSTRUCTIONS,
        help="Instructions sent to the AI when 'Create Sale Order' runs. "
             "Every new Sale Order Automation record starts with a copy of "
             "this text.",
    )

    # ------------------------------------------------------------------
    # Constraints
    # ------------------------------------------------------------------
    @api.constrains("name")
    def _check_single_record(self):
        if self.sudo().search_count([]) > 1:
            raise ValidationError(_(
                "Only one AI Prompt record is allowed. It is shared by all "
                "Sale Order Automation records - please edit the existing one."
            ))

    # ------------------------------------------------------------------
    # Helpers used by order.automation
    # ------------------------------------------------------------------
    @api.model
    def get_prompt_text(self, field_name):
        """Return the common prompt stored in the `field_name` field
        ('extraction_instructions' or 'creation_instructions').

        Read-only on purpose (never creates a record) so it is safe to call
        from field defaults. Falls back to the built-in default text when
        no record exists yet or the stored text is empty.
        """
        fallback = {
            "extraction_instructions": DEFAULT_EXTRACTION_INSTRUCTIONS,
            "creation_instructions": DEFAULT_CREATION_INSTRUCTIONS,
        }[field_name]
        prompt = self.sudo().search([], order="id", limit=1)
        return (prompt[field_name] if prompt else False) or fallback

    @api.model
    def _init_default_prompt(self):
        """Create the single common record if it does not exist yet.
        Called from data/ai_prompt_data.xml on install/upgrade; harmless
        to call repeatedly."""
        if not self.sudo().search_count([]):
            self.sudo().create({})
        return True

    @api.model
    def action_open_prompt(self):
        """Open the single common prompt record directly in form view."""
        self._init_default_prompt()
        prompt = self.sudo().search([], order="id", limit=1)
        return {
            "type": "ir.actions.act_window",
            "name": _("AI Prompt"),
            "res_model": "ai.prompt",
            "res_id": prompt.id,
            "view_mode": "form",
            "views": [(False, "form")],
            "target": "current",
        }

    def action_restore_defaults(self):
        """Put back the built-in prompts shipped with the module."""
        for prompt in self:
            prompt.write({
                "extraction_instructions": DEFAULT_EXTRACTION_INSTRUCTIONS,
                "creation_instructions": DEFAULT_CREATION_INSTRUCTIONS,
            })
        return True
