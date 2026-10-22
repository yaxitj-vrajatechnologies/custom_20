/** @odoo-module **/

import {registry} from "@web/core/registry";
import {user} from "@web/core/user";
import {onMounted, onPatched, proxy} from "@odoo/owl";
import {useService} from "@web/core/utils/hooks";
import {VrajaAIDashboard} from "@vraja_ai/js/dashboard_client_action";

// ── Formatters ────────────────────────────────────────────────────────────────
function formatCurrency(value, compact = false, symbol = "$") {
    if (value === undefined || value === null) return `${symbol}0`;
    const abs = Math.abs(value);
    const sign = value < 0 ? "-" : "";
    if (compact) {
        if (abs >= 1e7) return `${sign}${symbol}${(abs / 1e7).toFixed(1)}Cr`;
        if (abs >= 1e5) return `${sign}${symbol}${(abs / 1e5).toFixed(1)}L`;
        if (abs >= 1e3) return `${sign}${symbol}${(abs / 1e3).toFixed(1)}K`;
        return `${sign}${symbol}${abs.toFixed(0)}`;
    }
    return new Intl.NumberFormat("en-US", {
        style: "currency", currency: "USD",
        minimumFractionDigits: 0, maximumFractionDigits: 0,
    }).format(value).replace("$", symbol);
}

function formatDate(dateStr) {
    if (!dateStr) return "—";
    try {
        const d = new Date(dateStr);
        return d.toLocaleDateString("en-US", {year: "numeric", month: "short", day: "numeric"});
    } catch {
        return dateStr;
    }
}

function formatDateShort(dateStr) {
    if (!dateStr) return "—";
    try {
        const d = new Date(dateStr);
        return d.toLocaleDateString("en-US", {month: "short", day: "numeric"});
    } catch {
        return dateStr;
    }
}

// ── Main Dashboard Component ──────────────────────────────────────────────────
export class VrajaCashflowDashboard extends VrajaAIDashboard {

    setup() {
        super.setup();

        this.cfFmt = {
            currency: (v) => formatCurrency(v, false, this.sym),
            compact: (v) => formatCurrency(v, true, this.sym),
            date: formatDate,
            dateShort: formatDateShort,
        };
        this.agingTotal = this.agingTotal.bind(this);
        this.agingPct = this.agingPct.bind(this);

        this.orm = useService("orm");
        this.notification = useService("notification");
        this.action = useService("action");

        const today = new Date();
        const prev = new Date();
        prev.setMonth(today.getMonth() - 2);
        const fmtDate = (d) => d.toISOString().split("T")[0];

        const savedCardId = parseInt(sessionStorage.getItem("vraja_ai_card_id") || "0") || null;
        const savedCompanyId = parseInt(sessionStorage.getItem("vraja_ai_company_id") || "0") || null;
        const parentState = this.state || {};
        const actionParams = this.props?.action?.params || {};

        this.state = proxy({
            ...parentState,
            cardId: this.props?.cardId || actionParams.card_id || parentState.cardId || savedCardId,
            companyId: this.props?.companyId || actionParams.company_id || parentState.companyId || savedCompanyId,
            dateFrom: fmtDate(prev),
            dateTo: fmtDate(today),
            additionalInfo: "",
            isGenerating: false,
            analysis: null,
            activePanel: 1,
            foldedSections: JSON.parse(localStorage.getItem("vraja_cf_folded") || "{}"),
            cfoUserId: null,
            cfoSelected: "",   // string value bound to the <select> (survives re-renders)
            cfoEmail: "",
            cfoLoading: false,
            usersList: [],
            companiesList: [],
        });

        onMounted(async () => {
            if (this.state.cardId) {
                sessionStorage.setItem("vraja_ai_card_id", String(this.state.cardId));
            }
            console.log("[CashflowAI] mounted", {
                cardId: this.state.cardId,
                companyId: this.state.companyId,
                store: this.state.store,
            });
            await this.resolveCardId();
            await Promise.all([
                this.loadCompanies(),
                this.loadUsersList(),
            ]);

            await this.loadLatestAnalysis();
            if (this.state.cardId) {
                await this.loadCfoData();
            } else {
                console.warn("[CashflowAI] no cardId found, saved CFO not loaded");
            }
            this.syncCfoSelect();
        });

        onPatched(() => {
            this.syncCfoSelect();
            if (this.state.companyId) {
                sessionStorage.setItem("vraja_ai_company_id", String(this.state.companyId));
            }
        });
    }

