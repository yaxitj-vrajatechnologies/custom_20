/** @odoo-module **/

import {registry} from "@web/core/registry";
import {onMounted, onWillUnmount, signal} from "@odoo/owl";
import {useService} from "@web/core/utils/hooks";
import {VrajaAIDashboard} from "@vraja_ai/js/dashboard_client_action";

class DynamicPricingDashboard extends VrajaAIDashboard {

    setup() {
        super.setup();
        this.actionService = useService("action");

        this.productSelectorRef = signal.ref();
        this.pricelistSelectorRef = signal.ref();

        // Page state
        this.state.ready = false;
        this.state.dpData = null;
        this.state.loading = false;
        this.state.isRunning = false;
        this.state.message = '';
        this.state.messageType = '';

        // Product multi-select state
        this.state.selectedProducts = [];
        this.state.selectedProductMap = {};
        this.state.productSearch = '';
        this.state.productDropdown = [];
        this.state.showProductDropdown = false;


        // Segment rules state
        this.state.dpSegmentRules = [];
        this.state.dpSegmentTypeOptions = [];

        this.state.dpSegmentPlSearch = {};
        this.state.dpSegmentPlDropdown = {};
        this.state.dpSegmentPlDropdownKey = null;
        this._segmentPlBlurTimer = null;
        this.state.allPricelists = [];
        this.state.dpAutoApplyEnabled = false;
        this.state.dpCompetitorUrls = [];
        this._pollTimer = null;
        // Step 6 (Review) state
        this.state.step4Search = '';
        this.state.step4Page = 1;
        this.state.selectedRows = [];
        this.state.deletedRows = [];
        // this.state.dpResultsOverride = null;


        // Close dropdowns when clicking outside
        this._outsideClickHandler = (ev) => {
            if (this.productSelectorRef() && !this.productSelectorRef().contains(ev.target)) {
                this.state.showProductDropdown = false;
            }
            if (this.pricelistSelectorRef() && !this.pricelistSelectorRef().contains(ev.target)) {
                this.state.showPricelistDropdown = false;
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
            this._stopPolling();
        });
    }

    // ─────────────────────────────────────────────────────────────────────────
    // INITIALISATION
    // Loads card data after the base class resolves the store type.
    // ─────────────────────────────────────────────────────────────────────────

    async loadCardStore() {
        await super.loadCardStore();
        if (this.state.store === 'dynamic_pricing' || !this.state.cardId) {
            await this.ensureDpCardId();
        }
        if (this.state.store === 'dynamic_pricing' && this.state.cardId) {
            await this.loadDpDashboardData();
            this._restoreSelectionsFromData();
        }
        this.state.ready = true;
    }

    async ensureDpCardId() {
        if (this.state.cardId) return;
        const cardId = await this.orm.call('vraja.ai.card', 'action_dp_get_default_card_id', []);
        if (cardId) {
            this.state.cardId = cardId;
            this.state.store = 'dynamic_pricing';
        }
    }

    // ─────────────────────────────────────────────────────────────────────────
    // DATA LOADING
    // ─────────────────────────────────────────────────────────────────────────

    async loadDpDashboardData() {
        if (!this.state.cardId) return;
        try {
            this.state.dpData = await this.orm.call(
                'vraja.ai.card', 'get_dp_dashboard_data', [this.state.cardId]
            );
            // Load all pricelists for segment rule dropdowns
            this.state.allPricelists = await this.orm.searchRead(
                'product.pricelist', [], ['id', 'name'], {limit: 0}
            );
            // Restore auto apply toggle state
            this.state.dpAutoApplyEnabled = this.state.dpData?.dp_auto_apply || false;
        } catch (e) {
            console.error('Failed to load DP dashboard data:', e);
        }
    }

