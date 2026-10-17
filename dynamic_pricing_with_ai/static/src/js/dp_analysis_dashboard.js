/** @odoo-module **/

import {Component, onMounted, onWillUnmount, proxy} from "@odoo/owl";
import {registry} from "@web/core/registry";
import {useService} from "@web/core/utils/hooks";

export class DynamicPricingAnalysisDashboard extends Component {
    setup() {
        this.orm = useService("orm");

        this.state = proxy({
            cardId: this.props.action?.params?.card_id,
            loading: true,
            error: "",
            data: {},
            activeTab: "impact",        // impact | products | segments | history | alerts
            productSearch: "",
            impactSearch: "",
            impactFilter: "all",        // all | increase | decrease | hold | skip
        });
        this.actionService = useService("action");
        this.state.activeView = 'card';
        this.requestSeq = 0;
        this.moneyFormatter = null;
        this.numberFormatter = new Intl.NumberFormat(undefined, {maximumFractionDigits: 2});

        onMounted(async () => {
            this.enableDashboardScroll();
            await this.loadDashboard();
        });

        onWillUnmount(() => {
            this.restoreDashboardScroll();
        });
    }

    goBack() {
        this.actionService.doAction({
            type: 'ir.actions.client',
            tag: 'dynamic_pricing_dashboard_template',
            target: 'current',
        });
    }

    toggleView() {
        this.state.activeView = this.state.activeView === 'card' ? 'list' : 'card';
    }

    enableDashboardScroll() {
        const selectors = [".o_content", ".o_action_manager", ".o_view_controller", ".o_action"];
        this._scrollTargets = [];
        selectors.forEach(sel => {
            const el = document.querySelector(sel);
            if (el) {
                this._scrollTargets.push({
                    el,
                    prevOverflow: el.style.overflowY,
                    prevHeight: el.style.height,
                    prevMinHeight: el.style.minHeight
                });
                el.style.overflowY = "visible";
                el.style.height = "auto";
                el.style.minHeight = "unset";
            }
        });
        const appRoot = document.querySelector(".o_web_client") || document.body;
        this._appRoot = appRoot;
        this._prevAppOverflow = appRoot.style.overflowY;
        appRoot.style.overflowY = "auto";
        this._prevBodyOverflow = document.body.style.overflowY;
        document.body.style.overflowY = "auto";
    }

    restoreDashboardScroll() {
        (this._scrollTargets || []).forEach(({el, prevOverflow, prevHeight, prevMinHeight}) => {
            el.style.overflowY = prevOverflow || "";
            el.style.height = prevHeight || "";
            el.style.minHeight = prevMinHeight || "";
        });
        if (this._appRoot) this._appRoot.style.overflowY = this._prevAppOverflow || "";
        document.body.style.overflowY = this._prevBodyOverflow || "";
    }

    async loadDashboard() {
        const requestId = ++this.requestSeq;
        if (!this.state.cardId) {
            await this.ensureCardId();
            if (!this.state.cardId) {
                this.state.error = "Dynamic pricing card was not found.";
                this.state.loading = false;
                return;
            }
        }
        this.state.loading = true;
        this.state.error = "";
        try {
            const data = await this.orm.call(
                "vraja.ai.card",
                "action_get_dp_analysis_dashboard_data",
                [this.state.cardId]
            );
            if (requestId === this.requestSeq) {
                this.state.data = data;
                this.moneyFormatter = null;
            }
        } catch (error) {
            if (requestId === this.requestSeq) {
                this.state.error = error?.data?.message || error?.message || String(error);
            }
        } finally {
            if (requestId === this.requestSeq) this.state.loading = false;
        }
    }

    async ensureCardId() {
        try {
            const cardId = await this.orm.call("vraja.ai.card", "action_dp_get_default_card_id", []);
            if (cardId) this.state.cardId = cardId;
        } catch (error) {
            this.state.error = error?.data?.message || error?.message || String(error);
        }
    }

    setTab(tab) {
        this.state.activeTab = tab;
    }

    setImpactFilter(f) {
        this.state.impactFilter = f;
        this.state.impactSearch = "";
    }