    syncCfoSelect() {
        const el = document.querySelector(".cf-cfo-select");
        if (!el) return;
        const wanted = this.state.cfoSelected || "";
        if (el.value !== wanted) {
            el.value = wanted;
        }
    }

    // ── Find the cashflow card id even when the action params were lost ──────
    async resolveCardId() {
        if (this.state.cardId) return this.state.cardId;
        const candidates = [];
        const ctx = this.props?.action?.context || {};
        const params = this.props?.action?.params || {};
        candidates.push(params.card_id, ctx.active_id, ctx.default_card_id, this.props?.action?.params?.active_id);
        candidates.push(parseInt(sessionStorage.getItem("vraja_ai_card_id") || "0") || null);
        // URL looks like /odoo/action-93/8/vraja_cashflow_dashboard
        const m = window.location.pathname.match(/action-[^/]+\/(\d+)/);
        if (m) candidates.push(parseInt(m[1], 10));
        const ids = [...new Set(candidates.filter(Boolean).map(Number))];
        try {
            if (ids.length) {
                const found = await this.orm.searchRead(
                    "vraja.ai.card",
                    [["id", "in", ids], ["vraja_common_store", "=", "cashflow"]],
                    ["id"], {limit: 1}
                );
                if (found.length) return this._setCardId(found[0].id);
            }
            // Last resort: the cashflow card of the current company.
            const any = await this.orm.searchRead(
                "vraja.ai.card", [["vraja_common_store", "=", "cashflow"]],
                ["id"], {limit: 1, order: "id asc"}
            );
            if (any.length) return this._setCardId(any[0].id);
        } catch (e) {
            console.error("[CashflowAI] resolveCardId failed:", e);
        }
        return null;
    }

    _setCardId(id) {
        this.state.cardId = id;
        sessionStorage.setItem("vraja_ai_card_id", String(id));
        return id;
    }

    async loadCardStore() {
        // On browser refresh the action params are lost, so restore the card id
        // BEFORE the parent runs (it needs it) and again after it.
        if (!this.state.cardId) {
            const saved = sessionStorage.getItem("vraja_ai_card_id");
            if (saved) this.state.cardId = parseInt(saved);
        }
        await super.loadCardStore();
        if (!this.state.cardId) {
            const saved = sessionStorage.getItem("vraja_ai_card_id");
            if (saved) this.state.cardId = parseInt(saved);
        }
        if (this.state.cardId) {
            sessionStorage.setItem("vraja_ai_card_id", String(this.state.cardId));
            // This component only ever serves the cashflow dashboard, so do not
            // let a lost "store" value (refresh) stop the data from loading.
            if (!this.state.store) {
                this.state.store = "cashflow";
            }
        }
    }

    get sym() {
        return this.state.analysis?.currency || "$";
    }

    // ── Quick date range buttons ─────────────────────────────────────────────
    setDateRange(months) {
        const today = new Date();
        const from = new Date();
        from.setMonth(today.getMonth() - months);
        const f = (d) => d.toISOString().split("T")[0];
        this.state.dateFrom = f(from);
        this.state.dateTo = f(today);
    }

    // ── Panel switching ──────────────────────────────────────────────────────
    setPanel(n) {
        this.state.activePanel = n;
    }