    /** Restores product and pricelist selections from loaded card data. */
    _restoreSelectionsFromData() {
        const d = this.state.dpData;
        if (!d) return;
        if (d.dp_segment_type_options) {
            this.state.dpSegmentTypeOptions = d.dp_segment_type_options;
        }

        this.state.selectedProducts = (d.selected_products || []).map(p => ({id: p.id, name: p.name}));
        this.state.selectedProductMap = Object.fromEntries(
            this.state.selectedProducts.map(p => [p.id, true])
        );
        this.state.selectedPricelists = (d.selected_pricelists || []).map(pl => ({id: pl.id, name: pl.name}));

        this.state.dpSegmentRules = (d.dp_segment_rules || []).map(r => ({
            _key: r.id?.toString() || Date.now().toString(),
            id: r.id || false,
            customer_type: r.customer_type || 'retailer',
            pricelist_ids: (r.pricelist_ids || []),
            min_margin_pct: r.min_margin_pct || 0,
            max_margin_pct: r.max_margin_pct || 0,
            max_decrease_pct: r.max_decrease_pct || 0,
            max_increase_pct: r.max_increase_pct || 0,
        }));

        this.state.dpAutoApplyEnabled = d.dp_auto_apply || false;

        // Load dynamic competitor URLs
        if (d.dp_competitor_urls && d.dp_competitor_urls.length > 0) {
            this.state.dpCompetitorUrls = d.dp_competitor_urls.map(u => ({
                _key: `${Date.now()}_${Math.random().toString(36).slice(2)}`,
                url: u.url || '',
            }));
        } else {
            this.state.dpCompetitorUrls = [];
        }
    }

    // ─────────────────────────────────────────────────────────────────────────
    // STEP NAVIGATION
    // ─────────────────────────────────────────────────────────────────────────

    goToStep(currentId, targetId) {
        document.querySelector(currentId)?.classList.remove('show');
        const target = document.querySelector(targetId);
        if (target) {
            target.classList.add('show');
            setTimeout(() => target.closest('.card')?.scrollIntoView({behavior: 'smooth', block: 'start'}), 100);
        }
    }

    openStep(targetId) {
        const target = document.querySelector(targetId);
        if (target) {
            target.classList.add('show');
            setTimeout(() => target.closest('.card')?.scrollIntoView({behavior: 'smooth', block: 'start'}), 100);
        }
    }

    // ─────────────────────────────────────────────────────────────────────────
    // PRODUCT MULTI-SELECT
    // ─────────────────────────────────────────────────────────────────────────

    async onProductSearchInput(ev) {
        this.state.productSearch = ev.target.value;
        if (!this.state.productSearch.trim()) {
            this.state.productDropdown = [];
            this.state.showProductDropdown = false;
            return;
        }
        const results = await this.orm.searchRead(
            'product.product',
            [
                ['active', '=', true],
                ['sale_ok', '=', true],
                ['display_name', 'ilike', this.state.productSearch],
                ['id', 'not in', this.state.selectedProducts.map(p => p.id)],
            ],
            ['id', 'display_name'], {limit: 0}
        );
        this.state.productDropdown = results.map(p => ({id: p.id, name: p.display_name}));
        this.state.showProductDropdown = this.state.productDropdown.length > 0;
    }

    async onProductSearchFocus() {
        const excludeIds = this.state.selectedProducts.map(p => p.id);
        const results = await this.orm.searchRead(
            'product.product',
            [['active', '=', true], ['sale_ok', '=', true], ['id', 'not in', excludeIds]],
            ['id', 'display_name'], {limit: 0}
        );
        this.state.productDropdown = results.map(p => ({id: p.id, name: p.display_name}));
        this.state.showProductDropdown = this.state.productDropdown.length > 0;
    }

    async onSelectAllProducts() {
        if (this.state.selectedProducts.length) {
            this.state.selectedProducts = [];
            this.state.selectedProductMap = {};
        } else {
            const all = await this.orm.searchRead(
                'product.product',
                [['active', '=', true], ['sale_ok', '=', true]],
                ['id', 'display_name'], {limit: 0}
            );
            const normalized = all.map(p => ({id: p.id, name: p.display_name}));
            this.state.selectedProducts = normalized;
            this.state.selectedProductMap = Object.fromEntries(normalized.map(p => [p.id, true]));
        }
        this.state.showProductDropdown = false;
        await this._autoSaveProducts();
    }

