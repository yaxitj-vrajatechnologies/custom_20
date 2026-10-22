# -*- coding: utf-8 -*-
from odoo import fields, models
from dateutil.relativedelta import relativedelta
from datetime import date

class VrajaCashflowWizard(models.TransientModel):
    _name = 'vraja.cashflow.wizard'
    _description = 'Generate Cashflow Analyst Wizard'

    def _default_date_from(self):
        return date.today().replace(day=1) - relativedelta(months=2)

    def _default_date_to(self):
        return date.today()

    card_id = fields.Many2one('vraja.ai.card', string='Card Reference', required=True)
    date_from = fields.Date(string='From Date', default=_default_date_from, required=True)
    date_to = fields.Date(string='To Date', default=_default_date_to, required=True)
    company_id = fields.Many2one(
        'res.company', string='Company', required=True,
        help="Company whose data will be analyzed.",
        default=lambda self: self.env.company,
    )
    additional_info = fields.Text(
        string='Additional Information',
        help=(
            "Extra business context or instructions appended to the AI system prompt "
            "(e.g. 'We are seasonal — Q4 is always low', 'Ignore intercompany invoices', "
            "'Report in a conservative tone'). Leave empty for the standard analysis.\n\n"
            "These instructions are stored on the analysis and reused by later "
            "regenerations of this dashboard."
        ),
    )

    def action_generate_analysis(self):
        self.ensure_one()
        # Create an empty 'generating' record to kick things off.
        # Alternatively, we could just pass these parameters directly to the dashboard,
        # but the safest way is to go to the dashboard so it shows the loading spinner 
        # while the python code runs (otherwise the UI hangs in the backend).
        # We'll just open the dashboard, and the dashboard component's 'onMounted'
        # can actually do the generation if there is no analysis.
        
        # Or better yet: call generate_analysis right here, passing dates.
        params = {
            'date_from': str(self.date_from),
            'date_to': str(self.date_to),
            'card_id': self.card_id.id,
            'company_id': self.company_id.id,
            'additional_info': self.additional_info or '',
        }
        self.env['vraja.cashflow.analysis'].generate_analysis(params)

        # Return the client action to open the populated dashboard
        return {
            'type': 'ir.actions.client',
            'tag': 'vraja_ai_dashboard_template',
            'target': 'current',
            'params': {
                'card_id': self.card_id.id,
                'company_id': self.company_id.id,
            }
        }
