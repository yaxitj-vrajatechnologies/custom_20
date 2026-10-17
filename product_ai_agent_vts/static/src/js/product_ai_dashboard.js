/** @odoo-module **/

import {registry} from "@web/core/registry";
import {onMounted, onWillUnmount} from "@odoo/owl";
import {VrajaAIDashboard} from "@vraja_ai/js/dashboard_client_action";

class ProductAIAgentDashboard extends VrajaAIDashboard {

    // ─────────────────────────────────────────────────────────────────────────
    // SETUP
    // ─────────────────────────────────────────────────────────────────────────

    setup() {
        super.setup();

        // Product-specific state on top of base state
        this.state.ready = false;
        this.state.productData = null;
        this.state.loading = false;
        this.state.message = '';
        this.state.messageType = '';
        this.state.selectedProducts = [];
        this.state.selectedProductMap = {};
        this.state.productSearch = '';
        this.state.productDropdown = [];
        this.state.showDropdown = false;
        this.state.skuFilename = '';
        this.state.skuUploadMessage = '';
        this.state.skuUploadMessageType = 'success';
        this.state.useSalesHistory = true;
        this.state.useCategory = true;
        this.state.step6Search = '';
        this.state.step6Page = 1;

        this.state.suggestionType = '';
        this.state.minConfidence = '';


        this._outsideClickHandler = (ev) => {
            const el = document.getElementById("product_ai_product_selector");
            if (el && !el.contains(ev.target)) {
                this.state.showDropdown = false;
            }
        };

        onMounted(async () => {
            document.addEventListener('mousedown', this._outsideClickHandler);
            document.body.style.overflowY = "auto";
            const root = document.querySelector(".o_content");
            if (root) {
                root.style.overflowY = "auto";
                root.style.height = "100vh";
            }
        });

        onWillUnmount(() => {
            document.removeEventListener('mousedown', this._outsideClickHandler);
        });
    }

    // ─────────────────────────────────────────────────────────────────────────
    // INITIALISATION HELPERS
    // ─────────────────────────────────────────────────────────────────────────

    /** Load card store and initialize product dashboard data. */
    /** Load the selected card store and recover product AI context after refresh. */
    async loadCardStore() {
        await super.loadCardStore();
        if (this.state.store === 'product_alt_acc' || !this.state.cardId) {
            await this.ensureProductCardId();
        }
        if (this.state.store === 'product_alt_acc' && this.state.cardId) {
            await this.loadProductAIDashboardData();
            this.loadSelectedProducts();
            this.state.useSalesHistory = this.state.productData?.product_ai_use_sales_history ?? true;
            this.state.suggestionType = this.state.productData?.product_ai_suggestion_type || '';
            this.state.minConfidence = this.state.productData?.product_ai_min_confidence || '';

        }
        this.state.ready = true;
    }

    /** Fetch the default product AI card id when route params are unavailable. */
    async ensureProductCardId() {
        if (this.state.cardId) {
            return;
        }
        const cardId = await this.orm.call(
            'vraja.ai.card',
            'action_product_ai_get_default_card_id',
            []
        );
        if (cardId) {
            this.state.cardId = cardId;
            this.state.store = 'product_alt_acc';
        }
    }

    // ─────────────────────────────────────────────────────────────────────────
    // DATA LOADING
    // ─────────────────────────────────────────────────────────────────────────

    /** Loads all saved card settings and AI results from Python. */
    async loadProductAIDashboardData() {
        if (!this.state.cardId) return;
        try {
            this.state.productData = await this.orm.call(
                'vraja.ai.card',
                'action_get_product_ai_dashboard_data',
                [this.state.cardId]
            );
        } catch (e) {
            console.error('Failed to load product AI data:', e);
        }
    }

    /** Restores selected product tag pills from productData. */
    loadSelectedProducts() {
        const products = this.state.productData?.selected_products || [];
        this.state.selectedProducts = products.map(p => ({id: p.id, name: p.name}));
        const map = {};
        products.forEach(p => {
            map[p.id] = true;
        });
        this.state.selectedProductMap = map;
    }