    async onToggleProductCheckbox(product) {
        const map = {...this.state.selectedProductMap};
        if (map[product.id]) {
            delete map[product.id];
            this.state.selectedProducts = this.state.selectedProducts.filter(p => p.id !== product.id);
        } else {
            map[product.id] = true;
            this.state.selectedProducts = [...this.state.selectedProducts, product];
        }
        this.state.selectedProductMap = map;
        await this._autoSaveProducts();
    }

    async onRemoveProduct(productId) {
        const map = {...this.state.selectedProductMap};
        delete map[productId];
        this.state.selectedProductMap = map;
        this.state.selectedProducts = this.state.selectedProducts.filter(p => p.id !== productId);
        await this._autoSaveProducts();
    }

    async _autoSaveProducts() {
        await this.orm.call('vraja.ai.card', 'action_save_dp_dashboard_data', [
            this.state.cardId,
            {dp_selected_product_ids: this.state.selectedProducts.map(p => p.id)}
        ]);
    }

    // ─────────────────────────────────────────────────────────────────────────
    // AUTO APPLY TOGGLE
    // ─────────────────────────────────────────────────────────────────────────

    onDpAutoApplyToggle(ev) {
        this.state.dpAutoApplyEnabled = ev.target.checked;
        if (this.state.dpData) {
            this.state.dpData.dp_auto_apply = ev.target.checked;
        }
    }

    // ─────────────────────────────────────────────────────────────────────────
    // SEGMENT RULES — Add / Delete / Edit rows
    // All fields use vraja.ai.card field names (dp_* prefix on card fields,
    // no prefix on segment row fields which are saved via dp_segment_rules list)
    // ─────────────────────────────────────────────────────────────────────────

    onSegmentAddRow() {
        const newRule = {
            _key: `${Date.now()}_${Math.random().toString(36).slice(2)}`,
            id: false,
            customer_type: 'retailer',
            pricelist_ids: [],
            min_margin_pct: this.state.dpData?.dp_min_margin_pct || 15.0,
            max_margin_pct: this.state.dpData?.dp_max_margin_pct || 60.0,
            max_decrease_pct: this.state.dpData?.dp_max_decrease_pct || 20.0,
            max_increase_pct: this.state.dpData?.dp_max_increase_pct || 10.0,
        };
        this.state.dpSegmentRules = [...this.state.dpSegmentRules, newRule];
    }

    onSegmentDeleteRow(key) {
        this.state.dpSegmentRules = this.state.dpSegmentRules.filter(r => r._key !== key);
    }

    onCompetitorUrlAdd() {
        this.state.dpCompetitorUrls = [
            ...this.state.dpCompetitorUrls,
            {
                _key: `${Date.now()}_${Math.random().toString(36).slice(2)}`,
                url: '',
            }
        ];
    }

    onCompetitorUrlDelete(key) {
        this.state.dpCompetitorUrls = this.state.dpCompetitorUrls.filter(u => u._key !== key);
    }

    onCompetitorUrlChange(key, value) {
        this.state.dpCompetitorUrls = this.state.dpCompetitorUrls.map(u =>
            u._key === key ? {...u, url: value} : u
        );
    }

    getSegmentLabel(value) {
        const option = this.state.dpSegmentTypeOptions.find(o => o.value === value);
        return option ? option.label : value;
    }

    onSegmentTypeChange(key, value) {
        this.state.dpSegmentRules = this.state.dpSegmentRules.map(r =>
            r._key === key ? {...r, customer_type: value} : r
        );
    }

    onDpDataChange(field, value) {
        this.state.dpData = {...this.state.dpData, [field]: value};
    }

    onSegmentNumChange(key, field, value) {
        this.state.dpSegmentRules = this.state.dpSegmentRules.map(r =>
            r._key === key ? {...r, [field]: parseFloat(value) || 0} : r
        );
    }

    // ─────────────────────────────────────────────────────────────────────────
    // SEGMENT RULES — Pricelist tag-box per row
    // ─────────────────────────────────────────────────────────────────────────

