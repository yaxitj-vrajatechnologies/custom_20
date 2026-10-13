# -*- coding: utf-8 -*-
from odoo import models, fields, api
from datetime import timedelta
from dateutil.relativedelta import relativedelta


class BookingDashboard(models.Model):
    _name = 'booking.dashboard'
    _description = 'Booking Dashboard'

    # ─── HELPER ───────────────────────────────────────────────
    @api.model
    def _get_period_domain(self, period='month'):
        today = fields.Date.context_today(self)

        if period == '7d':
            start_date = today - timedelta(days=7)
            end_date = today

        elif period == 'month':
            start_date = today.replace(day=1)
            end_date = (today.replace(day=1) + relativedelta(months=1)) - timedelta(days=1)

        elif period == 'year':
            start_date = today.replace(month=1, day=1)
            end_date = today.replace(month=12, day=31)

        else:
            start_date = today.replace(day=1)
            end_date = today

        return [
            ('preferred_date', '>=', start_date),
            ('preferred_date', '<=', end_date),
        ]

    # ─── KPI CARDS ────────────────────────────────────────────
    @api.model
    def get_dashboard_data(self, period='month'):
        Booking = self.env['booking.request']
        domain = self._get_period_domain(period)

        # get total revenue from approved bookings in period
        approved_bookings = Booking.search(domain + [('state', '=', 'approved')])
        total_revenue = sum(b.estimated_amount or 0.0 for b in approved_bookings)

        # Convert domain dates to strings for JS
        str_domain = [
            (d[0], d[1], str(d[2])) if isinstance(d, tuple) else d
            for d in domain
        ]

        return {
            'total': Booking.search_count(domain),
            'draft': Booking.search_count(domain + [('state', '=', 'draft')]),
            'under_review': Booking.search_count(domain + [('state', '=', 'under_review')]),
            'approved': Booking.search_count(domain + [('state', '=', 'approved')]),
            'rejected': Booking.search_count(domain + [('state', '=', 'rejected')]),
            'total_revenue': round(total_revenue, 2),
            'domain': str_domain,
        }

    # ─── TOP SERVICES ─────────────────────────────────────────
    @api.model
    def get_service_analysis(self, period='month'):
        domain = self._get_period_domain(period)

        data = self.env['booking.request'].read_group(
            domain=domain,
            fields=['service_type_id'],
            groupby=['service_type_id']
        )

        return [{'service': d['service_type_id'][1],'count': d['service_type_id_count'],}
            for d in data if d.get('service_type_id')]

    # ─── REVENUE BAR CHART ────────────────────────────────────
    @api.model
    def get_service_revenue_distribution(self, period='month'):
        domain = self._get_period_domain(period) + [('state', '=', 'approved')]
        bookings = self.env['booking.request'].search(domain)

        service_data = {}
        total = 0.0

        for b in bookings:
            service = b.service_type_id.name if b.service_type_id else None
            if not service:
                continue
            amount = b.estimated_amount or 0.0
            total += amount
            service_data[service] = service_data.get(service, 0.0) + amount

        result = [
            {
                'service': service,
                'amount': round(amount, 2),
                'percent': round(amount / total * 100, 2) if total else 0,
            }
            for service, amount in service_data.items()
        ]
        # sort total amount from higher to lower
        result.sort(key=lambda x: x['amount'], reverse=True)

        return {
            'total_revenue': round(total, 2),
            'data': result,
        }

    # ─── TREND LINE CHART ─────────────────────────────────────
    @api.model
    def get_booking_trend(self, period='month'):
        domain = self._get_period_domain(period)
        bookings = self.env['booking.request'].search(domain, order='preferred_date asc')

        trend = {}
        for b in bookings:
            if b.preferred_date:
                key = b.preferred_date.strftime('%b %d')
                trend[key] = trend.get(key, 0) + 1

        return {'data': [{'date': k, 'count': v} for k, v in trend.items()]}

    # ─── TOP CLEANERS ─────────────────────────────────────────
    @api.model
    def get_top_cleaners(self, period='month'):
        domain = self._get_period_domain(period) + [('state', '=', 'approved')]
        bookings = self.env['booking.request'].sudo().search(domain)

        cleaners = {}
        for b in bookings:
            name = b.individual_id.name if b.individual_id else (
                b.cleaning_team_id.name if b.cleaning_team_id else None
            )
            if name:
                cleaners[name] = cleaners.get(name, 0) + 1

        sorted_cleaners = sorted(cleaners.items(), key=lambda x: x[1], reverse=True)[:7]
        return [{'name': k, 'count': v} for k, v in sorted_cleaners]
