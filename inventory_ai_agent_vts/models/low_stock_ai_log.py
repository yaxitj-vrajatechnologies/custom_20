from odoo import models, fields, api


class InventoryAILog(models.Model):
    _inherit = 'vraja.ai.log'

    vraja_common_log_store = fields.Selection(
        selection_add=[('ai_low_stock', 'Low Stock Alert')]
    )
    inventory_ai_minimum_stock_threshold = fields.Integer(string='Minimum Stock Threshold', readonly=True)
    inventory_ai_sale_forecast_days = fields.Integer(string='Sales Forecast Days', readonly=True)
    inventory_ai_forecast_period = fields.Selection(
        [('all_data', 'All Time Data'), ('selected_data', 'Preferred Data'), ],
        string='Sales Forecast Period')
    inventory_ai_purchase_forecast_period = fields.Selection(
        [('all_data', 'All Time Data'), ('selected_data', 'Preferred Data'), ],
        string='Purchase Forecast Period')
    inventory_ai_purchase_forecast_days = fields.Integer(string='Purchase Forecast Days', readonly=True)
    inventory_ai_auto_create_rfq = fields.Boolean(string='Auto Create RFQ', readonly=True)
    inventory_ai_total_products = fields.Integer(string='Products Recommended', readonly=True)
    inventory_ai_total_order_qty = fields.Float(string='Total Recommended Qty', readonly=True)
    inventory_ai_purchase_order_count = fields.Integer(string='RFQs Created', readonly=True)
    inventory_ai_error = fields.Text(string='Error', readonly=True)
    inventory_ai_token_usage = fields.Char(string='Token Usage', readonly=True)

    def get_formview_action(self, access_uid=None):
        action = super().get_formview_action(access_uid=access_uid)
        if self.vraja_common_log_store == 'ai_low_stock':
            view_id = self.env.ref('inventory_ai_agent_vts.inventory_ai_log_form_vts').id
            action['views'] = [(view_id, 'form')]
        return action


class InventoryAILogLine(models.Model):
    _inherit = 'vraja.ai.log.line'

    inventory_ai_product_id = fields.Many2one('product.product', string='Product', readonly=True)
    inventory_ai_product_name = fields.Char(string='Product Name', readonly=True)
    inventory_ai_product_sku = fields.Char(string='SKU', readonly=True)
    inventory_ai_warehouse = fields.Char(string='Warehouse', readonly=True)
    inventory_ai_current_stock = fields.Float(string='Current Stock', readonly=True)
    inventory_ai_incoming_stock = fields.Float(string='Incoming Stock', readonly=True)
    inventory_ai_reserved_stock = fields.Float(string='Reserved Stock', readonly=True)
    inventory_ai_available_stock = fields.Float(string='Available Stock', readonly=True)
    inventory_ai_average_daily_sales = fields.Float(string='Average Daily Sales', readonly=True)
    inventory_ai_forecasted_demand = fields.Float(string='Forecasted Demand', readonly=True)
    inventory_ai_recommended_order_qty = fields.Float(string='Recommended Qty', readonly=True)
    inventory_ai_recommended_vendor_id = fields.Many2one('res.partner', string='Recommended Vendor', readonly=True)
    inventory_ai_recommended_vendor_name = fields.Char(string='Recommended Vendor Name', readonly=True)
    inventory_ai_vendor_lead_time_days = fields.Float(string='Vendor Lead Time Days', readonly=True)
    inventory_ai_vendor_reliability = fields.Char(string='Vendor Reliability', readonly=True)
    inventory_ai_decision = fields.Char(string='Decision', readonly=True)
    inventory_ai_reason = fields.Text(string='Reason', readonly=True)