    onSegmentPlBoxClick(key, ev) {
        if (this._segmentPlBlurTimer) {
            clearTimeout(this._segmentPlBlurTimer);
            this._segmentPlBlurTimer = null;
        }
        this.state.dpSegmentPlDropdownKey = key;
        this._filterSegmentPricelists(key, this.state.dpSegmentPlSearch[key] || '');
        const input = ev.currentTarget.querySelector('input');
        if (input) input.focus();
    }

    onSegmentPlSearchInput(key, value) {
        this.state.dpSegmentPlSearch = {...this.state.dpSegmentPlSearch, [key]: value};
        this._filterSegmentPricelists(key, value);
    }

    onSegmentPlFocus(key) {
        // Cancel any pending blur close
        if (this._segmentPlBlurTimer) {
            clearTimeout(this._segmentPlBlurTimer);
            this._segmentPlBlurTimer = null;
        }
        this.state.dpSegmentPlDropdownKey = key;
        this._filterSegmentPricelists(key, this.state.dpSegmentPlSearch[key] || '');
    }

    onSegmentPlBlur(key) {
        this._segmentPlBlurTimer = setTimeout(() => {
            this.state.dpSegmentPlDropdownKey = null;
            this._segmentPlBlurTimer = null;
        }, 200);
    }

    onSegmentTogglePl(key, pl) {
        this.state.dpSegmentRules = this.state.dpSegmentRules.map(r => {
            if (r._key !== key) return r;

            const exists = (r.pricelist_ids || []).some(p => p.id === pl.id);

            return {
                ...r,
                pricelist_ids: exists
                    ? r.pricelist_ids.filter(p => p.id !== pl.id)
                    : [...(r.pricelist_ids || []), {id: pl.id, name: pl.name}],
            };
        });

        this._filterSegmentPricelists(key, this.state.dpSegmentPlSearch[key] || '');
    }

    onSegmentRemovePl(key, plId, ev) {
        ev.stopPropagation();

        this.state.dpSegmentRules = this.state.dpSegmentRules.map(r =>
            r._key === key
                ? {...r, pricelist_ids: (r.pricelist_ids || []).filter(p => p.id !== plId)}
                : r
        );

        this._filterSegmentPricelists(key, this.state.dpSegmentPlSearch[key] || '');
    }

    _filterSegmentPricelists(key, search) {
        const all = this.state.allPricelists || [];
        const q = (search || '').toLowerCase();

        // Exclude pricelists already used in ANY segment
        const selectedIds = this.state.dpSegmentRules.flatMap(r =>
            (r.pricelist_ids || []).map(p => p.id)
        );

        const filtered = all.filter(p => {
            const matchesSearch = !q || (p.name || '').toLowerCase().includes(q);
            const notAlreadySelected = !selectedIds.includes(p.id);
            return matchesSearch && notAlreadySelected;
        });

        this.state.dpSegmentPlDropdown = {
            ...this.state.dpSegmentPlDropdown,
            [key]: filtered,
        };
    }

    // ─────────────────────────────────────────────────────────────────────────
    // BUSINESS INFO BLUR — auto-persist the textarea on blur
    // ─────────────────────────────────────────────────────────────────────────

    async onBusinessInfoBlur(ev) {
        const value = ev.target.value || '';
        try {
            await this.orm.call('vraja.ai.card', 'action_save_dp_dashboard_data', [
                this.state.cardId,
                {dp_business_info: value}
            ]);
            if (this.state.dpData) this.state.dpData.dp_business_info = value;
        } catch (e) {
            console.error('Failed to save business info:', e);
        }
    }

    // ─────────────────────────────────────────────────────────────────────────
    // FLASH MESSAGE
    // ─────────────────────────────────────────────────────────────────────────

    _showMessage(msg, type = 'success') {
        this.state.message = msg;
        this.state.messageType = type;
        setTimeout(() => {
            this.state.message = '';
        }, 4000);
    }

    // ─────────────────────────────────────────────────────────────────────────
    // REVIEW TABLE HELPERS
    // ─────────────────────────────────────────────────────────────────────────