    _fillSelects() {
        if (!this.state.productData) return;
        const d = this.state.productData;
        setTimeout(() => {
            const setSelect = (id, val) => {
                const el = document.getElementById(id);
                if (el && val !== undefined && val !== null) el.value = val;
            };
            setSelect('product_ai_suggestion_type', d.product_ai_suggestion_type);
            setSelect('product_ai_min_confidence', d.product_ai_min_confidence);
        }, 0);
    }

    // ─────────────────────────────────────────────────────────────────────────
// STEP NAVIGATION
// ─────────────────────────────────────────────────────────────────────────

    goToStep(currentId, targetId) {
        const current = document.querySelector(currentId);
        const target = document.querySelector(targetId);

        if (current && current.classList.contains('show')) {
            current.classList.remove('show');
        }

        if (target) {
            target.classList.add('show');
            setTimeout(() => {
                target.closest('.card')?.scrollIntoView({behavior: 'smooth', block: 'start'});
            }, 100);
        }
    }


    // ─────────────────────────────────────────────────────────────────────────
    // MANY2MANY PRODUCT SELECTOR
    // ─────────────────────────────────────────────────────────────────────────

    /** Fires on every keystroke — live ilike search. */
    async onProductSearchInput(ev) {
        const query = ev.target.value;
        this.state.productSearch = query;
        if (!query.trim()) {
            this.state.productDropdown = [];
            this.state.showDropdown = false;
            return;
        }
        const excludeIds = this.state.selectedProducts.map(p => p.id);
        this.state.productDropdown = await this.orm.searchRead(
            'product.template',
            [
                ['active', '=', true],
                ['sale_ok', '=', true],
                ['name', 'ilike', query],
                ['id', 'not in', excludeIds],
            ],
           ['id', 'name'],
            {limit: 80}
        );
        this.state.showDropdown = this.state.productDropdown.length > 0;
    }

    /** Opens dropdown on focus. */
    async onProductSearchFocus() {
        if (this.state.productDropdown.length) {
            this.state.showDropdown = true;
            return;
        }
        const excludeIds = this.state.selectedProducts.map(p => p.id);
        this.state.productDropdown = await this.orm.searchRead(
            'product.template',
               [['active', '=', true], ['sale_ok', '=', true], ['id', 'not in', excludeIds]],
            ['id', 'name'],
            {limit: 80}
        );
        this.state.showDropdown = this.state.productDropdown.length > 0;
    }

    // ── Select All Product ──────────────────────────────────────────────
    async onSelectAllProducts() {
        console.log("SELECT ALL CLICKED", this);
        try {
            await this._onSelectAllProductsInner();
        } catch (e) {
            console.error("SELECT ALL ERROR", e);
            this._showMessage("Select All error: " + (e?.data?.message || e?.message || String(e)), 'danger');
        }
    }

    async _onSelectAllProductsInner() {
        if (this.state.selectedProducts.length) {
            // Deselect all
            this.state.selectedProducts = [];
            this.state.selectedProductMap = {};
            this.state.showDropdown = false;
            await this._autoSaveProducts();
        } else {
            // Select all
            const allProducts = await this.orm.searchRead('product.template', [['active', '=', true], ['sale_ok', '=', true]], ['id', 'name'], {limit: 100000});
            const map = {};
            allProducts.forEach(p => {
                map[p.id] = true;
            });
            this.state.selectedProducts = allProducts.map(p => ({id: p.id, name: p.name}));
            this.state.selectedProductMap = map;
            this.state.showDropdown = false;
            await this._autoSaveProducts();
        }
    }


