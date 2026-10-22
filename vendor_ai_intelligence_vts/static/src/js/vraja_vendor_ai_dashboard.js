/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { proxy, signal, onMounted, onPatched, onWillStart, onWillUnmount } from "@odoo/owl";
import { loadBundle } from "@web/core/assets";
import { VrajaAIDashboard } from "@vraja_ai/js/dashboard_client_action";

const DEFAULT_CARD = {
    id: false,
    vraja_common_card_name: "",
    ai_vendor_company_information: "",
    ai_vendor_procurement_process: "",
    ai_vendor_forecast_period: "all_data",
    ai_vendor_forecast_days: 30,
    ai_vendor_instruction: "",
    ai_vendor_default_prompt: "",
    ai_vendor_analysis_result: "",
    ai_vendor_analysis_error: "",
    ai_vendor_attachment_id: false,
    ai_vendor_analyzed_on: false,
    ai_vendor_auto_analyze: false,
};

export class VendorAIDashboard extends VrajaAIDashboard {
    chartRef = signal.ref();

    setup() {
        super.setup();

        this.orm = useService("orm");
        this.notification = useService("notification");

        this.state = proxy({
            ...this.state,
            isBusy: false,
            currentWizardStep: 0,
            card: { ...DEFAULT_CARD },
            parsedAIResult: null,
            vendorLimit: 5,
        });

        this.chartInstance = null;

        onWillStart(() => loadBundle("web.chartjs_lib"));

        onMounted(async () => {
            await this.loadVendorCardData();
        });

        onPatched(() => {
            if (this.state.parsedAIResult && this.chartRef()) {
                this.renderChart();
            }
        });

        onWillUnmount(() => {
            if (this.chartInstance) {
                this.chartInstance.destroy();
                this.chartInstance = null;
            }
        });
    }

    onChangeVendorLimit(ev) {
        this.state.vendorLimit = parseInt(ev.target.value, 10);
        this.renderChart();
    }

    normalizeAIResult(result) {
        const toArray = (val) => {
            if (Array.isArray(val)) return val;
            if (val && typeof val === 'object') return [val];
            return [];
        };
        return {
            executive_summary: result.executive_summary || "",
            worst_delays: toArray(result.worst_delays),
            fastest_delivery: toArray(result.fastest_delivery),
            best_rates: toArray(result.best_rates),
            category_kings: Array.isArray(result.category_kings) ? result.category_kings : [],
            top_vendors: Array.isArray(result.top_vendors) ? result.top_vendors : [],
            red_flags: Array.isArray(result.red_flags) ? result.red_flags : [],
            action_plan: Array.isArray(result.action_plan) ? result.action_plan : [],
        };
    }

    renderChart() {
        if (!window.Chart) {
            console.error("Vendor AI: Chart.js is not loaded");
            return;
        }
        if (!this.chartRef()) return;

        if (this.chartInstance) {
            this.chartInstance.destroy();
            this.chartInstance = null;
        }

        const ctx = this.chartRef().getContext("2d");
        const allVendors = this.state.parsedAIResult.top_vendors || [];
        const vendors = allVendors.slice(0, this.state.vendorLimit);

        const colorPalette = [
            'rgba(68, 114, 196, 0.8)',   // Blue
            'rgba(237, 125, 49, 0.8)',   // Orange
            'rgba(165, 165, 165, 0.8)',  // Gray
            'rgba(255, 192, 0, 0.8)',    // Yellow
            'rgba(91, 155, 213, 0.8)',   // Light Blue
            'rgba(112, 173, 71, 0.8)',   // Green
            'rgba(38, 68, 120, 0.8)',    // Dark Blue
            'rgba(158, 72, 14, 0.8)',    // Dark Orange
            'rgba(99, 99, 99, 0.8)',     // Dark Gray
            'rgba(153, 115, 0, 0.8)',    // Dark Yellow
            'rgba(155, 89, 182, 0.8)',   // Purple
            'rgba(231, 76, 60, 0.8)',    // Red
            'rgba(26, 188, 156, 0.8)'    // Turquoise
        ];

        const backgroundColors = vendors.map((v, index) => colorPalette[index % colorPalette.length]);

        try {
        this.chartInstance = new window.Chart(ctx, {
            type: 'pie',
            data: {
                labels: vendors.map(v => v.name || v.vendor || 'Unknown Vendor'),
                datasets: [{
                    label: 'Overall AI Score',
                    data: vendors.map(v => v.score || 0),
                    backgroundColor: backgroundColors,
                    borderWidth: 1,
                    hoverOffset: 4
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        display: true,
                        position: 'right'
                    }
                }
            }
        });
        } catch (e) {
            console.error("Vendor AI: chart creation failed", e);
        }
    }