    // ── Load latest saved analysis on mount ──────────────────────────────────
    async loadLatestAnalysis() {
        try {
            const fields = ["id", "date_from", "date_to", "additional_info", "company_id", "card_id"];
            const base = [["state", "=", "done"]];
            const cardDom = this.state.cardId ? [["card_id", "=", this.state.cardId]] : [];
            const compDom = this.state.companyId ? [["company_id", "=", this.state.companyId]] : [];

            // 1st: exact match (card + company). 2nd: same card, any company.
            // If the card id itself is unknown (lost on refresh) the card filter is
            // simply left out, so the latest saved analysis is still found.
            const attempts = [[...base, ...cardDom, ...compDom]];
            if (compDom.length) attempts.push([...base, ...cardDom]);

            let result = [];
            for (const domain of attempts) {
                result = await this.orm.searchRead(
                    "vraja.cashflow.analysis", domain, fields,
                    {limit: 1, order: "generated_on desc"}
                );
                console.log("[CashflowAI] saved analyses found:", result.length, JSON.stringify(domain));
                if (result.length) break;
            }
            if (result.length > 0) {
                // Re-sync ids from the saved record itself
                const recCard = Array.isArray(result[0].card_id) ? result[0].card_id[0] : result[0].card_id;
                const recCompany = Array.isArray(result[0].company_id) ? result[0].company_id[0] : result[0].company_id;
                if (recCard) {
                    this.state.cardId = recCard;
                    sessionStorage.setItem("vraja_ai_card_id", String(recCard));
                }
                if (recCompany) {
                    this.state.companyId = recCompany;
                    sessionStorage.setItem("vraja_ai_company_id", String(recCompany));
                }
                this.state.dateFrom = result[0].date_from;
                this.state.dateTo = result[0].date_to;
                this.state.additionalInfo = result[0].additional_info || "";

                this.state.isGenerating = true;
                const data = await this.orm.call(
                    "vraja.cashflow.analysis", "generate_analysis",
                    [{
                        date_from: this.state.dateFrom,
                        date_to: this.state.dateTo,
                        card_id: this.state.cardId,
                        company_id: this.state.companyId,
                        additional_info: this.state.additionalInfo,
                    }]
                );
                this.state.isGenerating = false;

                if (data.state !== "error") {
                    this.state.analysis = data;
                } else {
                    console.error("loadLatestAnalysis: backend returned error:", data.error);
                    this.notification.add(
                        `Could not load the saved analysis: ${data.error || "unknown error"}`,
                        {type: "danger"}
                    );
                }
            }
        } catch (e) {
            console.error("loadLatestAnalysis error:", e);
            this.state.isGenerating = false;
            this.notification.add(
                e.data?.message || e.message || "Could not load the saved analysis.",
                {type: "danger"}
            );
        }
    }

    // ── Generate (always force-reruns fresh AI — no cache served) ─────────────
    async onGenerate() {
        if (!this.state.dateFrom || !this.state.dateTo) {
            this.notification.add("Please select both From and To dates.", {type: "warning"});
            return;
        }
        if (!this.state.cardId) {
            await this.resolveCardId();
        }
        this.state.isGenerating = true;
        this.state.analysis = null;
        try {
            const data = await this.orm.call(
                "vraja.cashflow.analysis", "force_generate_analysis",
                [{
                    date_from: this.state.dateFrom,
                    date_to: this.state.dateTo,
                    card_id: this.state.cardId,
                    company_id: this.state.companyId,
                    additional_info: this.state.additionalInfo || "",
                }]
            );
            if (data.state === "error") {
                this.notification.add(`Analysis failed: ${data.error}`, {type: "danger"});
            } else {
                this.state.analysis = data;
                this.state.additionalInfo = data.additional_info || "";
                // Re-sync the saved CFO recipient so the dropdown / status
                // always reflect what is stored on the card.
                await this.loadCfoData();
                this.notification.add("Cashflow intelligence generated successfully.", {type: "success"});
            }
        } catch (error) {
            this.notification.add(error.data?.message || error.message || "Failed to generate analysis.", {type: "danger"});
        } finally {
            this.state.isGenerating = false;
        }
    }

