/** @odoo-module **/

import {registry} from "@web/core/registry";
import {useService} from "@web/core/utils/hooks";
import {proxy, onMounted} from "@odoo/owl";
import {VrajaAIDashboard} from "@vraja_ai/js/dashboard_client_action";

const CARD_FIELDS = [
    "id",
    "vraja_common_store",
    "vraja_common_card_name",
    "minimum_stock_threshold",
    "forecast_period",
    "sale_forecast_days",
    "purchase_forecast_period",
    "purchase_forecast_days",
    "ai_low_stock_auto_create_rfq",
    "ai_low_stock_company_information",
    "ai_low_stock_instruction",
    "ai_low_stock_default_prompt",
    "ai_low_stock_analysis_result",
    "ai_low_stock_analysis_error",
    "ai_low_stock_attachment_id",
    "ai_low_stock_analyzed_on",
];

const NUMERIC_FIELDS = new Set([
    "minimum_stock_threshold",
    "sale_forecast_days",
    "purchase_forecast_days",
]);

const DEFAULT_CARD = {
    id: false,
    minimum_stock_threshold: 0,
    forecast_period: "all_data",
    sale_forecast_days: 30,
    purchase_forecast_period: "all_data",
    purchase_forecast_days: 30,
    ai_low_stock_auto_create_rfq: false,
    vraja_common_card_name: "",
    ai_low_stock_company_information: "",
    ai_low_stock_instruction: "",
    ai_low_stock_default_prompt: "",
    ai_low_stock_analysis_result: "",
    ai_low_stock_analysis_error: "",
    ai_low_stock_attachment_id: false,
    stock_attachment_name: "",
    ai_low_stock_analyzed_on: false,
};

export class InventoryDashboard extends VrajaAIDashboard {

    setup() {
        super.setup();

        this.orm = useService("orm");
        this.notification = useService("notification");
        this.actionService = useService("action");

        /*
            EXTEND STATE
        */
        this.state = proxy({
            ...this.state,

            isBusy: false,
            currentWizardStep: 0,
            currentPage: 1,
            recordsPerPage: 5,
            searchProduct: "",
            card: {...DEFAULT_CARD},
        });

        onMounted(async () => {
            await this.loadInventoryCardData();
        });
    }

    /**
     * Reads vraja_common_store for the current card.
     * On page refresh cardId may be missing — falls back to searching by store type.
     */
    async loadCardStore() {
        await super.loadCardStore();
        if (this.state.store === "ai_low_stock" || !this.state.cardId) {
            await this.ensureInventoryCardId();
        }
        if (this.state.store === "ai_low_stock" && this.state.cardId) {
            await this.loadInventoryCardData();
        }
    }

     /** Fetch the default forecast card id when route params are unavailable. */
    async ensureInventoryCardId() {
        if (this.state.cardId) {
            return;
        }
        const cards = await this.orm.searchRead(
                'vraja.ai.card',
                [['vraja_common_store', '=', 'ai_low_stock']],
                ['id', 'vraja_common_store'],
                {limit: 1}
            );
        if (cards.length) {
            this.state.cardId = cards[0].id;
            this.state.store = cards[0].vraja_common_store;
        }
    }

    onNextPage() {
        const totalPages = this.getTotalPages();

        if (this.state.currentPage < totalPages) {
            this.state.currentPage++;
        }
    }

