from odoo import models, fields, api, _
import logging
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class ResUsers(models.Model):
    _inherit = 'res.users'

    hubstaff_user_id = fields.Char("Hubstaff User ID", copy=False,
                                   help="Unique identifier of the user in Hubstaff. This value is automatically set when the user is synchronized with Hubstaff.")

    def action_sync_hubstaff_user(self):
        self.ensure_one()

        instance = self.env['hubstaff.instance.integration'].search(
            [('company_id', '=', self.company_id.id)],
            limit=1
        )

        if not instance:
            raise UserError(_("No Hubstaff instance found for this company."))

        # -------------------------------------------------
        # Prepare context
        # -------------------------------------------------
        context = dict(self.env.context or {})
        context.update({
            "process_name": "user",
            "import_operations": True,
        })

        instance = instance.with_context(context)
        main_log_id = instance._create_log(
            log_type="import",
            force_new_log=True
        )

        instance = instance.with_context(import_log_id=main_log_id)

        try:
            # -------------------------------------------------
            # Ensure access token
            # -------------------------------------------------
            if not instance.access_token or not instance._is_hubstaff_token_valid():
                instance.action_generate_access_token()

            # -------------------------------------------------
            # FETCH ORGANIZATION MEMBERS
            # -------------------------------------------------
            try:
                members = instance._hubstaff_paginated_fetch(
                    endpoint=f"/v2/organizations/{instance.hubstaff_organization_id}/members",
                    data_key="members"
                )
            except Exception as e:
                instance._create_log(
                    message=f"Failed to fetch organization members: {str(e)}",
                    log_type="import",
                    api_response=str(e)
                )
                raise

            if not members:
                raise Exception("No members found in Hubstaff organization")

            # -------------------------------------------------
            # MATCH USER BY EMAIL
            # -------------------------------------------------
            target_email = (self.email or "").lower()
            matched_user_id = None

            for member in members:
                uid = member.get("user_id")
                if not uid:
                    continue

                try:
                    user_data, response = instance._hubstaff_api_call(
                        method="GET",
                        endpoint=f"/v2/users/{uid}"
                    )
                except Exception as e:
                    instance._create_log(
                        message=f"User fetch failed for Hubstaff User ID {uid}: {str(e)}",
                        log_type="import",
                        api_response=str(e)
                    )
                    continue

                if not response or response.status_code != 200:
                    continue

                user = (user_data or {}).get("user")

                if user and user.get("email", "").lower() == target_email:
                    matched_user_id = str(user.get("id"))
                    break

            # -------------------------------------------------
            # NO MATCH FOUND
            # -------------------------------------------------
            if not matched_user_id:
                instance._create_log(
                    message=f"No Hubstaff user found matching email {self.email}",
                    log_type="import"
                )
                raise Exception(f"No Hubstaff user found matching email {self.email}")

            # -------------------------------------------------
            # UPDATE ODOO USER
            # -------------------------------------------------
            self.hubstaff_user_id = matched_user_id

            instance._create_log(
                message=f"User linked with Hubstaff ID {matched_user_id}",
                log_type="import"
            )

            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": _("Hubstaff Sync Completed"),
                    "message": _("User successfully linked with Hubstaff."),
                    "type": "success",
                    "sticky": False,
                },
            }

        except Exception as e:
            instance._create_log(
                message=str(e),
                log_type="import"
            )
            raise UserError(_("Hubstaff user sync failed: %s") % str(e))