    // ── Toggle section fold ───────────────────────────────────────────────────
    toggleSection(name) {
        this.state.foldedSections[name] = !this.state.foldedSections[name];
        localStorage.setItem("vraja_cf_folded", JSON.stringify(this.state.foldedSections));
    }

    // ── CFO Report: users for the dropdown (independent of the card) ─────────
    async loadUsersList() {
        let users = [];
        const attempts = [
            ["backend method", () => this.orm.call("vraja.ai.card", "get_internal_users_list", [])],
            ["internal users", () => this.orm.searchRead(
                "res.users", [["share", "=", false]], ["id", "name", "email"],
                {order: "name asc", limit: 200})],
            ["all users", () => this.orm.searchRead(
                "res.users", [], ["id", "name", "email"],
                {order: "name asc", limit: 200})],
        ];
        for (const [label, run] of attempts) {
            try {
                users = await run();
                console.log(`[CashflowAI] users via ${label}:`, users ? users.length : 0);
            } catch (e) {
                console.error(`[CashflowAI] users via ${label} failed:`, e);
                users = [];
            }
            if (users && users.length) break;
        }
        this.state.usersList = users || [];
        if (!this.state.usersList.length) {
            this.notification.add(
                "Could not load users for the CFO Report Recipient list. See browser console.",
                {type: "warning"}
            );
        }
    }

    // ── CFO Report: currently saved CFO for this card ────────────────────────
    async loadCfoData() {
        if (!this.state.cardId) return;
        try {
            const cfo = await this.orm.call(
                "vraja.ai.card", "get_cfo_user_for_card", [this.state.cardId]
            );
            if (cfo) {
                this.state.cfoUserId = cfo.id;
                this.state.cfoSelected = String(cfo.id);
                this.state.cfoEmail = cfo.email;
            } else {
                this.state.cfoUserId = null;
                this.state.cfoSelected = "";
                this.state.cfoEmail = "";
            }
        } catch (e) {
            console.error("Cashflow AI: Failed to load saved CFO user:", e);
        }
    }

    // ── Load selectable companies + default to current user company ───────────
    async loadCompanies() {
        try {
            const companies = await this.orm.searchRead(
                "res.company", [], ["id", "name"], {order: "name asc"}
            );
            this.state.companiesList = companies;
            if (!this.state.companyId) {
                const companyId =
                    user.activeCompany?.id ||
                    user.context?.allowed_company_ids?.[0] ||
                    (companies[0] && companies[0].id);
                this.state.companyId = companyId || null;
            }
        } catch (e) {
            console.error("loadCompanies error:", e);
        }
    }

    // ── CFO Report: save selection when dropdown changes ──────────────────────
    async onCfoUserChange(ev) {
        const rawVal = ev.target.value;
        const userId = rawVal ? parseInt(rawVal, 10) : null;
        // Remember the last saved value so the dropdown can be reverted on error.
        const previousSelected = this.state.cfoUserId ? String(this.state.cfoUserId) : "";

        if (!this.state.cardId) {
            await this.resolveCardId();
        }
        if (!this.state.cardId) {
            this.state.cfoSelected = previousSelected;
            this.notification.add(
                "Dashboard card not found. Please reopen the dashboard from the card.",
                {type: "warning"}
            );
            return;
        }

        this.state.cfoLoading = true;
        try {
            await this.orm.call(
                "vraja.ai.card", "set_cfo_user_for_card",
                [this.state.cardId, userId || false]
            );
            this.state.cfoUserId = userId;
            this.state.cfoSelected = userId ? String(userId) : "";
            if (userId) {
                const found = this.state.usersList.find(u => u.id === userId);
                this.state.cfoEmail = found ? found.email : "";
                this.notification.add(
                    `CFO report will be sent to ${found ? found.name : "selected user"} every night.`,
                    {type: "success"}
                );
            } else {
                this.state.cfoEmail = "";
                this.notification.add(
                    "CFO report has been disabled for this dashboard.",
                    {type: "info"}
                );
            }
        } catch (e) {
            this.state.cfoSelected = previousSelected;
            this.notification.add("Failed to save CFO user. Please try again.", {type: "danger"});
            console.error("Cashflow AI: set_cfo_user_for_card error:", e);
        } finally {
            this.state.cfoLoading = false;
        }
    }