    async loadCardStore() {
        await super.loadCardStore();
        if (this.state.store === "ai_vendor_intel" || !this.state.cardId) {
            await this.ensureVendorCardId();
        }
        if (this.state.store === "ai_vendor_intel" && this.state.cardId) {
            await this.loadVendorCardData();
        }
    }

    async ensureVendorCardId() {
        if (this.state.cardId) return;
        const cards = await this.orm.searchRead('vraja.ai.card', [['vraja_common_store', '=', 'ai_vendor_intel']], ['id', 'vraja_common_store']);
        if (cards.length > 0) {
            this.state.cardId = cards[0].id;
            this.state.store = cards[0].vraja_common_store;
        } else {
            this.state.cardId = await this.orm.call('vraja.ai.card', 'action_ai_vendor_get_default_card_id', []);
        }
    }

    async loadVendorCardData() {
        if (!this.state.cardId) return;
        try {
            const data = await this.orm.read('vraja.ai.card', [this.state.cardId], Object.keys(DEFAULT_CARD));
            if (data.length > 0) {
                const cardData = data[0];
                this.state.card = {
                    ...this.state.card,
                    ...cardData,
                    ai_vendor_attachment_id: cardData.ai_vendor_attachment_id ? cardData.ai_vendor_attachment_id[0] : false
                };

                if (cardData.ai_vendor_analysis_result) {
                    try {
                        let text = cardData.ai_vendor_analysis_result.replace(/```json/g, '').replace(/```/g, '').trim();
                        this.state.parsedAIResult = this.normalizeAIResult(JSON.parse(text));
                        if (this.state.currentWizardStep <= 1) {
                            this.state.currentWizardStep = 5;
                        }
                    } catch(e) {
                        console.warn("Could not parse AI result as JSON:", e);
                        this.state.parsedAIResult = null;
                    }
                } else {
                    this.state.parsedAIResult = null;
                }
            }
        } catch (e) {
            console.error(e);
        }
    }

    async onClickGenerateData() {
        this.state.isBusy = true;
        try {
            // The backend recomputes scores using the card period settings before exporting.
            await this.orm.call('vraja.ai.card', 'generate_ai_vendor_file', [[this.state.cardId]]);

            // Reload Data
            await this.loadVendorCardData();

            this.notification.add("Scores updated and Workbook generated successfully", { type: "success" });
            this.onNextStep();
        } catch (e) {
            this.notification.add("Failed to generate vendor data", { type: "danger" });
        } finally {
            this.state.isBusy = false;
        }
    }

    onNextStep() {
        if (this.state.currentWizardStep < 5) {
            this.state.currentWizardStep++;
        }
    }

    onPrevStep() {
        if (this.state.currentWizardStep > 1) {
            this.state.currentWizardStep--;
        }
    }

    async onChangeField(field, ev) {
        const value = ev.target.value;
        this.state.card[field] = value;
        if (this.state.card.id) {
            await this.orm.write("vraja.ai.card", [this.state.card.id], { [field]: value });
        }
    }

    async onChangeBooleanField(field, ev) {
        const value = ev.target.checked;
        this.state.card[field] = value;
        if (this.state.card.id) {
            await this.orm.write("vraja.ai.card", [this.state.card.id], { [field]: value });
        }
    }

    async onClickReRunAI() {
        if (!this.state.card.id) return;
        this.state.isBusy = true;
        try {
            await this.orm.write("vraja.ai.card", [this.state.card.id], { ai_vendor_analysis_result: false });
            this.state.card.ai_vendor_analysis_result = false;
            this.state.parsedAIResult = null;
            this.state.currentWizardStep = 1;
        } catch (e) {
            console.error("Failed to clear analysis result", e);
        } finally {
            this.state.isBusy = false;
        }
    }

    async onClickRunAI() {
        this.state.isBusy = true;
        try {
            await this.orm.call("vraja.ai.card", "action_run_vendor_ai_analysis", [[this.state.cardId]]);
            await this.loadVendorCardData();

            if (this.state.card.ai_vendor_analysis_error) {
                this.notification.add("AI analysis finished with an error.", { type: "warning" });
            } else {
                this.notification.add("Vendor AI analysis completed.", { type: "success" });
                this.onNextStep();
            }
        } catch (e) {
            this.notification.add("Failed to run AI", { type: "danger" });
        } finally {
            this.state.isBusy = false;
        }
    }
}

VendorAIDashboard.template = "vraja_ai_dashboard_template";

registry.category("actions").add(
    "vendor_ai_intelligence_dashboard_template",
    VendorAIDashboard
);