from odoo import http
from odoo.http import request
from odoo import api, fields, models, _
from werkzeug.utils import redirect
import logging
from odoo.http import request

_logger = logging.getLogger(__name__)


class HubstaffOAuthController(http.Controller):

    @http.route('/callback', type='http', auth='public', csrf=False, methods=['GET'])
    def hubstaff_callback(self, **params):
        auth_code = params.get('code')
        state = params.get('state')

        rec = request.env['hubstaff.instance.integration'].sudo().search(
            [('id', '=', int(state))], limit=1
        )

        context = dict(request.env.context or {})
        context.update({'process_name': 'token'})
        rec = rec.with_context(context)

        # CREATE ONE MAIN LOG
        main_log_id = rec._create_log(
            log_type='import',
            force_new_log=True
        )
        rec = rec.with_context(import_log_id=main_log_id)

        if not auth_code:
            rec._create_log("Authorization code not received in callback.", 'import')
            return redirect('/web')

        rec.write({
            'auth_code': auth_code,
            'state': 'confirm'
        })

        rec._create_log(f"Authorization code stored: {auth_code}", 'import')

        #  Token exchange
        self._exchange_hubstaff_token(rec, auth_code)

        # Fetch organization
        if rec.access_token:
            self._fetch_hubstaff_org(rec)
        return redirect(
            f"/web#id={rec.id}&model=hubstaff.instance.integration&view_type=form"
        )

    def _exchange_hubstaff_token(self, rec, auth_code):
        """Exchange authorization code for Hubstaff access & refresh token"""

        if not rec or not auth_code:
            rec._create_log(
                "Missing instance or authorization code.",
                'import'
            )
            return False

        try:
            data, response = rec._hubstaff_api_call(
                method="POST",
                full_url=rec.account_token_url,
                payload={
                    "grant_type": "authorization_code",
                    "client_id": rec.client_id,
                    "client_secret": rec.client_secret,
                    "redirect_uri": rec.redirect_url,
                    "code": auth_code,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                is_form=True
            )

        except Exception as exc:
            rec._create_log(
                f"Token exchange failed: {str(exc)}",
                'import',
                api_response=str(exc)
            )
            return False

        try:
            data = response.json()
        except Exception:
            rec._create_log(f"Invalid JSON response from token API: {response.text}",'import')
            return False

        access_token = data.get("access_token")
        if not access_token:
            rec._create_log(f"Access token not found in response: {data}",'import')
            return False

        vals = {
            "access_token": access_token,
            "token_generated_at": fields.Datetime.now(),
        }

        if data.get("refresh_token"):
            vals["refresh_token"] = data.get("refresh_token")

        rec.write(vals)

        rec._create_log(
            "Hubstaff access token generated successfully.",
            'import'
        )
        return True

    def _fetch_hubstaff_org(self, rec):
        """Fetch and set Hubstaff organization"""
        try:
            data, response = rec._hubstaff_api_call(
                method="GET",
                endpoint="/v2/organizations"
            )

        except Exception as e:
            rec._create_log(
                f"Organization API exception: {str(e)}",
                'import',
                api_response=str(e)
            )
            return False

        orgs = data.get('organizations')

        if not orgs:
            rec._create_log("No organization found.", 'import')
            return False

        org_id = orgs[0]['id']
        rec.hubstaff_organization_id = org_id

        rec._create_log(
            f"Organization set successfully: {org_id}",
            'import'
        )

        return True

    @http.route('/webhook', type='http', auth='public', csrf=False, methods=['POST'])
    def webhook(self, **kwargs):
        instance = None
        event = None

        try:
            # --------------------------------------------------
            # WEBHOOK VERIFICATION (Hubstaff handshake)
            # --------------------------------------------------
            secret = request.httprequest.headers.get('X-Hook-Secret')
            if secret and not request.httprequest.data:
                _logger.info("Hubstaff webhook verification request received.")
                return request.make_response(
                    "OK",
                    headers={"X-Hook-Secret": secret},
                    status=200
                )

            # --------------------------------------------------
            # READ PAYLOAD
            # --------------------------------------------------
            payload = request.httprequest.get_json(silent=True) or {}

            _logger.info("============== HUBSTAFF WEBHOOK RECEIVED ==============")
            _logger.info("Webhook payload: %s", payload)

            event = payload.get('event')
            if not event:
                _logger.warning("Webhook received without event.")
                return request.make_response("No event provided", status=200)

            selection = dict(
                request.env['hubstaff.webhook'].fields_get(
                    ['webhook_event']
                )['webhook_event']['selection']
            )
            event_label = selection.get(event, event)

            # --------------------------------------------------
            # GET INSTANCE
            # --------------------------------------------------
            instance = request.env['hubstaff.instance.integration'].sudo().search([], limit=1)
            if not instance:
                _logger.error("No Hubstaff instance configured.")
                return request.make_response("No instance found", status=200)

            # --------------------------------------------------
            # CONTEXT PREPARATION
            # --------------------------------------------------
            process_name = event.split('.')[0]

            instance = instance.with_context(
                process_name=process_name
            )

            # --------------------------------------------------
            # CREATE MAIN LOG
            # --------------------------------------------------
            main_log_id = instance._create_log(
                log_type='import',
                force_new_log=True
            )

            instance = instance.with_context(
                import_log_id=main_log_id,
                process_name=process_name
            )

            # --------------------------------------------------
            # PROCESS EVENT
            # --------------------------------------------------
            payload_data = payload.get('payload') or {}

            if event == "project.create":
                data = payload_data.get('project') or payload_data
                instance.with_context(from_webhook=True)._import_project(data)

            elif event == "task.create":
                data = payload_data.get('task') or payload_data
                project = request.env['project.project'].sudo().search(
                    [('hubstaff_project_id', '=', str(data.get('project_id')))],
                    limit=1
                )

                if project:
                    instance.with_context(from_webhook=True)._import_tasks_for_project(
                        project,
                        hs_tasks=[data]
                    )
                else:
                    instance._create_log(
                        f"Webhook task skipped. Project not found for Hubstaff project ID {data.get('project_id')}",
                        'import'
                    )

            else:
                instance._create_log(
                    f"Unhandled webhook event received: {event_label}",
                    'import'
                )
                _logger.info("Unhandled webhook event ignored: %s", event_label)
                return request.make_response("Event ignored", status=200)

            # --------------------------------------------------
            # SUCCESS LOG
            # --------------------------------------------------
            instance._create_log(
                f"Webhook processed successfully for event: {event_label}",
                'import'
            )
            _logger.info("Webhook processed successfully for event: %s", event_label)

        except Exception as e:
            _logger.exception("Webhook processing failed")
            if instance:
                instance._create_log(
                    f"Webhook processing failed: {str(e)}",
                    'import'
                )
        return request.make_response("Received", status=200)