    // ── Aging helpers ─────────────────────────────────────────────────────────
    agingTotal(aging) {
        if (!aging) return 0;
        return (aging.current || 0) + (aging.d1_30 || 0) + (aging.d31_60 || 0) +
            (aging.d61_90 || 0) + (aging.d91_180 || 0) + (aging.d180_plus || 0);
    }

    agingPct(amount, total) {
        if (!total) return 0;
        return Math.min(100, Math.round((amount / total) * 100));
    }

    // ── Daily forecast chart (SVG polyline) ──────────────────────────────────
    getDailyForecastSVG() {
        const W = 700, H = 160, PAD = {top: 10, right: 10, bottom: 30, left: 60};
        const data = this.state.analysis?.daily_forecast;
        if (!data || !data.length) return {
            balanceLine: "", inBars: [], outBars: [],
            yLabels: [], xLabels: [], minY: 0, maxY: 0,
            W, H, PAD, zeroY: H / 2
        };

        const chartW = W - PAD.left - PAD.right;
        const chartH = H - PAD.top - PAD.bottom;
        const n = data.length;

        const balances = data.map(d => d.projected_balance);
        const inflows = data.map(d => d.expected_inflow);
        const outflows = data.map(d => d.expected_outflow);

        const allVals = [...balances, ...inflows.map(v => -v)];
        let minY = Math.min(...allVals);
        let maxY = Math.max(...allVals, 0);
        const padding = (maxY - minY) * 0.1 || 1000;
        minY -= padding;
        maxY += padding;

        const xScale = (i) => PAD.left + (i / (n - 1)) * chartW;
        const yScale = (v) => PAD.top + chartH - ((v - minY) / (maxY - minY)) * chartH;

        const balanceLine = balances.map((v, i) => `${xScale(i)},${yScale(v)}`).join(" ");
        const bw = Math.max(2, (chartW / n) * 0.35);

        const inBars = data.map((d, i) => ({
            x: xScale(i) - bw,
            y: yScale(d.expected_inflow),
            h: Math.max(0, yScale(0) - yScale(d.expected_inflow)),
            w: bw,
        }));
        const outBars = data.map((d, i) => ({
            x: xScale(i),
            y: yScale(0),
            h: Math.max(0, yScale(-d.expected_outflow) - yScale(0)),
            w: bw,
        }));

        const yLabels = [];
        for (let i = 0; i <= 4; i++) {
            const v = minY + ((maxY - minY) / 4) * i;
            yLabels.push({y: yScale(v), text: formatCurrency(v, true, this.sym)});
        }

        const xLabels = data.filter((_, i) => i % 5 === 0 || i === n - 1).map((d) => {
            const idx = data.indexOf(d);
            return {x: xScale(idx), text: formatDateShort(d.date)};
        });

        return {balanceLine, inBars, outBars, yLabels, xLabels, minY, maxY, W, H, PAD, zeroY: yScale(0)};
    }

