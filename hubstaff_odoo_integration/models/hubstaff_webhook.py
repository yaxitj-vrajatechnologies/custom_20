from odoo import models, fields, api
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class HubstaffWebhook(models.Model):
    _name = 'hubstaff.webhook'
    _description = 'Hubstaff Webhook'

    name = fields.Char(string="Webhook Name")
    webhook_event = fields.Selection([
        ('project.create', 'Create Project'),
        ('task.create', 'Create Task'),
    ], string="Event Type", help="Event type in Hubstaff that will trigger this webhook.")

    status = fields.Selection([
        ('active', 'Active'),
        ('disabled', 'Disabled'),
    ], string="Status", default='disabled', index=True,
        help="Status of the webhook. Active means the webhook is enabled, Disabled means it is not currently in use.")

    hubstaff_instance_id = fields.Many2one(
        'hubstaff.instance.integration', string="Hubstaff Instance", copy=False,
        help="Hubstaff instance to which this webhook configuration belongs."
    )
    hubstaff_webhook_id = fields.Char(string="Hubstaff Webhook ID", index=True, copy=False,
                                      help="Unique identifier of the webhook created in Hubstaff.")

    state = fields.Selection(related='hubstaff_instance_id.state',
                             help="Current state of the related Hubstaff instance.")

    def action_create_hubstaff_webhook(self):
        for rec in self:
            instance = rec.hubstaff_instance_id

            if not instance.api_url or not instance.hubstaff_organization_id or not instance.access_token:
                raise UserError(
                    "Hubstaff Instance configuration missing required values."
                )

            # --------------------------------------------------
            # Identify process name from webhook event
            # project.create -> project
            # task.create -> task
            # --------------------------------------------------
            process_name = rec.webhook_event.split('.')[0]

            # Get selection LABEL instead of key
            event_label = dict(
                self._fields['webhook_event'].selection
            ).get(rec.webhook_event)

            instance = instance.with_context(process_name=process_name)

            # --------------------------------------------------
            # Create ONE main log
            # --------------------------------------------------
            main_log_id = instance._create_log(
                log_type='export',
                force_new_log=True
            )

            # IMPORTANT → pass parent log to all next calls
            instance = instance.with_context(export_log_id=main_log_id)

            # --------------------------------------------------
            # Prepare payload
            # --------------------------------------------------
            base_url = self.env['ir.config_parameter'].sudo().get_str('web.base.url')

            payload = {
                "events": [rec.webhook_event],
                "target_url": f"{base_url}/webhook"
            }

            # --------------------------------------------------
            # Create webhook via Hubstaff API
            # --------------------------------------------------
            try:
                data, response = instance._hubstaff_api_call(
                    method="POST",
                    endpoint=f"/v2/organizations/{instance.hubstaff_organization_id}/webhooks",
                    payload=payload,
                )

                rec.hubstaff_webhook_id = data.get('id')
                rec.status = 'active'

                instance._create_log(
                    message=f"Webhook created successfully: "
                            f"{event_label} (ID: {rec.hubstaff_webhook_id})",
                    log_type='export'
                )

            except Exception as e:
                instance._create_log(
                    message=f"Webhook creation failed for {event_label}: {str(e)}",
                    log_type='export',
                    api_request=payload,
                    api_response=str(e)
                )
                raise

            # --------------------------------------------------
            # Activate webhook
            # --------------------------------------------------
            try:
                instance._hubstaff_api_call(
                    method="POST",
                    endpoint=f"/v2/webhooks/{rec.hubstaff_webhook_id}/activate",
                )
            except Exception as e:
                instance._create_log(
                    message=f"Webhook activation failed for {event_label}: {str(e)}",
                    log_type='export',
                    api_request={
                        "webhook_id": rec.hubstaff_webhook_id,
                        "action": "activate"
                    },
                    api_response=str(e)
                )

            # --------------------------------------------------
            # Final notification
            # --------------------------------------------------
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": "Success",
                    "message": f"Webhook {event_label} activated successfully in Hubstaff!",
                    "sticky": False,
                }
            }

    def unlink(self):
        for rec in self:
            instance = rec.hubstaff_instance_id

            if not instance.api_url or not instance.access_token or not rec.hubstaff_webhook_id:
                raise UserError(
                    f"Hubstaff configuration missing for webhook record: {rec.name}"
                )

            process_name = rec.webhook_event.split('.')[0]

            event_label = dict(
                self._fields['webhook_event'].selection
            ).get(rec.webhook_event)

            instance = instance.with_context(process_name=process_name)

            main_log_id = instance._create_log(
                log_type='export',
                force_new_log=True
            )

            # Pass parent log once
            instance = instance.with_context(export_log_id=main_log_id)

            try:
                instance._hubstaff_api_call(
                    method="DELETE",
                    endpoint=f"/v2/webhooks/{rec.hubstaff_webhook_id}",
                )

                instance._create_log(
                    message=f"Webhook deleted successfully: "
                            f"{event_label} (ID: {rec.hubstaff_webhook_id})",
                    log_type='export'
                )

            except Exception as e:
                instance._create_log(
                    message=f"Webhook deletion failed for "
                            f"{event_label}: {str(e)}",
                    log_type='export',
                    api_request={
                        "webhook_id": rec.hubstaff_webhook_id
                    },
                    api_response=str(e)
                )
                raise
        return super(HubstaffWebhook, self).unlink()