    onPrevPage() {
        if (this.state.currentPage > 1) {
            this.state.currentPage--;
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

    getTotalPages() {
        const totalRecords = this.getFilteredProductAIResults().length;
        return Math.ceil(
            totalRecords / this.state.recordsPerPage
        ) || 1;
    }

    getPaginatedLowStockResults() {
        const results = this.getFilteredProductAIResults();

        const start =
            (this.state.currentPage - 1)
            * this.state.recordsPerPage;

        const end =
            start + this.state.recordsPerPage;

        return results.slice(start, end);
    }

    /*
        LOAD CARD DETAILS
    */
    async loadInventoryCardData() {

        if (!this.state.cardId) {
            return;
        }

        const [card] = await this.orm.read(
            "vraja.ai.card",
            [this.state.cardId],
            CARD_FIELDS
        );

        this.state.store = card?.vraja_common_store || false;
        this.state.card = this.normalizeCard(card);

        this.updateDynamicPrompt();
    }

    normalizeCard(card = {}) {
        return {
            ...DEFAULT_CARD,
            ...card,
            ai_low_stock_attachment_id: card.ai_low_stock_attachment_id?.[0] || false,
            stock_attachment_name: card.ai_low_stock_attachment_id?.[1] || "",
            ai_low_stock_auto_create_rfq: Boolean(card.ai_low_stock_auto_create_rfq),
            ai_low_stock_analysis_result: card.ai_low_stock_analysis_result || "",
            ai_low_stock_analysis_error: card.ai_low_stock_analysis_error || "",
        };
    }

    /*
        UPDATE PROMPT LIVE
    */
    updateDynamicPrompt() {

        const forecastPeriod = this.state.card.forecast_period || "all_data";
        const saleForecastDays = this.state.card.sale_forecast_days || 0;
        const purchaseForecastPeriod = this.state.card.purchase_forecast_period || "all_data";
        const purchaseForecastDays = this.state.card.purchase_forecast_days || 0;

        const salesForecastText = forecastPeriod === "selected_data"
            ? `Use recent sales rows for approximately ${saleForecastDays} days.`
            : "Use the available sales history in the workbook.";

        const purchaseForecastText = purchaseForecastPeriod === "selected_data"
            ? `Use recent purchase rows for approximately ${purchaseForecastDays} days.`
            : "Use the available purchase history in the workbook.";

        this.state.card.ai_low_stock_default_prompt = `
Review the uploaded inventory workbook. It contains stock, sales, purchase, and vendor pricelist sheets.

Configuration:
- Minimum stock threshold: ${this.state.card.minimum_stock_threshold || 0}
- Sales forecast mode: ${forecastPeriod}
- ${salesForecastText}
- Purchase history mode: ${purchaseForecastPeriod}
- ${purchaseForecastText}

Task:
- Use product_id and product_sku from the workbook when matching rows.
- Use available_stock from the stock sheet as provided.
- Estimate average_daily_sales from the sales sheet.
- Estimate forecasted_demand for the selected sales period.
- Recommend a purchase quantity when forecasted_demand is greater than available_stock.
- Select a vendor using purchase history signals such as lead time, delay, reliability, and price.
- Vendor selection priority for every product:
  1. If the product has rows in the Purchase Data sheet, choose the vendor with the lowest average_received_lead_time_days (fastest delivery; ignore vendors where it is blank). If two vendors have the same average_received_lead_time_days, choose the vendor with the highest total_purchase_orders for that product.
  2. If the product has no rows in the Purchase Data sheet, choose the vendor from the Vendor Pricelist sheet (vendor_priority 1 first).
  3. Use vendor_id and vendor exactly as given in the workbook, and always fill recommended_vendor_id and recommended_vendor when a vendor exists.
- Include rows only when a purchase RFQ is recommended.

Return CSV text with this exact header:
product_id,product,product_sku,recommended_vendor_id,recommended_vendor,available_stock,forecasted_demand,recommended_order_qty,decision,reason

For recommended rows, set decision to CREATE_RFQ.
Return plain CSV text only, without markdown formatting.
`;
    }

    async onChangeCheckbox(fieldName, ev) {

        this.state.card[fieldName] = ev.target.checked;

        if (this.state.card.id) {
            await this.orm.write(
                "vraja.ai.card",
                [this.state.card.id],
                {
                    [fieldName]: this.state.card[fieldName],
                }
            );
        }

        this.updateDynamicPrompt();
    }

    /*
        ON CHANGE VALUE
    */
    async onChangeField(field, ev) {

        const value = NUMERIC_FIELDS.has(field)
            ? Number(ev.target.value || 0)
            : ev.target.value;
        this.state.card[field] = value;

        if (!this.state.card.id) {
            return;
        }

        // SAVE INTO DATABASE
        await this.orm.write(
            "vraja.ai.card",
            [this.state.card.id],
            {
                [field]: value,
            }
        );
        this.updateDynamicPrompt();
    }

    /*
        GENERATE EXCEL FILE
    */
    async onClickGenerateFile() {
        this.state.isBusy = true;

        try {
            await this.orm.call(
                "vraja.ai.card",
                "generate_ai_inventory_file",
                [[this.state.cardId]]
            );

            await this.loadInventoryCardData();
            this.notification.add(
                "Inventory data file generated successfully.",
                {
                    type: "success",
                }
            );
            this.onNextStep();
        } finally {
            this.state.isBusy = false;
        }
    }

    /*
        RUN AI ANALYSIS
    */
    async onClickRunAI() {
        this.state.isBusy = true;

        try {
            /*
            ALWAYS GENERATE LATEST PROMPT
            */
            this.updateDynamicPrompt();

            /*
                SAVE LATEST GENERATED PROMPT
            */
            await this.orm.write(
                "vraja.ai.card",
                [this.state.card.id],
                {
                    ai_low_stock_default_prompt:
                        this.state.card.ai_low_stock_default_prompt,

                    ai_low_stock_instruction:
                        this.state.card.ai_low_stock_instruction,

                    minimum_stock_threshold:
                        this.state.card.minimum_stock_threshold,

                    forecast_period:
                        this.state.card.forecast_period,

                    sale_forecast_days:
                        this.state.card.sale_forecast_days,

                    purchase_forecast_period:
                        this.state.card.purchase_forecast_period,

                    purchase_forecast_days:
                        this.state.card.purchase_forecast_days,

                    ai_low_stock_auto_create_rfq:
                        this.state.card.ai_low_stock_auto_create_rfq,

                    ai_low_stock_company_information:
                        this.state.card.ai_low_stock_company_information,
                }
            );

            await this.orm.call(
                "vraja.ai.card",
                "action_run_inventory_ai_analysis",
                [[this.state.cardId]]
            );

            await this.loadInventoryCardData();
            const type = this.state.card.ai_low_stock_analysis_error ? "warning" : "success";
            this.notification.add(
                this.state.card.ai_low_stock_analysis_error
                    ? "AI analysis finished with an error. Review the dashboard details."
                    : "Inventory AI analysis completed.",
                {type}
            );
            if (!this.state.card.ai_low_stock_analysis_error) {
                this.onNextStep();
            }
        } finally {
            this.state.isBusy = false;
        }
    }

    /*
    CREATE RFQ FROM AI RESPONSE
    */
    async onClickCreateRFQ() {

        try {

            const action = await this.orm.call(
                "vraja.ai.card",
                "action_create_rfq",
                [[this.state.cardId]]
            );

            this.notification.add("RFQ created successfully.", {type: "success"});

            /*
                OPEN CREATED RFQ LIST VIEW
            */
            this.actionService.doAction(action);

        } catch (error) {

            // Odoo RPC errors always have message "Odoo Server Error";
            // the real server message is in error.data.message
            this.notification.add(
                error?.data?.message || error?.message || "Failed to Create RFQ",
                {
                    type: "danger",
                }
            );
        }
    }

    /*
    PARSE AI RESPONSE
    */
    getParsedAIResult() {
        try {
            const parsed = JSON.parse(
                this.state.card.ai_low_stock_analysis_result || "[]"
            );
            return Array.isArray(parsed) ? parsed : [];

        } catch {

            return [];
        }
    }

    /* Search & filter Record */

    onSearchProduct(ev) {
        this.state.searchProduct = ev.target.value.toLowerCase();
        this.state.currentPage = 1;
    }

    getFilteredProductAIResults() {
        const p = this.state.searchProduct;
        const results = this.getParsedAIResult();
        if (!p) return results;
        return results.filter(r =>
            (r.product || '').toLowerCase().includes(p) ||
            (r.product_sku || '').toLowerCase().includes(p) ||
            (r.recommended_vendor || '').toLowerCase().includes(p) ||
            String(r.product_id || "").includes(p)
        );
    }

    getDashboardStats() {
        const records = this.getParsedAIResult();
        const totalQty = records.reduce(
            (sum, record) => sum + Number(record.recommended_order_qty || 0),
            0
        );
        const vendorIds = new Set(
            records
                .map((record) => record.recommended_vendor_id || record.recommended_vendor)
                .filter(Boolean)
        );

        return {
            recommendations: records.length,
            totalQty,
            vendors: vendorIds.size,
            analyzedOn: this.state.card.ai_low_stock_analyzed_on || "Not analyzed",
        };
    }
}

/*
    USE SAME TEMPLATE
*/
InventoryDashboard.template = "vraja_ai_dashboard_template";

/*
    Register a dedicated inventory action so this dashboard does not compete
    with other modules that also extend the common Vraja AI template.
*/
registry.category("actions").add(
    "inventory_low_stock_dashboard_template",
    InventoryDashboard
);