    // ── Monthly trend SVG ─────────────────────────────────────────────────────
    getMonthlyTrendSVG() {
        const data = this.state.analysis?.monthly_surplus;
        if (!data || !data.length) return null;

        const W = 500, H = 130, PAD = {top: 10, right: 10, bottom: 25, left: 55};
        const chartW = W - PAD.left - PAD.right;
        const chartH = H - PAD.top - PAD.bottom;
        const n = data.length;

        const inVals = data.map(d => d.inflow);
        const outVals = data.map(d => d.outflow);
        const netVals = data.map(d => d.net);

        const allVals = [...inVals, ...outVals, ...netVals, 0];
        let minY = Math.min(...allVals);
        let maxY = Math.max(...allVals);
        const pad = (maxY - minY) * 0.1 || 1000;
        minY -= pad;
        maxY += pad;

        const xs = (i) => PAD.left + (n > 1 ? (i / (n - 1)) * chartW : chartW / 2);
        const ys = (v) => PAD.top + chartH - ((v - minY) / (maxY - minY)) * chartH;

        return {
            W, H, PAD,
            zeroY: ys(0),
            inLine: inVals.map((v, i) => `${xs(i)},${ys(v)}`).join(" "),
            outLine: outVals.map((v, i) => `${xs(i)},${ys(v)}`).join(" "),
            netLine: netVals.map((v, i) => `${xs(i)},${ys(v)}`).join(" "),
            xLabels: data.map((d, i) => ({x: xs(i), text: (d.label || d.month).slice(0, 6)})),
        };
    }

    // ── AR Aging donut data ───────────────────────────────────────────────────
    getArAgingDonut() {
        const ag = this.state.analysis?.ar_aging;
        if (!ag) return [];
        const total = this.agingTotal(ag);
        if (!total) return [];
        const segments = [
            {label: "0–30 Days", value: ag.d1_30 || 0, color: "#4ade80"},
            {label: "31–60 Days", value: ag.d31_60 || 0, color: "#facc15"},
            {label: "61–90 Days", value: ag.d61_90 || 0, color: "#f97316"},
            {label: "90+ Days", value: (ag.d91_180 || 0) + (ag.d180_plus || 0), color: "#ef4444"},
        ];
        let cumPct = 0;
        return segments.map(s => {
            const pct = total ? (s.value / total) * 100 : 0;
            const start = cumPct;
            cumPct += pct;
            return {...s, pct: Math.round(pct), startPct: start};
        });
    }

    // ── Drill-Down helpers ────────────────────────────────────────────────────
    drillDownAR(bucket = null) {
        const today = new Date();
        const f = (d) => d.toISOString().split("T")[0];
        const sub = (days) => {
            const d = new Date(today);
            d.setDate(today.getDate() - days);
            return d;
        };
        const base = [
            ["move_type", "=", "out_invoice"], ["state", "=", "posted"],
            ["payment_state", "not in", ["paid", "reversed"]],
            ["invoice_date", ">=", this.state.dateFrom], ["invoice_date", "<=", this.state.dateTo]
        ];
        const bucketMap = {
            current: {
                name: "Receivables — Not Yet Due",
                extra: ["|", ["invoice_date_due", ">=", f(today)], ["invoice_date_due", "=", false]]
            },
            d1_30: {
                name: "Receivables — 1-30 Days Overdue",
                extra: [["invoice_date_due", ">=", f(sub(30))], ["invoice_date_due", "<", f(today)]]
            },
            d31_60: {
                name: "Receivables — 31-60 Days Overdue",
                extra: [["invoice_date_due", ">=", f(sub(60))], ["invoice_date_due", "<", f(sub(30))]]
            },
            d61_90: {
                name: "Receivables — 61-90 Days Overdue",
                extra: [["invoice_date_due", ">=", f(sub(90))], ["invoice_date_due", "<", f(sub(60))]]
            },
            d91_180: {
                name: "Receivables — 91-180 Days Overdue",
                extra: [["invoice_date_due", ">=", f(sub(180))], ["invoice_date_due", "<", f(sub(90))]]
            },
            d180_plus: {name: "Receivables — 180+ Days Overdue", extra: [["invoice_date_due", "<", f(sub(180))]]},
        };
        const cfg = bucketMap[bucket] || {name: "All Open Receivables", extra: []};
        this.action.doAction({
            type: "ir.actions.act_window",
            name: cfg.name,
            res_model: "account.move",
            domain: [...base, ...cfg.extra],
            views: [[false, "list"], [false, "form"]],
            target: "current"
        });
    }