    // 2.  getDpResults() — add unique rowKey per row
    getDpResults() {
        if (!this.state.dpData?.dp_result_json) return [];
        try {
            const parsed = JSON.parse(this.state.dpData.dp_result_json);
            if (!Array.isArray(parsed)) return [];
            const costMap = {};
            for (const p of (this.state.dpData?.selected_products || [])) {
                if (p.cost_price !== undefined) costMap[p.id] = p.cost_price;
            }

            return parsed.map((d) => ({
                product_id: d.product_id,
                product_name: d.product_name || '',
                segment_name: d.segment_name || '',
                cost_price: d.cost_price || costMap[d.product_id] || 0,
                current_price: d.current_price || 0,
                suggested_price: d.suggested_price || 0,
                decision: d.decision || 'hold',
                margin_before: d.margin_before || 0,
                margin_after: d.margin_after || 0,
                reason: d.reason || '',
                rowKey: `${d.product_id}_${d.segment_name || ''}`,  // ← unique per row
            }));
        } catch {
            return [];
        }
    }

    // 3. REPLACE getFilteredDpResults() — filter by rowKey not product_id
    getFilteredDpResults() {
        let results = this.getDpResults();
        if (this.state.deletedRows?.length) {
            results = results.filter(r => !this.state.deletedRows.includes(r.rowKey));
        }
        const q = (this.state.step4Search || '').toLowerCase();
        if (!q) return results;
        return results.filter(r =>
            r.product_name.toLowerCase().includes(q) ||
            r.segment_name.toLowerCase().includes(q)
        );
    }

    onStep4Search(ev) {
        this.state.step4Page = 1;
        this.state.step4Search = ev.target.value;
    }

    getPagedDpResults() {
        const start = (this.state.step4Page - 1) * 10;
        return this.getFilteredDpResults().slice(start, start + 10);
    }

    getTotalPages() {
        return Math.max(1, Math.ceil(this.getFilteredDpResults().length / 10));
    }

    getPageNumbers() {
        const total = this.getTotalPages(), cur = this.state.step4Page, pages = [];
        if (total <= 7) {
            for (let i = 1; i <= total; i++) pages.push(i);
        } else {
            pages.push(1);
            if (cur > 3) pages.push('...');
            for (let i = Math.max(2, cur - 1); i <= Math.min(total - 1, cur + 1); i++) pages.push(i);
            if (cur < total - 2) pages.push('...');
            pages.push(total);
        }
        return pages;
    }


    onStep4PageChange(page) {
        if (page >= 1 && page <= this.getTotalPages()) this.state.step4Page = page;
    }

    getDecisionBadgeClass(decision) {
        return {
            increase: 'dp-badge-increase',
            decrease: 'dp-badge-decrease',
            hold: 'dp-badge-hold',
            skip: 'dp-badge-skip',
        }[decision] || 'dp-badge-skip';
    }

    isDpRowSelected(rowKey) {
        return this.state.selectedRows.includes(rowKey);
    }

    // 5. REPLACE toggleDpRow — use rowKey
    toggleDpRow(rowKey, ev) {
        if (ev.target.checked) {
            this.state.selectedRows = [...this.state.selectedRows, rowKey];
        } else {
            this.state.selectedRows = this.state.selectedRows.filter(k => k !== rowKey);
        }
    }

    isDpAllSelected() {
        const rows = this.getFilteredDpResults();
        return rows.length > 0 && rows.every(r => this.state.selectedRows.includes(r.rowKey));
    }

    // toggleDpSelectAll — use rowKey
    toggleDpSelectAll(ev) {
        const rows = this.getFilteredDpResults();
        if (ev.target.checked) {
            this.state.selectedRows = rows.map(r => r.rowKey);
        } else {
            this.state.selectedRows = [];
        }
    }

    async deleteSelectedDpRows() {
        const toDelete = [...this.state.selectedRows];
        this.state.deletedRows = [...this.state.deletedRows, ...toDelete];
        this.state.selectedRows = [];
        this._showMessage('Selected rows removed.', 'success');
        await this.orm.call('vraja.ai.card', 'action_delete_dp_result_rows', [this.state.cardId, toDelete]);
    }

