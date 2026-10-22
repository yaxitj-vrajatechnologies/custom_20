from odoo import api, fields, models, _
import requests, logging
import datetime, time, random
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)
from datetime import datetime, timedelta


class HubstaffInstanceIntegration(models.Model):
    _name = 'hubstaff.instance.integration'
    _description = 'Hubstaff Instance Integration Configuration'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _rec_name = 'name'

    company_id = fields.Many2one('res.company', required=True, tracking=True, copy=False,
                                 help="Company for which this Hubstaff instance is configured.")
    api_url = fields.Char(string="API URL", required=True, tracking=True, default="https://api.hubstaff.com",
                          help="Base URL used to connect with the Hubstaff API.")
    hubstaff_organization_id = fields.Char(string="Organization ID", tracking=True, copy=False,
                                           help="Unique identifier of the Hubstaff organization associated with this instance.")
    client_id = fields.Char(string="Client ID", required=True, tracking=True, copy=False,
                            help="Client ID provided by Hubstaff for OAuth authentication.")
    client_secret = fields.Char(string="Client Secret", required=True, tracking=True, copy=False,
                                help="Client Secret provided by Hubstaff for OAuth authentication.")
    access_token = fields.Char(string="Access Token", readonly=True, copy=False,
                               help="Access token generated after successful authentication with Hubstaff.")
    refresh_token = fields.Char(string="Refresh Token", tracking=True, copy=False,
                                help="Refresh token used to generate a new access token when the current one expires.")
    redirect_url = fields.Char(string="Redirect URL", tracking=True, copy=False,
                               help="Callback URL configured in Hubstaff where the user is redirected after authorization.")
    token_generated_at = fields.Datetime(readonly=True, copy=False,
                                         help="Date and time when the current access token was generated.")
    hubstaff_exported = fields.Boolean(default=False, copy=False, tracking=True,
                                       help="Indicates whether data has been exported to Hubstaff from this instance.")
    image = fields.Binary(string="Instance Logo", help="Logo representing this Hubstaff instance.")
    name = fields.Char(string="Name", tracking=True, copy=False, help="Display name of this Hubstaff instance.")
    account_token_url = fields.Char(
        string="Account Token URL",
        default="https://account.hubstaff.com/access_tokens",
        help="Hubstaff URL used to exchange the authorization code for access and refresh tokens."

    )

    is_export_project = fields.Boolean(string='Auto Export Project To Hubstaff', copy=False, default=False,
                                       help="If enabled, newly created or updated projects will be automatically exported to Hubstaff.")
    is_export_task = fields.Boolean(string='Auto Export Task To Hubstaff', copy=False, default=False,
                                    help="If enabled, newly created or updated tasks will be automatically exported to Hubstaff.")
    imported_project_count = fields.Integer(compute="_compute_counts", string="Imported Projects", tracking=True,
                                            copy=False,
                                            help="Total number of projects imported from Hubstaff for this instance.")
    imported_task_count = fields.Integer(compute="_compute_counts", string="Imported Tasks", tracking=True, copy=False,
                                         help="Total number of tasks imported from Hubstaff for this instance.")
    imported_user_count = fields.Integer(compute="_compute_counts", string="Imported Users", tracking=True, copy=False,
                                         help="Total number of users imported from Hubstaff for this instance.")
    last_project_synced_date = fields.Datetime(
        string="Last Project Synced Date",
        copy=False,
        tracking=True, help="Date and time when projects were last synchronized with Hubstaff."

    )
    auth_code = fields.Char(string='Authorization Code', copy=False,
                            help="Authorization code received from Hubstaff during the OAuth authentication process.")
    state = fields.Selection([
        ('draft', 'Draft'), ('confirm', 'Confirm')], default='draft',
        help="Status of the Hubstaff instance. Draft means not authenticated, Confirm means successfully connected.")

    is_update_project = fields.Boolean(default=False, copy=False, string="Update Project in Hubstaff", tracking=True,
                                       help="If enabled, changes made to projects in Odoo will be updated in Hubstaff.")
    is_update_task = fields.Boolean(default=False, copy=False, string="Update Task in Hubstaff", tracking=True,
                                    help="If enabled, changes made to tasks in Odoo will be updated in Hubstaff.")

    webhook_ids = fields.One2many(
        'hubstaff.webhook', 'hubstaff_instance_id',
        string="Webhooks", help="Webhooks configured for this Hubstaff instance to receive real-time updates."
    )
    task_entry_days = fields.Integer(
        string="Task Entry Fetch Days",
        default=1,
        help="Fetch task entries from last N days (used in Cron & Manual Import)"
    )
    failure_activity_user_id = fields.Many2one(
        'res.users',
        string="Failure Activity User",
        help="User who will receive activities when Hubstaff sync fails."
    )

    def _create_log(
            self,
            message=None,
            log_type=None,
            api_request=None,
            api_response=None,
            force_new_log=False,
    ):
        """
        Central logging method
        - Handles instance logs
        - Handles project-wise logs
        - Supports multi-line messages
        - IMPORT  → api_request = False
        - EXPORT  → api_request allowed
        """

        context = dict(self.env.context or {})
        process_name = context.get('process_name')

        if api_request is None:
            api_request = "N/A"
        if api_response is None:
            api_response = "N/A"

        if log_type == 'import':
            api_request = False
        elif log_type == 'export':
            api_request = api_request or {}

        # Determine correct log key
        log_key = f"{log_type}_log_id"

        log_id = None
        if not force_new_log:
            log_id = context.get(log_key)

        # Create main log only if not exists
        if log_id:
            log = self.env['hubstaff.log'].browse(log_id)
        else:
            log = self.env['hubstaff.log'].create({
                'process_type': log_type,
                'company_id': self.company_id.id,
                'instance_id': self.id,
                'process_name': process_name,
            })

            context[log_key] = log.id

        if not message:
            return log.id

        # Create log lines
        lines = message.split("\n") if isinstance(message, str) else [str(message)]

        for line in lines:
            self.env['hubstaff.log.line'].create({
                'log_id': log.id,
                'company_id': self.company_id.id,
                'message': line,
                'api_request': api_request,
                'api_response': api_response,
            })

        _logger.info(message)
        return log.id

    def _hubstaff_paginated_fetch(self, endpoint, data_key, params=None):
        """
        Generic pagination handler for Hubstaff APIs.

        :param endpoint: API endpoint
        :param data_key: key inside response (projects/tasks/time_entries)
        :param params: extra params
        :return: full list of records
        """

        all_records = []
        page_start_id = 0
        page_limit = 100
        params = params or {}

        while True:
            page_params = dict(params)
            page_params.update({
                "page_start_id": page_start_id,
                "page_limit": page_limit,
            })

            try:
                data, response = self._hubstaff_api_call(
                    endpoint=endpoint,
                    method="GET",
                    params=page_params
                )
            except Exception as e:
                _logger.exception(
                    "Hubstaff pagination failed for endpoint %s", endpoint
                )
                # self._create_log(
                #     message=f"Pagination failed for endpoint {endpoint}: {str(e)}",
                #     log_type='import'
                # )
                break

            # HTTP validation
            if response.status_code != 200:
                _logger.error(
                    "Hubstaff API error %s for %s: %s",
                    response.status_code,
                    endpoint,
                    response.text
                )
                self._create_log(
                    message=f"Hubstaff API error {response.status_code} for {endpoint}",
                    log_type='import',
                    api_response=response.text
                )
                break

            # API error validation
            if isinstance(data, dict) and data.get("error"):
                _logger.error(
                    "Hubstaff API returned error for %s: %s",
                    endpoint,
                    data.get("error")
                )
                break

            records = (data or {}).get(data_key, [])

            if not records:
                break

            all_records.extend(records)

            # Last page condition
            if len(records) < page_limit:
                break
            # next page start id
            page_start_id = records[-1].get("id") or (page_start_id + page_limit)

        return all_records

    def _hubstaff_api_call(self, method, endpoint=None, payload=None, params=None,
                           full_url=None, headers=None, is_form=False):
        """
        Common Hubstaff API handler
        Returns: (data, response)
        """

        # URL handling
        if full_url:
            url = full_url
        else:
            base_url = self.api_url.rstrip('/')
            endpoint = endpoint.lstrip('/')
            url = f"{base_url}/{endpoint}"

        # Default headers
        final_headers = {}

        if self.access_token:
            final_headers["Authorization"] = f"Bearer {self.access_token}"

        if headers:
            final_headers.update(headers)
        else:
            final_headers["Content-Type"] = "application/json"

        try:
            response = requests.request(
                method=method,
                url=url,
                headers=final_headers,
                json=None if is_form else payload,
                data=payload if is_form else None,
                params=params,
                timeout=30
            )
            if not (200 <= response.status_code < 300):
                raise UserError(
                    f"Hubstaff API Error ({response.status_code}): {response.text}"
                )
            return response.json() if response.text else {}, response

        except Exception as e:
            _logger.exception(
                "Hubstaff API call failed | %s %s | Error: %s",
                method,
                url,
                str(e)
            )
            raise

    @api.model
    def _cron_export_project_task(self):
        records = self.search([('state', '=', 'confirm')])
        base_context = dict(self.env.context) or {}
        base_context.update({"export_project_cron": True})

        for rec in records:

            processed_project_ids = []

            # -------------------------------------------------
            # PART 1 — EXPORT NEW PROJECTS (if enabled)
            # -------------------------------------------------
            if rec.is_export_project:

                context = dict(base_context)
                context.update({'process_name': 'project'})

                domain = [('create_date', '>=', rec.last_project_synced_date)] if rec.last_project_synced_date else []
                projects = self.env['project.project'].search(domain)

                if projects:
                    # One log for project export
                    log = self.env['hubstaff.log'].create({
                        'process_type': 'export',
                        'company_id': rec.company_id.id,
                        'instance_id': rec.id,
                        'process_name': 'project',
                    })

                    context.update({'export_log_id': log.id})

                    wizard = self.env['hubstaff.export.project.wizard'].with_context(context)
                    for project in projects:
                        processed_project_ids.append(project.id)  # mark as processed
                        try:
                            wizard._export_single_project(project, rec)
                        except Exception as e:
                            rec.with_context(context)._create_log(
                                message=f"Project export failed: {project.name} | Error: {str(e)}",
                                log_type='export',
                                api_response=str(e)
                            )
                            continue

                    # Update project sync date
                    rec.last_project_synced_date = fields.Datetime.now()
                    self.env.cr.commit()

            # -------------------------------------------------
            # PART 2 — EXPORT TASKS ONLY (if enabled)
            # -------------------------------------------------
            if rec.is_export_task:

                context = dict(base_context)
                context.update({'process_name': 'task'})

                # Find projects already exported to Hubstaff BUT NOT handled in Part 1
                exported_projects = self.env['project.project'].search([
                    ('hubstaff_project_id', '!=', False),
                    ('hubstaff_instance_id', '=', rec.id),
                    ('id', 'not in', processed_project_ids),
                ])

                if not exported_projects:
                    continue

                # First check if ANY project has pending tasks
                projects_with_pending_tasks = []
                for project in exported_projects:
                    pending_tasks = self.env['project.task'].search([
                        ('project_id', '=', project.id),
                        ('hubstaff_task_id', '=', False),
                    ], limit=1)

                    if pending_tasks:
                        projects_with_pending_tasks.append(project)

                #  If no pending tasks at all → do NOTHING (no blank log)
                if not projects_with_pending_tasks:
                    continue

                # Now create ONE log because we are sure tasks exist
                task_log = self.env['hubstaff.log'].create({
                    'process_type': 'export',
                    'company_id': rec.company_id.id,
                    'instance_id': rec.id,
                    'process_name': 'task',
                })

                context.update({'export_log_id': task_log.id})

                wizard = self.env['hubstaff.export.project.wizard'].with_context(context)
                # Export only projects that really have pending tasks
                for project in projects_with_pending_tasks:
                    try:
                        wizard._export_project_tasks(project, rec)
                        self.env.cr.commit()
                    except Exception as e:
                        rec.with_context(context)._create_log(
                            message=f"Task export failed for project: {project.name} | Error: {str(e)}",
                            log_type='export',
                            api_response=str(e)
                        )
                        continue

    def _compute_counts(self):
        for rec in self:
            rec.imported_project_count = self.env['project.project'].search_count([
                ('hubstaff_instance_id', '=', rec.id)
            ])
            rec.imported_task_count = self.env['project.task'].search_count([
                ('hubstaff_instance_id', '=', rec.id)
            ])
            rec.imported_user_count = self.env['res.users'].search_count([
                ('hubstaff_user_id', '!=', False)
            ])

    def action_view_instance_projects(self):
        """Open only projects imported/created from this Hubstaff instance"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Imported Projects'),
            'res_model': 'project.project',
            'view_mode': 'list,form',
            'domain': [('hubstaff_instance_id', '=', self.id)],
            'context': {'default_hubstaff_instance_id': self.id},
        }

    def action_view_instance_tasks(self):
        """Open only tasks imported/created from this Hubstaff instance"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Imported Tasks'),
            'res_model': 'project.task',
            'view_mode': 'list,form',
            'domain': [('hubstaff_instance_id', '=', self.id)],
            'context': {'default_hubstaff_instance_id': self.id},
        }

    def action_view_users(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Imported Users'),
            'res_model': 'res.users',
            'view_mode': 'list,form',
            'domain': [('hubstaff_user_id', '!=', False)],

        }

    @api.model
    def _cron_refresh_hubstaff_tokens(self):
        """Cron job to generate access tokens safely for all instances"""

        instances = self.search([('state', '=', 'confirm')])

        for instance in instances:
            context = dict(self.env.context or {})
            context.update({'process_name': 'token'})

            main_log_id = instance.with_context(context)._create_log(
                log_type='import',
                force_new_log=True
            )

            instance = instance.with_context(context,
                import_log_id=main_log_id
            )

            if not instance.refresh_token:
                instance._create_log(
                    message="Missing Refresh Token.",
                    log_type='import',
                    api_response="refresh_token is empty"
                )
                continue

            payload = {
                'grant_type': 'refresh_token',
                'refresh_token': instance.refresh_token,
                'client_id': instance.client_id,
                'client_secret': instance.client_secret,
            }

            try:
                data, response = instance._hubstaff_api_call(
                    full_url=instance.account_token_url,
                    method='POST',
                    payload=payload,
                    headers={'Content-Type': 'application/x-www-form-urlencoded'},
                    is_form=True
                )

                data = response.json()

                vals = {
                    'access_token': data.get('access_token'),
                    'token_generated_at': fields.Datetime.now(),
                }

                if data.get('refresh_token'):
                    vals['refresh_token'] = data.get('refresh_token')

                instance.write(vals)

                instance._create_log(
                    message="Access token refreshed successfully.",
                    log_type='import'
                )

            except Exception as e:
                instance._create_log(
                    message=f"Token refresh failed: {str(e)}",
                    log_type='import',
                    api_response=str(e)
                )

    def action_sync_all_users_button(self):
        """Button click to sync all users for this instance."""
        self.ensure_one()

        context = dict(self.env.context or {})
        context.update({'process_name': 'user', 'import_operations': True})

        Users = self.env['res.users'].sudo()
        results = []

        if not self.access_token:
            raise UserError(_("Please configure access token."))

        try:
            instance = self.with_context(context)
            main_log_id = instance._create_log(
                log_type='import',
                force_new_log=True
            )
            instance = instance.with_context(import_log_id=main_log_id)

            # --------------------------------------------------
            # Fetch organization members
            # --------------------------------------------------
            members_endpoint = f"/v2/organizations/{self.hubstaff_organization_id}/members"

            members = instance._hubstaff_paginated_fetch(
                endpoint=members_endpoint,
                data_key="members"
            )

            if not members:
                instance._create_log(
                    message="No organization members returned from Hubstaff.",
                    log_type='import',
                    api_request=False,
                    api_response=[]
                )
                raise UserError(_("No Hubstaff members found."))

            # --------------------------------------------------
            # Process each member
            # --------------------------------------------------
            for member in members:
                user_id = member.get('user_id')
                if not user_id:
                    instance._create_log(
                        message="Member record missing user_id.",
                        log_type='import',
                    )
                    results.append(("Unknown", "Member missing user_id"))
                    continue

                # Fetch user details
                user_endpoint = f"/v2/users/{user_id}"
                try:
                    user_data, user_raw = instance._hubstaff_api_call(
                        endpoint=user_endpoint,
                        method='GET'
                    )
                except Exception as e:
                    instance._create_log(
                        message=f"User sync failed for member {member.get('user_id')}: {str(e)}",
                        log_type='import',
                        api_response=str(e)
                    )
                    continue

                hubstaff_user = (user_data or {}).get('user')
                if not hubstaff_user:
                    msg = f"Empty user data received from Hubstaff | User ID: {user_id}"
                    instance._create_log(
                        message=msg,
                        log_type='import',
                        api_request=False,
                        api_response=user_raw
                    )
                    results.append((user_id, msg))
                    continue

                email = (hubstaff_user.get('email') or '').lower()
                hs_id = hubstaff_user.get('id')
                name = hubstaff_user.get('name') or (email.split('@')[0] if email else 'Hubstaff User')

                if not email:
                    instance._create_log(
                        message=f"Hubstaff user missing email | User ID: {user_id}",
                        log_type='import',
                    )
                    results.append((user_id, "Email missing"))
                    continue

                # Create / Update Odoo user
                odoo_user = Users.search([('email', '=', email)], limit=1)

                if not odoo_user:
                    odoo_user = Users.create({
                        'login': name,
                        'name': name,
                        'email': email,
                        'hubstaff_user_id': str(hs_id) if hs_id else False,
                    })

                    msg = f"New Odoo user created → Hubstaff ID: {hs_id}"
                    results.append((email, msg))
                    instance._create_log(message=msg, log_type='import')
                else:
                    if hs_id:
                        odoo_user.write({'hubstaff_user_id': str(hs_id)})

                    msg = f"Existing user synced → Hubstaff ID: {hs_id}"
                    results.append((odoo_user.name, msg))
                    instance._create_log(message=msg, log_type='import')

        except Exception as e:
            err_msg = f"Critical User Sync Error: {str(e)}"
            instance._create_log(
                message=err_msg,
                log_type='import',
                api_request=False,
                api_response=str(e)
            )
            raise UserError(_("Hubstaff user sync failed:\n%s") % str(e))

        # --------------------------------------------------
        # Final notification
        # --------------------------------------------------
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Hubstaff Sync Completed"),
                "message": _("Total members processed: %s") % len(results),
                "type": "success",
                "sticky": False,
            },
        }

    @api.model
    def _cron_import_project_task(self):
        instances = self._get_valid_instances()
        for instance in instances:
            instance._sync_projects_and_tasks()

    def _get_valid_instances(self):
        return self.env['hubstaff.instance.integration'].search([
            ('access_token', '!=', False),
            ('hubstaff_organization_id', '!=', False),
            ('api_url', '!=', False),
            ('state', '=', 'confirm')
        ])

    def _sync_projects_and_tasks(self):
        """Sync projects and tasks instance wise"""

        instance = self.with_context(import_operations=True)

        # -------------------------
        # PROJECT SYNC
        # -------------------------
        try:
            main_log_id = instance.with_context(process_name='project')._create_log(
                log_type='import',
                force_new_log=True
            )
            instance = instance.with_context(import_log_id=main_log_id, process_name='project')
            instance._sync_hubstaff_projects()

        except Exception as e:
            _logger.exception("Project sync failed")
            instance._create_log(f"Project sync error: {str(e)}", 'import')

        # -------------------------
        # TASK SYNC
        # -------------------------
        try:
            main_log_id = instance.with_context(process_name='task')._create_log(
                log_type='import',
                force_new_log=True
            )

            instance = instance.with_context(import_log_id=main_log_id, process_name='task')
            instance._sync_hubstaff_tasks()

        except Exception as e:
            _logger.exception("Task sync failed")
            instance._create_log(f"Task sync error: {str(e)}", 'import')

    def _sync_hubstaff_projects(self):
        endpoint = f"/v2/organizations/{self.hubstaff_organization_id}/projects"
        projects = self._hubstaff_paginated_fetch(
            endpoint=endpoint,
            data_key="projects"
        )

        for hs_project in projects:
            try:
                self._import_project(hs_project)
            except Exception as e:
                self._create_log(
                    message=f"Project import failed: {str(e)}",
                    log_type='import'
                )
                continue

    def _import_project(self, hs_project):
        Project = self.env['project.project']
        hs_id = str(hs_project.get('id'))
        project_name = hs_project.get('name')

        exists_project = Project.search([
            ('hubstaff_project_id', '=', hs_id)
        ], limit=1)

        manager = self._get_project_manager(hs_id)

        vals = {
            "name": project_name,
            "active": hs_project.get('status') == 'active',
            "user_id": manager.id if manager else False,
            "hubstaff_organization_id": self.hubstaff_organization_id,
        }

        # ----------------------------------------------------
        # UPDATE EXISTING PROJECT
        # ----------------------------------------------------
        if exists_project:
            if not exists_project.hubstaff_instance_id:
                vals["hubstaff_instance_id"] = self.id

            exists_project.with_context(import_project=True).write(vals)

            self._create_log(
                message=f"Project updated from Hubstaff: {project_name}",
                log_type='import',
            )
            return exists_project

        # ----------------------------------------------------
        # CREATE NEW PROJECT
        # ----------------------------------------------------
        vals.update({
            'company_id': self.company_id.id,
            'hubstaff_project_id': hs_id,
            'hubstaff_instance_id': self.id,
        })

        project = Project.create(vals)

        self._create_log(
            message=f"Project imported: {project_name}",
            log_type='import',
        )
        return project

    def _get_project_manager(self, hs_project_id):

        Users = self.env['res.users']
        endpoint = f"/v2/projects/{hs_project_id}/members"

        try:
            members = self._hubstaff_paginated_fetch(
                endpoint=endpoint,
                data_key="members"
            )
        except Exception:
            return False

        for m in members:
            if not isinstance(m, dict):
                continue

            if (
                    m.get('membership_status') == 'active'
                    and m.get('membership_role') == 'manager'
            ):
                user = Users.search(
                    [('hubstaff_user_id', '=', str(m.get('user_id')))],
                    limit=1
                )
                if user:
                    return user

        return False

    def _sync_hubstaff_tasks(self):
        Project = self.env['project.project']
        projects = Project.search([ ('hubstaff_project_id', '!=', False)])

        for project in projects:
            try:
                self._import_tasks_for_project(project)
            except Exception as e:
                self._create_log(
                    message=f"Task sync failed for project {project.name}: {str(e)}",
                    log_type='import',
                )
                continue

    def _import_tasks_for_project(self, project, hs_tasks=None):
        Task = self.env['project.task']

        # --------------------------------------------------
        # WEBHOOK MODE
        # If tasks already passed, DO NOT call API
        # --------------------------------------------------
        if hs_tasks is None:
            endpoint = f"/v2/projects/{project.hubstaff_project_id}/tasks"

            hs_tasks = self._hubstaff_paginated_fetch(
                endpoint=endpoint,
                data_key="tasks"
            )

        if not isinstance(hs_tasks, list):
            self._create_log(
                message=f"Invalid task response for project {project.name}",
                log_type='import',
            )
            return

        log_messages = []

        for hs_task in hs_tasks:
            if not isinstance(hs_task, dict):
                continue
            hs_task_id = str(hs_task.get('id'))
            task_name = hs_task.get('summary') or hs_task.get('name')

            exists_task = Task.search([
                ('hubstaff_task_id', '=', hs_task_id)
            ], limit=1)

            assignee = self._prepare_task_assignee(hs_task.get('assignee_ids'))

            # ----------------------------
            # UPDATE EXISTING TASK
            # ----------------------------
            if exists_task:
                exists_task.with_context(import_project=True).write({
                    "name": task_name,
                    "project_id": project.id,
                    "user_ids": [(6, 0, [assignee.id])] if assignee else [(5, 0, 0)],
                    "hubstaff_instance_id": self.id,
                })

                msg = f"Task already exists, updated: {task_name}"
                log_messages.append(msg)

                self._create_log(
                    message=msg,
                    log_type='import',
                )
                continue

            # ----------------------------
            # CREATE NEW TASK
            # ----------------------------
            vals = {
                'name': task_name,
                'project_id': project.id,
                'hubstaff_task_id': hs_task_id,
                'user_ids': [(6, 0, [assignee.id])] if assignee else False,
                'hubstaff_instance_id': self.id,
            }

            try:
                Task.with_context(import_project=True).create(vals)
                msg = f"{task_name} → Task imported | Assigned to: {assignee.name if assignee else 'Not Found'}"
                log_messages.append(msg)

                self._create_log(
                    message=msg,
                    log_type='import',
                )

            except Exception as e:
                msg = f"{task_name} → Failed: {str(e)}"
                log_messages.append(msg)

                self._create_log(
                    message=msg,
                    log_type='import'
                )

        # grouped log
        if log_messages and not self.env.context.get('from_webhook'):
            self._create_log(
                message="\n".join(log_messages),
                log_type='import',
            )

    def _prepare_task_assignee(self, assignee_ids):
        """Match Hubstaff assignee to Odoo user"""
        if not assignee_ids:
            return False
        user = self.env['res.users'].search([('hubstaff_user_id', '=', str(assignee_ids[0]))], limit=1)
        return user or False

    def _is_hubstaff_token_valid(self):
        context = dict(self.env.context or {})
        context.update({'process_name': 'token'})

        try:
            data, response = self.with_context(context)._hubstaff_api_call(
                endpoint="/v2/organizations",
                method="GET"
            )
        except Exception as e:
            self._create_log(
                message=f"Token validation failed: {str(e)}",
                log_type='import'
            )
            return False

        if response.status_code == 401:
            try:
                data = response.json()
            except Exception:
                data = {}
            return data.get('error') != 'invalid_token'

        return response.status_code == 200

    def action_generate_access_token(self):
        self.ensure_one()

        context = dict(self.env.context or {})
        context.update({'process_name': 'token'})

        if not self.client_id or not self.client_secret:
            raise UserError(_("Please configure Client ID and Client Secret first."))

        if not self.refresh_token:
            raise UserError(_("Refresh Token is missing."))

        payload = {
            "grant_type": "refresh_token",
            "refresh_token": self.refresh_token,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
        }

        try:
            data, response = self.with_context(context)._hubstaff_api_call(
                full_url=self.account_token_url,
                method="POST",
                payload=payload,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                is_form=True
            )
        except Exception as e:
            raise UserError(str(e))

        if response.status_code != 200 or not data.get("access_token"):
            raise UserError(
                _("Failed to generate access token:\n%s") % response.text
            )

        vals = {
            "access_token": data.get("access_token"),
            "token_generated_at": fields.Datetime.now(),
        }

        if data.get("refresh_token"):
            vals["refresh_token"] = data.get("refresh_token")

        self.write(vals)

        self.with_context(context)._create_log(
            message="Access token generated successfully.",
            log_type="import",
            api_request=payload,
            api_response=response.text
        )

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Success"),
                "message": _("Access token generated successfully."),
                "type": "success",
                "sticky": False,
            },
        }

    @api.model
    def _cron_import_task_entry(self):
        instances = self.search([
            ('state', '=', 'confirm'),
            ('access_token', '!=', False),
            ('company_id', '!=', False),
        ])

        for instance in instances:
            main_log_id = False

            try:
                instance = instance.with_context(
                    import_operations=True,
                    process_name='task_entry',
                )

                main_log_id = instance._create_log(
                    log_type='import',
                    force_new_log=True
                )

                instance = instance.with_context(import_log_id=main_log_id)
                instance._sync_hubstaff_task_entries()

            except Exception as e:
                    _logger.exception(
                        "Cron: Failed to import Hubstaff task entries for instance %s",
                        instance.display_name
                    )

                    instance.with_context(import_log_id=main_log_id, process_name='task_entry')._create_log(
                        message=f"Cron import failed for instance {instance.display_name}",
                        log_type='import',
                        api_response=str(e)
                    )

    def _sync_hubstaff_task_entries(self):
        self.ensure_one()
        instance = self.with_context(process_name='task_entry')
        try:
            # --------------------------------------------------
            # Fetch daily activities
            # --------------------------------------------------
            activities = instance._hubstaff_get_daily_activities()
            if not activities:
                instance._create_log(
                    message="No daily activity entries found for today.",
                    log_type='import'
                )
                return True

            # --------------------------------------------------
            # Process and create timesheets
            # --------------------------------------------------
            project_logs = instance._process_and_create_timesheets(activities)
            instance._log_project_wise(project_logs)
            return True

        except Exception as e:
            instance._create_log(
                message=f"Task entry sync failed: {str(e)}",
                log_type='import',
                api_response=str(e)
            )
            raise

    def _hubstaff_get_daily_activities(self):

        days = self.task_entry_days or 1
        today = datetime.utcnow().date()
        start_date = today - timedelta(days=days)

        endpoint = f"/v2/organizations/{self.hubstaff_organization_id}/activities/daily"
        params = {
            "date[start]": start_date.isoformat(),
            "date[stop]": today.isoformat(),
        }

        try:
            activities = self._hubstaff_paginated_fetch(
                endpoint=endpoint,
                data_key="daily_activities",
                params=params,
            )
        except Exception:
            if self.env.context.get('import_operations'):
                raise UserError(_("Unable to connect to Hubstaff. Please try again later."))
            return []

        return activities

    def _process_and_create_timesheets(self, activities):

        AAL = self.env['account.analytic.line']
        Users = self.env['res.users']
        Projects = self.env['project.project']
        Tasks = self.env['project.task']

        act_ids = [str(a["id"]) for a in activities]
        existing_lines = AAL.search([("hubstaff_task_entry_id", "in", act_ids)])
        existing_map = {l.hubstaff_task_entry_id: l for l in existing_lines}

        logs = {}

        for act in activities:
            a_id = str(act["id"])

            if a_id in existing_map:
                existing_map[a_id].write({
                    "date": act.get('date'),
                    "unit_amount": self._seconds_to_hours(act.get('tracked')),
                })
                continue

            user = Users.search([("hubstaff_user_id", "=", str(act.get("user_id")))], limit=1)
            if not user or not user.employee_id:
                self._create_log(
                    f"Skipped activity {a_id}: Employee not found",
                    'import'
                )
                continue

            project = Projects.search([("hubstaff_project_id", "=", str(act.get("project_id")))], limit=1)
            task = Tasks.search([("hubstaff_task_id", "=", str(act.get("task_id")))], limit=1)

            vals = self._prepare_timesheet_vals(a_id, user, project, task, act.get('tracked'), act)
            AAL.create(vals)
            self.env.cr.commit()

            hours = vals.get("unit_amount", 0.0)
            project_name = project.name if project else "No Project"
            task_name = task.name if task else "No Task"

            msg = (
                f"Created Timesheet | "
                f"Employee: {user.name} | "
                f"Project: {project_name} | "
                f"Task: {task_name} | "
                f"Hours: {hours:.2f}"
            )

            key = project.id if project else False
            logs.setdefault(key, []).append(msg)

        return logs

    def _prepare_timesheet_vals(self, act_id, user, project, task, time,act):
        return {
            "name": task.name if task else f"Hubstaff Activity {act_id}",
            "date": act.get('date'),
            "user_id": user.id if user else False,
            "employee_id":user.employee_id.id if user and user.employee_id else False,
            "project_id": project.id if project else False,
            "task_id": task.id if task else False,
            "unit_amount": self._seconds_to_hours(time),
            "company_id": self.company_id.id,
            "hubstaff_task_id": task.hubstaff_task_id if task else False,
            "hubstaff_task_entry_id": act_id,
            "hubstaff_instance_id": task.hubstaff_instance_id.id if task else self.id,
            "is_billable": True if act.get('billable') else False,
        }

    def _seconds_to_hours(self, seconds):
        return seconds / 3600 if seconds else 0

    def _get_utc_today(self):
        return datetime.utcnow().date()

    def _log_project_wise(self, project_logs):
        Projects = self.env['project.project']

        for p_id, lines in project_logs.items():
            project = Projects.browse(p_id) if p_id else False
            self._create_log(
                message="\n".join(lines),
                log_type='import',
            )

    def action_authenticate(self):
        self.ensure_one()
        if not self.redirect_url:
            raise UserError(_("Please configure Redirect URL."))

        nonce = str(int(time.time() * 1000)) + str(random.randint(1000, 9999))
        auth_url = (
            "https://account.hubstaff.com/authorizations/new?"
            f"client_id={self.client_id}"
            f"&response_type=code"
            f"&scope=openid hubstaff:read hubstaff:write"
            f"&redirect_uri={self.redirect_url}"
            f"&nonce={nonce}"
            f"&state={self.id}"
        )

        return {
            "type": "ir.actions.act_url",
            "url": auth_url,
            "target": "new",
        }

    def action_reset_to_draft(self):
        self.state = "draft"