    drillDownAP(bucket = null) {
        const today = new Date();
        const f = (d) => d.toISOString().split("T")[0];
        const sub = (days) => {
            const d = new Date(today);
            d.setDate(today.getDate() - days);
            return d;
        };
        const base = [
            ["move_type", "=", "in_invoice"], ["state", "=", "posted"],
            ["payment_state", "not in", ["paid", "reversed"]],
            ["invoice_date", ">=", this.state.dateFrom], ["invoice_date", "<=", this.state.dateTo]
        ];
        const bucketMap = {
            current: {
                name: "Payables — Not Yet Due",
                extra: ["|", ["invoice_date_due", ">=", f(today)], ["invoice_date_due", "=", false]]
            },
            d1_30: {
                name: "Payables — 1-30 Days Overdue",
                extra: [["invoice_date_due", ">=", f(sub(30))], ["invoice_date_due", "<", f(today)]]
            },
            d31_60: {
                name: "Payables — 31-60 Days Overdue",
                extra: [["invoice_date_due", ">=", f(sub(60))], ["invoice_date_due", "<", f(sub(30))]]
            },
            d61_90: {
                name: "Payables — 61-90 Days Overdue",
                extra: [["invoice_date_due", ">=", f(sub(90))], ["invoice_date_due", "<", f(sub(60))]]
            },
            d91_180: {
                name: "Payables — 91-180 Days Overdue",
                extra: [["invoice_date_due", ">=", f(sub(180))], ["invoice_date_due", "<", f(sub(90))]]
            },
            d180_plus: {name: "Payables — 180+ Days Overdue", extra: [["invoice_date_due", "<", f(sub(180))]]},
        };
        const cfg = bucketMap[bucket] || {name: "All Open Payables", extra: []};
        this.action.doAction({
            type: "ir.actions.act_window",
            name: cfg.name,
            res_model: "account.move",
            domain: [...base, ...cfg.extra],
            views: [[false, "list"], [false, "form"]],
            target: "current"
        });
    }

    drillDownExpenses() {
        this.action.doAction({
            type: "ir.actions.act_window", name: "Pending Employee Expenses",
            res_model: "hr.expense",
            domain: [["state", "in", ["submitted", "approved", "posted"]], ["payment_mode", "=", "own_account"], ["date", ">=", this.state.dateFrom], ["date", "<=", this.state.dateTo]],
            views: [[false, "list"], [false, "form"]], target: "current"
        });
    }

    drillDownSO() {
        this.action.doAction({
            type: "ir.actions.act_window", name: "Sales Orders — Pending Invoice",
            res_model: "sale.order",
            domain: [["state", "=", "sale"], ["invoice_status", "=", "to invoice"], ["date_order", ">=", this.state.dateFrom], ["date_order", "<=", this.state.dateTo]],
            views: [[false, "list"], [false, "form"]], target: "current"
        });
    }

    drillDownPO() {
        this.action.doAction({
            type: "ir.actions.act_window", name: "Purchase Orders — Pending Billing",
            res_model: "purchase.order",
            domain: [["state", "in", ["purchase", "done"]], ["invoice_status", "=", "to invoice"], ["date_order", ">=", this.state.dateFrom], ["date_order", "<=", this.state.dateTo]],
            views: [[false, "list"], [false, "form"]], target: "current"
        });
    }

    async onPrintReport() {
        if (!this.state.analysis?.analysis_id) return;
        await this.action.doAction({
            type: "ir.actions.report",
            report_type: "qweb-pdf",
            report_name: "vraja_cashflow_ai.report_cashflow_analysis",
            report_file: "vraja_cashflow_ai.report_cashflow_analysis",
            context: {active_ids: [this.state.analysis.analysis_id]},
        });
    }
}

VrajaCashflowDashboard.template = "vraja_cashflow_ai.CashflowDashboardTemplate";
registry.category("actions").add("vraja_cashflow_dashboard", VrajaCashflowDashboard);