# -*- coding: utf-8 -*-
import base64
import logging
from datetime import date
from dateutil.relativedelta import relativedelta

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class VrajaAICard(models.Model):
    """Extends the common vraja.ai.card Selection to add Cashflow AI store."""
    _inherit = 'vraja.ai.card'

    vraja_common_store = fields.Selection(
        selection_add=[('cashflow', 'Cashflow AI')],
        ondelete={'cashflow': 'set null'},
    )

    # ── CFO Report ────────────────────────────────────────────────────────
    cfo_user_id = fields.Many2one(
        'res.users',
        string='CFO User (Report)',
        domain="[('share', '=', False), ('active', '=', True)]",
        help=(
            "The selected user will automatically receive the Executive Report PDF "
            "every night via email through the scheduled action. "
            "Leave empty to disable report emails for this dashboard."
        ),
    )

    # ──────────────────────────────────────────────────────────────────────────
    def action_review_dashboard(self):
        self.ensure_one()
        if self.vraja_common_store == 'cashflow':
            existing = self.env['vraja.cashflow.analysis'].search([
                ('card_id', '=', self.id),
                ('state', '=', 'done')
            ], limit=1)

            if existing:
                action = super().action_review_dashboard()
                # Launch the cashflow component directly. The generic AI
                # dashboard is only an empty shell and depends on a template
                # extension to mount store-specific content.
                action['tag'] = 'vraja_cashflow_dashboard'
                return action
            else:
                return {
                    'name': 'Generate Cashflow Intelligence',
                    'type': 'ir.actions.act_window',
                    'res_model': 'vraja.cashflow.wizard',
                    'view_mode': 'form',
                    'target': 'new',
                    'context': {'default_card_id': self.id},
                }

        return super().action_review_dashboard()

    def action_log_view(self):
        self.ensure_one()
        res = super().action_log_view()
        if self.vraja_common_store == 'cashflow':
            # Remove hard domain so user can un-filter if they want
            res['domain'] = []
            res['context'] = {'search_default_store_cashflow': 1, 'default_vraja_common_log_store': 'cashflow'}
        return res

    # ── OWL RPC Helpers ───────────────────────────────────────────────────────
    @api.model
    def get_cfo_user_for_card(self, card_id):
        """Return current CFO user info for the given card (called from OWL)."""
        card = self.browse(card_id)
        if card.exists() and card.cfo_user_id:
            return {
                'id': card.cfo_user_id.id,
                'name': card.cfo_user_id.name,
                'email': card.cfo_user_id.email or '',
            }
        return False

    @api.model
    def set_cfo_user_for_card(self, card_id, user_id):
        """Set (or clear) the CFO user for a given card (called from OWL)."""
        card = self.browse(card_id)
        if card.exists():
            card.sudo().write({'cfo_user_id': user_id or False})
            return True
        return False

    @api.model
    def get_internal_users_list(self):
        """Return list of internal (non-portal) users for OWL CFO dropdown."""
        users = self.env['res.users'].search(
            [('share', '=', False), ('active', '=', True)],
            order='name asc',
            limit=200,
        )
        return [{'id': u.id, 'name': u.name, 'email': u.email or ''} for u in users]

    # ── Scheduled Action ──────────────────────────────────────────────────────
    @api.model
    def action_send_cfo_nightly_report(self):
        """
        Scheduled Action: Every night, send the Executive Report PDF to the
        configured CFO user for each Cashflow AI card that has one set.

        Triggered by: Cashflow AI – CFO Executive Report (ir.cron).
        """
        _logger.info("Cashflow AI: Starting CFO report email job.")

        cashflow_cards = self.search([
            ('vraja_common_store', '=', 'cashflow'),
            ('cfo_user_id', '!=', False),
        ])

        if not cashflow_cards:
            _logger.info(
                "Cashflow AI: No Cashflow AI cards with a CFO user configured. "
                "Job has nothing to do — skipping."
            )
            return True

        today = date.today()
        # Default analysis window: current month + 2 previous months
        date_from = today.replace(day=1) - relativedelta(months=2)
        date_to = today

        report_action = self.env.ref(
            'vraja_cashflow_ai.action_report_cashflow_analysis',
            raise_if_not_found=False,
        )
        if not report_action:
            _logger.error(
                "Cashflow AI: Report action 'vraja_cashflow_ai.action_report_cashflow_analysis' "
                "not found. Cannot send CFO emails."
            )
            return False

        for card in cashflow_cards:
            try:
                self._send_cfo_report_for_card(card, date_from, date_to, report_action, today)
            except Exception as exc:
                _logger.exception(
                    "Cashflow AI: Failed to send CFO report for card %s: %s",
                    card.id, exc,
                )

        _logger.info("Cashflow AI: CFO report job completed.")
        return True

    def _send_cfo_report_for_card(self, card, date_from, date_to, report_action, today):
        """Generate PDF and email the latest Executive Report to the card's CFO user."""
        cfo_user = card.cfo_user_id
        cfo_email = cfo_user.email
        if not cfo_email:
            _logger.warning(
                "Cashflow AI: CFO user '%s' (id=%s) has no email address. "
                "Skipping card %s.",
                cfo_user.name, cfo_user.id, card.id,
            )
            return

        # ── Find or generate the latest done analysis ─────────────────────
        analysis = self.env['vraja.cashflow.analysis'].search([
            ('card_id', '=', card.id),
            ('state', '=', 'done'),
        ], order='generated_on desc', limit=1)

        if not analysis:
            _logger.info(
                "Cashflow AI: No completed analysis for card %s. "
                "Generating a fresh one for CFO email...", card.id,
            )
            result = self.env['vraja.cashflow.analysis'].generate_analysis({
                'date_from': str(date_from),
                'date_to': str(date_to),
                'card_id': card.id,
            })
            if result.get('state') != 'done':
                _logger.warning(
                    "Cashflow AI: Fresh analysis for card %s failed or not ready. "
                    "Skipping CFO email.", card.id,
                )
                return
            analysis = self.env['vraja.cashflow.analysis'].browse(result['analysis_id'])

        # ── Render PDF ────────────────────────────────────────────────────
        pdf_content, _mime = self.env['ir.actions.report']._render_qweb_pdf(
            report_action, [analysis.id]
        )

        # ── Create temporary attachment ───────────────────────────────────
        filename = f"CFO_Executive_Report_{today.strftime('%Y-%m-%d')}.pdf"
        attachment = self.env['ir.attachment'].create({
            'name': filename,
            'type': 'binary',
            'datas': base64.b64encode(pdf_content).decode('utf-8'),
            'mimetype': 'application/pdf',
            'res_model': 'vraja.cashflow.analysis',
            'res_id': analysis.id,
        })

        # ── Build email ───────────────────────────────────────────────────
        company = self.env.company
        runway_str = (
            'Indefinite'
            if (analysis.cash_runway_days or 0) >= 999
            else f"{analysis.cash_runway_days} days"
        )
        summary_block = ''
        if analysis.executive_summary:
            summary_block = f"""
            <div style="background:#fff8e7;border-radius:6px;padding:14px;
                        margin:0 0 16px 0;border-left:4px solid #f59e0b;">
                <strong>AI Executive Summary:</strong><br/>
                <em style="color:#555;">{analysis.executive_summary}</em>
            </div>"""

        body_html = f"""
        <div style="font-family:Arial,sans-serif;color:#1a1a2e;max-width:620px;">
            <div style="background:linear-gradient(135deg,#1a1a2e,#16213e);
                        padding:28px 24px;border-radius:10px 10px 0 0;">
                <h2 style="color:#fff;margin:0;font-size:22px;">
                    &#128202; CFO Executive Cash Flow Report
                </h2>
                <p style="color:#a0aec0;margin:8px 0 0 0;font-size:13px;">
                    {company.name} &nbsp;·&nbsp; {today.strftime('%d %B %Y')}
                </p>
            </div>
            <div style="background:#f8f9fa;padding:24px;border-radius:0 0 10px 10px;
                        border:1px solid #e2e8f0;border-top:none;">
                <p style="margin:0 0 14px 0;">Dear <strong>{cfo_user.name}</strong>,</p>
                <p style="margin:0 0 14px 0;">
                    Please find attached your <strong>Executive Cash Flow Report</strong>
                    generated by <em>Vraja Cashflow AI</em>.
                </p>
                <div style="background:#fff;border-radius:8px;padding:16px;
                            margin:0 0 16px 0;border-left:4px solid #4a6cf7;">
                    <table style="width:100%;border-collapse:collapse;font-size:14px;">
                        <tr>
                            <td style="padding:4px 8px 4px 0;color:#4a6cf7;font-weight:bold;
                                       white-space:nowrap;">Analysis Period:</td>
                            <td style="padding:4px 0;">{analysis.date_from} &rarr; {analysis.date_to}</td>
                        </tr>
                        <tr>
                            <td style="padding:4px 8px 4px 0;color:#4a6cf7;font-weight:bold;">
                                Liquidity Status:</td>
                            <td style="padding:4px 0;">{analysis.liquidity_status or 'N/A'}</td>
                        </tr>
                        <tr>
                            <td style="padding:4px 8px 4px 0;color:#4a6cf7;font-weight:bold;">
                                Liquidity Score:</td>
                            <td style="padding:4px 0;">{analysis.liquidity_score or 0:.0f} / 100</td>
                        </tr>
                        <tr>
                            <td style="padding:4px 8px 4px 0;color:#4a6cf7;font-weight:bold;">
                                Cash Runway:</td>
                            <td style="padding:4px 0;">{runway_str}</td>
                        </tr>
                    </table>
                </div>
                {summary_block}
                <p style="color:#718096;font-size:12px;margin:16px 0 0 0;
                           border-top:1px solid #e2e8f0;padding-top:12px;">
                    This report is automatically generated and emailed every night by
                    <strong>Vraja Cashflow AI</strong>.<br/>
                    To change the CFO recipient or disable this notification, open the
                    AI Dashboard and update the <em>CFO Report Recipient</em> field.
                </p>
            </div>
        </div>"""

        mail_values = {
            'subject': (
                f"[{company.name}] CFO Executive Cash Flow Report"
                f" — {today.strftime('%d %B %Y')}"
            ),
            'body_html': body_html,
            'email_to': cfo_email,
            'email_from': (
                company.email
                or self.env['ir.mail_server'].sudo().search([], limit=1).smtp_user
                or 'noreply@example.com'
            ),
            'attachment_ids': [(4, attachment.id)],
            'auto_delete': True,
        }
        mail = self.env['mail.mail'].sudo().create(mail_values)
        mail.send()

        _logger.info(
            "Cashflow AI: CFO report sent to '%s' <%s> (card %s, analysis %s).",
            cfo_user.name, cfo_email, card.id, analysis.id,
        )
