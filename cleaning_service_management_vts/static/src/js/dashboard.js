/** @odoo-module **/

import {registry} from "@web/core/registry";
import {Component, onWillStart, useState, useRef, onMounted} from "@odoo/owl";
import {useService} from "@web/core/utils/hooks";

class BookingDashboard extends Component {
    setup() {
        this.orm = useService("orm");
        this.action = useService("action");

        this.revenueChartRef = useRef("revenueChart");
        this.statusChartRef = useRef("statusChart");
        this.trendChartRef = useRef("trendChart");

        this.revenueChart = null;
        this.statusChart = null;
        this.trendChart = null;

        const savedPeriod = localStorage.getItem('dashboard_period') || 'month';

        this.state = useState({
            title: "Booking Dashboard",
            period: savedPeriod,
            serviceStats: [],
            topCleaners: [],
            revenue: {data: []},
            trend: {data: []},
            data: {
                draft: 0,
                under_review: 0,
                approved: 0,
                rejected: 0,
                total: 0,
                total_revenue: 0,
            },
        });

        onWillStart(async () => await this.loadAll());
        onMounted(async () => await this.renderAllCharts());
    }

    async loadAll() {
        try {
            const period = this.state.period;

            // All ORM calls in parallel
            const [kpis, serviceStats, revenue, trend, topCleaners,] =
                await Promise.all([
                    this.orm.call("booking.dashboard", "get_dashboard_data", [], {period}),
                    this.orm.call("booking.dashboard", "get_service_analysis", [], {period}),
                    this.orm.call("booking.dashboard", "get_service_revenue_distribution", [], {period}),
                    this.orm.call("booking.dashboard", "get_booking_trend", [], {period}),
                    this.orm.call("booking.dashboard", "get_top_cleaners", [], {period}),
                ]);

            this.state.data = kpis || this.state.data;
            this.state.serviceStats = serviceStats || [];
            this.state.revenue = revenue || {data: []};
            this.state.trend = trend || {data: []};
            this.state.topCleaners = topCleaners || [];

        } catch (err) {
            console.error("Dashboard load error:", err);
        }
    }

    async renderAllCharts() {
        await new Promise(requestAnimationFrame);
        this.renderRevenueChart();
        this.renderStatusChart();
        this.renderTrendChart();
    }

    async onChangePeriod(ev) {
        this.state.period = ev.target.value;
        localStorage.setItem('dashboard_period', this.state.period);
        await this.loadAll();
        await this.renderAllCharts();
    }

    openBookings(status) {
        const domain = [...(this.state.data.domain || [])];
        if (status) domain.push(['state', '=', status]);

        this.action.doAction({
            type: "ir.actions.act_window",
            name: "Bookings Requests",
            res_model: "booking.request",
            view_mode: "list,form",
            views: [[false, "list"], [false, "form"]],
            domain,
            target: "current",
        });
    }

    openServiceBookings(serviceName) {
        this.action.doAction({
            type: "ir.actions.act_window",
            name: "Service Bookings",
            res_model: "booking.request",
            view_mode: "list,form",
            views: [[false, "list"], [false, "form"]],
            domain: [["service_type_id.name", "=", serviceName]],
            target: "current",
        });
    }

    // ─── CHARTS ────
    _destroyChart(ref) {
        if (ref) {
            ref.destroy();
            ref = null;
        }
        return null;
    }

    renderRevenueChart() {
        const canvas = this.revenueChartRef.el;
        if (!canvas || !window.Chart) return;
        this.revenueChart = this._destroyChart(this.revenueChart);

        const data = this.state.revenue?.data || [];
        this.revenueChart = new window.Chart(canvas, {
            type: "bar",
            data: {
                labels: data.map(d => d.service),
                datasets: [{
                    label: "Revenue (%)",
                    data: data.map(d => d.percent),
                    backgroundColor: "#4e73df",
                    borderRadius: 6
                }]
            },
            options: {responsive: true, maintainAspectRatio: false, scales: {y: {beginAtZero: true, max: 100}}}
        });
    }

    renderStatusChart() {
        const canvas = this.statusChartRef.el;
        if (!canvas || !window.Chart) return;
        this.statusChart = this._destroyChart(this.statusChart);

        const d = this.state.data;
        this.statusChart = new window.Chart(canvas, {
            type: "doughnut",
            data: {
                labels: ["New Request", "Under Review", "Approved", "Rejected"],
                datasets: [{
                    data: [d.draft, d.under_review, d.approved, d.rejected],
                    backgroundColor: ["#858796", "#f6c23e", "#1cc88a", "#e74a3b"],
                }]
            },
            options: {
                responsive: true, maintainAspectRatio: false, cutout: "70%",
                plugins: {legend: {position: "bottom"}}
            }
        });
    }

    renderTrendChart() {
        const canvas = this.trendChartRef.el;
        if (!canvas || !window.Chart) return;
        this.trendChart = this._destroyChart(this.trendChart);

        const data = this.state.trend?.data || [];
        this.trendChart = new window.Chart(canvas, {
            type: "line",
            data: {
                labels: data.map(d => d.date),
                datasets: [{
                    label: "Bookings",
                    data: data.map(d => d.count),
                    borderColor: "#1cc88a",
                    backgroundColor: "rgba(28,200,138,0.1)",
                    fill: true,
                    tension: 0.4,
                }]
            },
            options: {responsive: true, maintainAspectRatio: false, scales: {y: {beginAtZero: true}}}
        });
    }
}

BookingDashboard.template = "cleaning_service_management_vts.booking_dashboard_template";
registry.category("actions").add("booking_dashboard", BookingDashboard);