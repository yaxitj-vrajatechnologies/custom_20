from odoo import models, fields


class VendorAILog(models.Model):
    _inherit = 'vraja.ai.log'

    vraja_common_log_store = fields.Selection(
        selection_add=[('ai_vendor_intel', 'Vendor AI Intel')]
    )
    vendor_ai_forecast_period = fields.Selection(
        [('all_data', 'All Time Data'), ('selected_data', 'Preferred Data')],
        string='Forecast Period', readonly=True)
    vendor_ai_forecast_days = fields.Integer(string='Forecast Days', readonly=True)
    vendor_ai_total_vendors = fields.Integer(string='Vendors Analyzed', readonly=True)
    vendor_ai_error = fields.Text(string='Error', readonly=True)
    vendor_ai_token_usage = fields.Char(string='Token Usage', readonly=True)
    vendor_ai_report_html = fields.Html(string='AI Executive Report', readonly=True)

    def get_formview_action(self, access_uid=None):
        """
        Overrides the standard form view action to route users to the custom 
        Vendor Intelligence Log form view when clicking on a record in the list.
        
        :param access_uid: Optional user ID for access rights checking
        :return: Dictionary representing the window action
        """
        action = super().get_formview_action(access_uid=access_uid)
        if self.vraja_common_log_store == 'ai_vendor_intel':
            view_id = self.env.ref('vendor_ai_intelligence_vts.vendor_ai_log_form_vts').id
            action['views'] = [(view_id, 'form')]
        return action


class VendorAILogLine(models.Model):
    _inherit = 'vraja.ai.log.line'

    vendor_ai_partner_name = fields.Char(string='Vendor Name', readonly=True)
    vendor_ai_score = fields.Float(string='Score', readonly=True)
    vendor_ai_rank = fields.Integer(string='Rank', readonly=True)
    vendor_ai_category = fields.Char(string='Category', readonly=True)
    vendor_ai_reason = fields.Char(string='Reason', readonly=True)