    // ── Data getters ──────────────────────────────────────────────────────────
    get card() {
        return this.state.data.card || {};
    }

    get summary() {
        return this.state.data.summary || {};
    }

    get alerts() {
        return this.state.data.alerts || {};
    }

    get segmentData() {
        return this.state.data.segment_data || [];
    }

    get allProductRows() {
        return this.state.data.product_rows || [];
    }

    get totalAlerts() {
        const a = this.alerts;
        return (a.negative_margin?.length || 0) + (a.dead_stock?.length || 0) +
            (a.out_of_stock?.length || 0) + (a.overstock?.length || 0);
    }

    // AI Impact rows — products with actual AI price change (not hold/skip)
    get aiImpactRows() {
        let rows = this.allProductRows.filter(r => r.ai_price_active);
        const q = (this.state.impactSearch || "").toLowerCase();
        const f = this.state.impactFilter;
        if (f === "increase") rows = rows.filter(r => r.decision === "increase");
        if (f === "decrease") rows = rows.filter(r => r.decision === "decrease");
        if (f === "hold") rows = rows.filter(r => r.decision === "hold");
        if (f === "skip") rows = rows.filter(r => r.decision === "skip");
        if (q) rows = rows.filter(r =>
            (r.product_name || "").toLowerCase().includes(q) ||
            (r.segment || "").toLowerCase().includes(q)
        );
        return rows;
    }

    // All product rows with optional search
    get filteredProductRows() {
        const q = (this.state.productSearch || "").toLowerCase();
        if (!q) return this.allProductRows;
        return this.allProductRows.filter(r =>
            (r.product_name || "").toLowerCase().includes(q) ||
            (r.segment || "").toLowerCase().includes(q) ||
            (r.category || "").toLowerCase().includes(q)
        );
    }

    // ── Formatters ────────────────────────────────────────────────────────────
    formatMoney(value) {
        if (!this.moneyFormatter) {
            this.moneyFormatter = new Intl.NumberFormat(undefined, {
                style: "currency",
                currency: this.state.data.currency || "USD",
                maximumFractionDigits: 2,
            });
        }
        return this.moneyFormatter.format(value || 0);
    }

    formatNumber(value) {
        return this.numberFormatter.format(value || 0);
    }

    formatPct(value) {
        const v = value || 0;
        return (v > 0 ? "+" : "") + v.toFixed(2) + "%";
    }

    // ── CSS helpers ───────────────────────────────────────────────────────────
    marginClass(value) {
        if (value < 0) return "dpad-negative";
        if (value < 15) return "dpad-warning";
        return "dpad-positive";
    }

    deltaClass(value) {
        if ((value || 0) > 0) return "dpad-positive";
        if ((value || 0) < 0) return "dpad-negative";
        return "dpad-neutral";
    }

    stockBadgeClass(status) {
        return {
            out_of_stock: "dpad-stock-badge dpad-stock-badge--out",
            low_stock: "dpad-stock-badge dpad-stock-badge--low",
            in_stock: "dpad-stock-badge dpad-stock-badge--in",
            overstock: "dpad-stock-badge dpad-stock-badge--over",
        }[status] || "dpad-stock-badge";
    }

    stockLabel(status) {
        return {
            out_of_stock: "Out of Stock",
            low_stock: "Low Stock",
            in_stock: "In Stock",
            overstock: "Overstock",
        }[status] || status;
    }

    decisionClass(decision) {
        return `dpad-decision dpad-decision--${decision || "hold"}`;
    }

    decisionIcon(decision) {
        return {
            increase: "arrow_upward",
            decrease: "arrow_downward",
            hold: "remove",
            skip: "block",
        }[decision] || "remove";
    }

    runStatusClass(status) {
        return status === "success" ? "dpad-run-success" : "dpad-run-failed";
    }

    hasAlert(row, flag) {
        return row.alert_flags && row.alert_flags.includes(flag);
    }
}

DynamicPricingAnalysisDashboard.template = "dynamic_pricing_analysis_dashboard_template";
registry.category("actions").add("dynamic_pricing_analysis_dashboard", DynamicPricingAnalysisDashboard);