    async deleteSingleDpRow(rowKey) {
        this.state.deletedRows = [...this.state.deletedRows, rowKey];
        this._showMessage('Row removed.', 'success');
        await this.orm.call('vraja.ai.card', 'action_delete_dp_result_rows', [this.state.cardId, [rowKey]]);
    }

    // ─────────────────────────────────────────────────────────────────────────
    // SAVE — Step 4: all config, segment rules, competitor URLs, thresholds
    // ─────────────────────────────────────────────────────────────────────────

    async onDpSave() {
        const deadStockEl = document.getElementById('dp_dead_stock_days');
        const salesHistoryEl = document.getElementById('dp_sales_history_days');
        const cronTimeEl = document.getElementById('dp_cron_time');

        const invalidSegments = (this.state.dpSegmentRules || []).filter(
            r => !r.pricelist_ids || r.pricelist_ids.length === 0
        );
        if (invalidSegments.length) {
            this._showMessage(
                'Each segment must have at least one pricelist assigned.',
                'danger'
            );
            return;
        }

        const payload = {
            dp_dead_stock_days: deadStockEl ? parseInt(deadStockEl.value) || 45 : 45,
            dp_sales_history_days: salesHistoryEl ? parseInt(salesHistoryEl.value) || 30 : 30,
            dp_competitor_urls_json: JSON.stringify(
                (this.state.dpCompetitorUrls || [])
                    .filter(u => u.url && u.url.trim())
                    .map(u => ({url: u.url.trim()}))
            ),
            dp_cron_time: cronTimeEl ? cronTimeEl.value : '02:00 AM',
            dp_auto_apply: this.state.dpAutoApplyEnabled,
            create_batches: true,

            // pricelist_ids kept as [{id, name}] so Python can re-serialize them
            dp_segment_rules: (this.state.dpSegmentRules || []).map(r => ({
                id: r.id || false,
                customer_type: r.customer_type || 'retailer',
                pricelist_ids: (r.pricelist_ids || []),
                min_margin_pct: r.min_margin_pct || 0,
                max_margin_pct: r.max_margin_pct || 0,
                max_decrease_pct: r.max_decrease_pct || 0,
                max_increase_pct: r.max_increase_pct || 0,
            })),
        };

        try {
            this.state.loading = true;
            await this.orm.call(
                'vraja.ai.card',
                'action_save_dp_dashboard_data',
                [this.state.cardId, payload],
            );
            // Keep local state in sync
            await this.loadDpDashboardData();
            this._showMessage('Settings saved successfully.', 'success');
            this.goToStep('#dp_step4_section', '#dp_step5_section');
        } catch (e) {
            this._showMessage('Save failed: ' + (e?.data?.message || e?.message || String(e)), 'danger');
        } finally {
            this.state.loading = false;
        }
    }

    _startPolling() {
        this._stopPolling();
        this._pollTimer = setInterval(async () => {
            await this.loadDpDashboardData();
            const batches = this.state.dpData?.dp_batches || [];
            const allDone = batches.length > 0 && batches.every(b => b.state === 'done');
            // Batches are reset to 'draft' on error (never set to 'error' state).
            // Detect failure via error_message field being populated.
            const errBatch = batches.find(b => b.error_message && b.error_message.trim() !== '');
            if (allDone) {
                this._stopPolling();
                this.state.loading = false;
                this.state.isRunning = false;
                this._showMessage('Analysis complete! Review your results.', 'success');
                setTimeout(() => this.goToStep('#dp_step5_section', '#dp_step6_section'), 50);
            } else if (errBatch) {
                this._stopPolling();
                this.state.loading = false;
                this.state.isRunning = false;
                this._showMessage(
                    'Analysis failed: ' + errBatch.error_message,
                    'danger'
                );
            }
        }, 5000);
    }

    _stopPolling() {
        if (this._pollTimer) {
            clearInterval(this._pollTimer);
            this._pollTimer = null;
        }
    }