    /** Toggles product checkbox. */
    async onToggleProductCheckbox(product) {
        const map = {...this.state.selectedProductMap};
        if (map[product.id]) {
            delete map[product.id];
            this.state.selectedProducts = this.state.selectedProducts.filter(p => p.id !== product.id);
        } else {
            map[product.id] = true;
            this.state.selectedProducts = [...this.state.selectedProducts, product];
        }
        this.state.selectedProductMap = {...map};
        this.state.showDropdown = true;
        await this._autoSaveProducts();
    }

    /** Removes a tag pill. */
    async onRemoveProduct(productId) {
        const map = {...this.state.selectedProductMap};
        delete map[productId];
        this.state.selectedProductMap = map;
        this.state.selectedProducts = this.state.selectedProducts.filter(p => p.id !== productId);
        await this._autoSaveProducts();
    }

    onSalesHistoryToggle(ev) {
        this.state.useSalesHistory = ev.target.checked;
    }

    onSuggestionTypeChange(ev) {
        this.state.suggestionType = ev.target.value;
    }

    onMinConfidenceChange(ev) {
        this.state.minConfidence = ev.target.value;
    }

    async onBusinessInfoBlur(ev) {
        const value = ev.target.value;
        await this.orm.call(
            'vraja.ai.card',
            'action_save_product_ai_dashboard_data',
            [this.state.cardId, {product_ai_business_info: value}]
        );
    }

    async _autoSaveProducts() {
        await this.orm.call(
            'vraja.ai.card',
            'action_save_product_ai_dashboard_data',
            [this.state.cardId, {
                product_ai_selected_product_ids: this.state.selectedProducts.map(p => p.id)
            }]
        );
    }

    // ─────────────────────────────────────────────────────────────────────────
    // SKU FILE UPLOAD
    // ─────────────────────────────────────────────────────────────────────────

    async onSKUFileUpload(ev) {
        const file = ev.target.files[0];
        if (!file) return;
        this.state.skuFilename = file.name;

        if (!this.state.cardId) {
            this.state.skuUploadMessage = "Card not loaded yet. Please refresh and try again.";
            this.state.skuUploadMessageType = "danger";
            return;
        }

        try {
            const base64 = await new Promise((resolve, reject) => {
                const reader = new FileReader();
                reader.onload = () => {
                    const result = reader.result;
                    const commaIndex = result.indexOf(",");
                    if (commaIndex === -1) {
                        reject(new Error("Failed to read file as base64."));
                        return;
                    }
                    resolve(result.substring(commaIndex + 1));
                };
                reader.onerror = () => reject(new Error("FileReader error"));
                reader.readAsDataURL(file);
            });

            const result = await this.orm.call(
                "vraja.ai.card",
                "action_import_products_from_sku_file",
                [this.state.cardId, base64, file.name]
            );

            if (result.products && result.products.length) {
                // Replace existing selection completely (do not append)
                const replacedProducts = result.products.map((p) => ({id: p.id, name: p.name}));
                const replacedMap = {};
                result.products.forEach((p) => {
                    replacedMap[p.id] = true;
                });

                this.state.selectedProducts = replacedProducts;
                this.state.selectedProductMap = replacedMap;

                this.state.skuUploadMessage =
                    `${result.products.length} product(s) replaced from file.` +
                    (result.not_found.length
                        ? ` ${result.not_found.length} SKU(s) not found: ${result.not_found.join(", ")}`
                        : "");
                this.state.skuUploadMessageType = "success";

                await this.orm.call(
                    "vraja.ai.card",
                    "action_save_product_ai_dashboard_data",
                    [this.state.cardId, {
                        // (6, 0, ids) behavior in backend will replace M2M
                        product_ai_selected_product_ids: this.state.selectedProducts.map((p) => p.id),
                    }]
                );
            } else {
                // If no matched products, clear existing selection (replace with empty)
                this.state.selectedProducts = [];
                this.state.selectedProductMap = {};

                await this.orm.call(
                    "vraja.ai.card",
                    "action_save_product_ai_dashboard_data",
                    [this.state.cardId, {product_ai_selected_product_ids: []}]
                );

                this.state.skuUploadMessage = `No matching products found. Not found SKUs: ${result.not_found.join(", ")}`;
                this.state.skuUploadMessageType = "danger";
            }

            ev.target.value = "";
        } catch (e) {
            this.state.skuUploadMessage = "Upload failed: " + (e?.data?.message || e?.message || String(e));
            this.state.skuUploadMessageType = "danger";
        }
    }

