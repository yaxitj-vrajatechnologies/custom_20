from collections import defaultdict
from datetime import timedelta

from odoo import api, fields, models


class VendorIntelligenceScore(models.Model):
    _name = 'vendor.intelligence.score'
    _description = 'AI Vendor Intelligence Score'

    partner_id = fields.Many2one('res.partner', string='Vendor', required=True, ondelete='cascade')
    category_id = fields.Many2one('product.category', string='Product Category',
                                  help="If empty, this is the overall score for the vendor.")

    # Scores (0-100)
    delivery_score = fields.Float(string='Delivery Punctuality (35%)', default=0.0)
    fulfillment_score = fields.Float(string='Quantity Fulfillment (25%)', default=0.0)
    price_score = fields.Float(string='Price Consistency (20%)', default=0.0)
    lead_time_score = fields.Float(string='Lead Time Accuracy (20%)', default=0.0)

    composite_score = fields.Float(string='Overall Score', compute='_compute_composite_score', store=True)

    @api.depends('delivery_score', 'fulfillment_score', 'price_score', 'lead_time_score')
    def _compute_composite_score(self):
        """
        Computes the Overall Score for a vendor based on predefined weightings:
        Delivery (35%), Fulfillment (25%), Price (20%), and Lead Time (20%).
        """
        for record in self:
            record.composite_score = (
                    (record.delivery_score * 0.35) +
                    (record.fulfillment_score * 0.25) +
                    (record.price_score * 0.20) +
                    (record.lead_time_score * 0.20)
            )

    @api.model
    def _get_score_domain(self, forecast_period='all_data', forecast_days=0):
        """
        Builds the search domain to filter Purchase Orders based on the configured
        forecast period (e.g. All Time vs Last X Days).
        
        :param forecast_period: 'all_data' or 'selected_data'
        :param forecast_days: Integer number of days if 'selected_data' is used
        :return: List representing the Odoo ORM search domain
        """
        domain = [('state', 'in', ['purchase', 'done'])]
        days = max(int(forecast_days or 0), 0)
        if forecast_period == 'selected_data' and days > 0:
            from_date = fields.Datetime.now() - timedelta(days=days)
            domain.append(('date_approve', '>=', fields.Datetime.to_string(from_date)))
        return domain

    @api.model
    def _new_stats_bucket(self):
        """
        Initializes an empty statistics bucket for accumulating raw data metrics 
        for a specific vendor (and optionally product category).
        
        :return: Dictionary containing zeroed-out metric keys
        """
        return {
            'total_lines': 0,
            'received_qty': 0.0,
            'ordered_qty': 0.0,
            'on_time_lines': 0,
            'lead_time_scores': [],
            'prices_by_product': defaultdict(list),
        }

    @api.model
    def _get_actual_receipt_date(self, line):
        """
        Determines the actual physical receipt date for a purchase order line
        by inspecting its related completed stock moves.
        
        :param line: purchase.order.line record
        :return: Datetime of the maximum done move, or False if none exists
        """
        done_moves = line.move_ids.filtered(lambda move: move.state == 'done')
        return max(done_moves.mapped('date')) if done_moves else False

    @api.model
    def _add_line_to_stats(self, stats, line, actual_date):
        """
        Processes a single purchase order line and increments the vendor's 
        running statistics bucket. Calculates on-time delivery boolean and 
        lead time score penalties.
        
        :param stats: Dictionary (bucket) accumulating vendor metrics
        :param line: purchase.order.line record
        :param actual_date: Datetime of physical receipt
        """
        stats['total_lines'] += 1
        stats['ordered_qty'] += line.product_qty
        stats['received_qty'] += min(line.qty_received, line.product_qty)
        stats['prices_by_product'][line.product_id.id].append(line.price_unit)

        if actual_date and line.date_planned:
            if actual_date.date() <= line.date_planned.date():
                stats['on_time_lines'] += 1
                stats['lead_time_scores'].append(100.0)
            else:
                days_late = (actual_date.date() - line.date_planned.date()).days
                stats['lead_time_scores'].append(max(0.0, 100.0 - (days_late * 10.0)))
        else:
            stats['lead_time_scores'].append(0.0)

    @api.model
    def _price_consistency_score(self, prices_by_product):
        """
        Calculates the Price Consistency (Volatility) score by calculating the coefficient 
        of variation for each product individually, then averaging them out for the vendor.
        
        :param prices_by_product: Dictionary mapping product IDs to lists of unit prices
        :return: Float score out of 100
        """
        if not prices_by_product:
            return 100.0

        product_scores = []
        for product_id, prices in prices_by_product.items():
            prices = [price for price in prices if price is not False and price is not None]
            if len(prices) <= 1:
                product_scores.append(100.0)
                continue

            average_price = sum(prices) / len(prices)
            if not average_price:
                product_scores.append(100.0)
                continue

            variance = sum((price - average_price) ** 2 for price in prices) / len(prices)
            coefficient = (variance ** 0.5) / average_price
            score = max(0.0, min(100.0, 100.0 - (coefficient * 100.0)))
            product_scores.append(score)

        if not product_scores:
            return 100.0

        return sum(product_scores) / len(product_scores)

    @api.model
    def _score_from_stats(self, stats):
        """
        Converts a completed statistics bucket containing raw sums into 
        final normalized percentage scores (0-100) for Delivery, Fulfillment, 
        Price, and Lead Time.
        
        :param stats: Dictionary containing accumulated vendor metrics
        :return: Dictionary of final computed scores, or False if empty
        """
        total_lines = stats['total_lines']
        if not total_lines:
            return False

        ordered_qty = stats['ordered_qty']
        fulfillment_score = (stats['received_qty'] / ordered_qty) * 100 if ordered_qty else 0.0
        lead_time_scores = stats['lead_time_scores'] or [0.0]
        return {
            'delivery_score': round((stats['on_time_lines'] / total_lines) * 100, 2),
            'fulfillment_score': round(min(fulfillment_score, 100.0), 2),
            'price_score': round(self._price_consistency_score(stats['prices_by_product']), 2),
            'lead_time_score': round(sum(lead_time_scores) / len(lead_time_scores), 2),
        }

    @api.model
    def compute_all_scores(self, forecast_period='all_data', forecast_days=0):
        """
        Core computational engine. Clears existing scores, iterates over all 
        relevant Purchase Orders and Lines, aggregates statistics into buckets 
        by Vendor and Category, and saves the final calculated scores back to the database.
        
        :param forecast_period: 'all_data' or 'selected_data'
        :param forecast_days: Integer number of days for the rolling window
        :return: True upon successful completion
        """
        self.search([]).unlink()

        stats_by_key = defaultdict(self._new_stats_bucket)
        purchase_orders = self.env['purchase.order'].search(
            self._get_score_domain(forecast_period, forecast_days)
        )

        today = fields.Date.context_today(self)
        for order in purchase_orders:
            vendor_id = order.partner_id.id
            if not vendor_id:
                continue

            for line in order.order_line:
                if line.product_id.type == 'service' or not line.product_qty:
                    continue

                actual_date = self._get_actual_receipt_date(line)
                if not actual_date and (not line.date_planned or line.date_planned.date() > today):
                    continue

                category_id = line.product_id.categ_id.id or False
                self._add_line_to_stats(stats_by_key[(vendor_id, False)], line, actual_date)
                if category_id:
                    self._add_line_to_stats(stats_by_key[(vendor_id, category_id)], line, actual_date)

        score_vals = []
        for (vendor_id, category_id), stats in stats_by_key.items():
            scores = self._score_from_stats(stats)
            if scores:
                score_vals.append({
                    'partner_id': vendor_id,
                    'category_id': category_id,
                    **scores,
                })

        if score_vals:
            self.create(score_vals)

        return True