    async onRefreshBatchStatus() {
        await this.loadDpDashboardData();
        setTimeout(() => this.openStep('#dp_step5_section'), 50);

        const allBatchesDone = this.state.dpData?.dp_batches?.length > 0 &&
            this.state.dpData.dp_batches.every(b => b.state === 'done');

        if (allBatchesDone) {
            this._showMessage('Analysis complete! Moving to Review.', 'success');
            setTimeout(() => this.goToStep('#dp_step5_section', '#dp_step6_section'), 50);
        } else if (this.state.dpData?.dp_status === 'running') {
            this._showMessage('Analysis is still running. Please wait.', 'warning');
        } else if (this.state.dpData?.dp_status === 'error') {
            this._showMessage('Analysis failed. Please check batch errors.', 'danger');
        } else {
            this._showMessage('Batch status refreshed.', 'info');
        }
    }

    // ─────────────────────────────────────────────────────────────────────────
    // APPLY PRICING
    // ─────────────────────────────────────────────────────────────────────────

    async onDpApply() {
        if (!confirm('Apply AI suggested prices to selected pricelists?')) return;
        try {
            this.state.loading = true;

            // Only send rows that are NOT deleted
            const activeRows = this.getFilteredDpResults().map(r => ({
                product_id: r.product_id,
                product_name: r.product_name,
                segment_name: r.segment_name,
                suggested_price: r.suggested_price,
                decision: r.decision,
                margin_before: r.margin_before,
                margin_after: r.margin_after,
            }));

            const result = await this.orm.call(
                'vraja.ai.card', 'action_apply_dynamic_pricing', [
                    this.state.cardId,
                    (this.state.dpSegmentRules || []).map(r => ({
                        customer_type: this.getSegmentLabel(r.customer_type),
                        pricelist_ids: (r.pricelist_ids || []).map(p => p.id),
                        min_margin_pct: r.min_margin_pct || 0,
                        max_margin_pct: r.max_margin_pct || 0,
                        max_decrease_pct: r.max_decrease_pct || 0,
                        max_increase_pct: r.max_increase_pct || 0,
                    })),
                    activeRows,  // ← filtered rows, deleted ones excluded
                ]
            );
            await this.loadDpDashboardData();
            this._showMessage(`Successfully applied to ${result.applied} product(s).`, 'success');
        } catch (e) {
            this._showMessage('Apply failed: ' + (e?.data?.message || e?.message || String(e)), 'danger');
        } finally {
            this.state.loading = false;
        }
    }

    async openAnalysisDashboard() {
        await this.actionService.doAction({
            type: 'ir.actions.client',
            tag: 'dynamic_pricing_analysis_dashboard',
            target: 'current',
            params: {card_id: this.state.dpData?.id},
        });
    }

    async runAllBatches() {
        const allBatchesDone = this.state.dpData?.dp_batches?.length > 0 &&
            this.state.dpData.dp_batches.every(b => b.state === 'done');

        if (allBatchesDone) {
            this.openStep('#dp_step6_section');
            return;
        }

        // Clear any previous error_message from batches so polling re-arms cleanly
        this.state.loading = true;
        this.state.isRunning = true;

        this._startPolling();
        fetch('/web/dataset/call_kw', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                jsonrpc: '2.0', method: 'call', id: 1,
                params: {
                    model: 'vraja.ai.card',
                    method: 'action_cron_dp_run_analysis',
                    args: [], kwargs: {},
                }
            })
        }).catch(e => {
            // Network-level failure (e.g. server unreachable)
            this._stopPolling();
            this.state.loading = false;
            this.state.isRunning = false;
            this._showMessage('Failed to reach server: ' + (e?.message || String(e)), 'danger');
        });
    }

    openBatchView() {
        this.env.services.action.doAction('dynamic_pricing_with_ai.vraja_dp_batch_action');
    }
}

DynamicPricingDashboard.template = "vraja_ai_dashboard_template";
registry.category("actions").add("dynamic_pricing_dashboard_template", DynamicPricingDashboard);