    async onDownloadSKUTemplate() {
        try {
            const result = await this.orm.call('vraja.ai.card', 'action_download_sku_template', []);
            const filename = result?.filename || 'sku_template.xlsx';
            const b64 = result?.file_data;
            if (!b64) throw new Error('Template content is empty.');
            const bytes = atob(b64);
            const arr = new Uint8Array(bytes.length);
            for (let i = 0; i < bytes.length; i++) {
                arr[i] = bytes.charCodeAt(i);
            }
            const blob = new Blob([arr], {type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'});
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = filename;
            document.body.appendChild(a);
            a.click();
            a.remove();
            URL.revokeObjectURL(url);
        } catch (e) {
            this.state.skuUploadMessage = 'Template download failed: ' + (e?.data?.message || e?.message || String(e));
            this.state.skuUploadMessageType = 'danger';
        }
    }

    // ===================================================================================================================================


    // ─────────────────────────────────────────────────────────────────────────
    // FLASH MESSAGE
    // ─────────────────────────────────────────────────────────────────────────

    /**
     * Shows a temporary bootstrap alert. Auto-clears after 4 seconds.
     */
    _showMessage(msg, type = 'success') {
        this.state.message = msg;
        this.state.messageType = type;
        setTimeout(() => {
            this.state.message = '';
            this.state.messageType = '';
        }, 4000);
    }

    // ─────────────────────────────────────────────────────────────────────────
    // AI RESULT HELPERS
    // ─────────────────────────────────────────────────────────────────────────

    /**
     * Parses product_ai_result_json into a flat array for the Step 6 results table.
     * Returns: [{product_id, alternatives: [], accessories: []}, ...]
     */
    getAIResults() {
        if (!this.state.productData?.product_ai_result_json) return [];
        try {
            return Object.entries(
                JSON.parse(this.state.productData.product_ai_result_json)
            ).map(([pid, data]) => ({
                product_id: pid,
                product_name: data.product_name || pid,
                alternatives: data.alternatives || [],
                accessories: data.accessories || [],
            }));
        } catch {
            return [];
        }
    }

    // ── Step 6 search and filter ──────────────────────────────────────────────

    onStep6Search(ev) {
        this.state.step6Page = 1;
        this.state.step6Search = ev.target.value.toLowerCase();
    }

    getPagedAIResults() {
        const s = (this.state.step6Page - 1) * 10;
        return this.getFilteredAIResults().slice(s, s + 10);
    }

    getTotalPages() {
        return Math.max(1, Math.ceil(this.getFilteredAIResults().length / 10));
    }

    onStep6PageChange(page) {
        const total = this.getTotalPages();
        if (page >= 1 && page <= total) this.state.step6Page = page;
    }

    getPageNumbers() {
        const total = this.getTotalPages(), cur = this.state.step6Page, pages = [];
        if (total <= 7) {
            for (let i = 1; i <= total; i++) pages.push(i);
        } else {
            pages.push(1);
            if (cur > 3) pages.push("...");
            for (let i = Math.max(2, cur - 1); i <= Math.min(total - 1, cur + 1); i++) pages.push(i);
            if (cur < total - 2) pages.push("...");
            pages.push(total);
        }
        return pages;
    }

    getFilteredAIResults() {
        const q = this.state.step6Search;
        const results = this.getAIResults();
        if (!q) return results;
        return results.filter(r =>
            (r.product_name || '').toLowerCase().includes(q) ||
            String(r.product_id).includes(q)
        );
    }


    // ─────────────────────────────────────────────────────────────────────────
    // ACTIONS
    // ─────────────────────────────────────────────────────────────────────────

    /**
     * Saves all form values to the card and regenerates the Excel preview file.
     */
    async onProductAISave() {
        const getEl = (id) => document.getElementById(id);
        const getVal = (id, fb) => getEl(id)?.value || fb;
        const getChk = (id) => getEl(id)?.checked || false;

        const values = {
            product_ai_business_info: getVal('product_ai_business_info', ''),
            product_ai_suggestion_type: this.state.suggestionType,
            product_ai_min_confidence: this.state.minConfidence,
            product_ai_price_tolerance: parseFloat(getVal('product_ai_price_tolerance', 15)),
            product_ai_max_suggestions: parseInt(getVal('product_ai_max_suggestions', 5)),
            product_ai_sales_history_days: parseInt(getVal('product_ai_sales_history_days', 30)),
            product_ai_auto_apply: getChk('product_ai_auto_apply'),

            product_ai_use_category: getChk('product_ai_use_category'),
            product_ai_use_tags: getChk('product_ai_use_tags'),
            product_ai_use_price: getChk('product_ai_use_price'),
            product_ai_use_attributes: getChk('product_ai_use_attributes'),
            product_ai_use_sales_history: this.state.useSalesHistory,

            // Send raw IDs — Python wraps into [(6, 0, ids)]
            product_ai_selected_product_ids: this.state.selectedProducts.map(p => p.id),
        };

        try {
            this.state.loading = true;
            await this.orm.call('vraja.ai.card', 'action_save_product_ai_dashboard_data', [this.state.cardId, values]);
            await this.loadProductAIDashboardData();
            this.loadSelectedProducts();

            this.state.useSalesHistory = this.state.productData?.product_ai_use_sales_history ?? true;
            this.state.suggestionType = this.state.productData?.product_ai_suggestion_type || '';
            this.state.minConfidence = this.state.productData?.product_ai_min_confidence || '';

            this._showMessage('Settings saved successfully.', 'success');
            this.goToStep('#product_ai_step4_section', '#product_ai_step5_section');

        } catch (e) {
            this._showMessage('Failed to save: ' + (e.message || String(e)), 'danger');
        } finally {
            this.state.loading = false;
        }
    }

    /**
     * Sends selected products to OpenAI for analysis.
     */
    async onProductAIRun() {
        try {
            this.state.loading = true;
            await this.orm.call('vraja.ai.card', 'action_run_product_ai', [this.state.cardId]);
            await this.loadProductAIDashboardData();

            if (this.state.productData?.product_ai_status === 'error') {
                this._showMessage(this.state.productData.product_ai_error || 'AI analysis failed.', 'danger');
            } else {
                this._showMessage('AI analysis completed successfully.', 'success');
                this.goToStep('#product_ai_step5_section', '#product_ai_step6_section');
            }

        } catch (e) {
            const msg = e?.data?.message || e?.message || String(e);
            this._showMessage(msg, 'danger');
            await this.loadProductAIDashboardData();
        } finally {
            this.state.loading = false;
        }
    }


    /**
     * Applies AI suggestions (alternatives/accessories) to Odoo products.
     */
    async onProductAIApply() {
        if (!confirm('This will overwrite existing alternative and accessory products. Continue?')) return;
        try {
            this.state.loading = true;
            const result = await this.orm.call('vraja.ai.card', 'action_apply_product_ai_suggestions', [this.state.cardId]);
            await this.loadProductAIDashboardData();
            this._showMessage(`Successfully applied to ${result.applied} product(s).`, 'success');
        } catch (e) {
            this._showMessage('Apply Error: ' + (e.message || String(e)), 'danger');
        } finally {
            this.state.loading = false;
        }
    }
}

ProductAIAgentDashboard.template = "vraja_ai_dashboard_template";
registry.category("actions").add("product_ai_agent_dashboard_template", ProductAIAgentDashboard);
