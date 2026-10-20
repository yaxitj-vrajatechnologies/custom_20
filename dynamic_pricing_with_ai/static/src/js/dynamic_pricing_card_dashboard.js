/** @odoo-module **/

import {registry} from "@web/core/registry";
import {onMounted, onWillUnmount} from "@odoo/owl";
import {useService} from "@web/core/utils/hooks";
import {VrajaAIDashboard} from "@vraja_ai/js/dashboard_client_action";

class DynamicPricingDashboard extends VrajaAIDashboard {

    setup() {
        super.setup();
        this.actionService = useService("action");

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
        this.state.productSelectionLoading = false;
        this._productSearchRequest = 0;


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
            const productEl = document.getElementById("dp_product_selector");
            if (productEl && !productEl.contains(ev.target)) {
                this.state.showProductDropdown = false;
            }
            const pricelistEl = document.getElementById("dp_pricelist_selector");
            if (pricelistEl && !pricelistEl.contains(ev.target)) {
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
        if (!this.state.cardId) {
            this._showMessage('Dynamic pricing card is not available. Reload the dashboard and try again.', 'danger');
            return false;
        }
        try {
            this.state.dpData = await this.orm.call(
                'vraja.ai.card', 'get_dp_dashboard_data', [this.state.cardId]
            );
            // Restore auto apply toggle state
            this.state.dpAutoApplyEnabled = this.state.dpData?.dp_auto_apply || false;
        } catch (e) {
            console.error('Failed to load DP dashboard data:', e);
            this._showMessage('Could not load dashboard data: ' + (e?.data?.message || e?.message || String(e)), 'danger');
            return false;
        }

        // A limit of 0 returns no records in Odoo 20; omit it to fetch every
        // active pricelist available to the current user/company.
        try {
            this.state.allPricelists = await this.orm.searchRead(
                'product.pricelist', [['active', '=', true]], ['id', 'name']
            );
        } catch (e) {
            this.state.allPricelists = [];
            console.error('Failed to load pricelists:', e);
            this._showMessage(
                'Failed to load pricelists: ' + (e?.data?.message || e?.message || String(e)),
                'danger'
            );
        }
        return true;
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
            this._productSearchRequest++;
            this.state.productDropdown = [];
            this.state.showProductDropdown = false;
            return;
        }
        await this._searchProducts(this.state.productSearch);
    }

    async onProductSearchFocus() {
        await this._searchProducts(this.state.productSearch);
    }

    async _searchProducts(query = '') {
        const requestId = ++this._productSearchRequest;
        const domain = [
            ['active', '=', true],
            ['sale_ok', '=', true],
            ['id', 'not in', this.state.selectedProducts.map(product => product.id)],
        ];
        if (query.trim()) {
            domain.push(['display_name', 'ilike', query.trim()]);
        }
        try {
            const products = await this.orm.searchRead(
                'product.product', domain, ['id', 'display_name'],
                {limit: 80}
            );
            if (requestId !== this._productSearchRequest) return;
            this.state.productDropdown = products.map(product => ({
                id: product.id,
                name: product.display_name,
            }));
            this.state.showProductDropdown = true;
        } catch (error) {
            if (requestId === this._productSearchRequest) {
                this.state.showProductDropdown = false;
                this._showMessage(
                    'Product search failed: ' + (error?.data?.message || error?.message || String(error)),
                    'danger'
                );
            }
        }
    }

    async onSelectAllProducts() {
        if (this.state.productSelectionLoading) return;
        this.state.productSelectionLoading = true;
        const previousSelection = this._getProductSelectionSnapshot();
        try {
            if (this.state.selectedProducts.length) {
                this.state.selectedProducts = [];
                this.state.selectedProductMap = {};
            } else {
                const products = await this.orm.searchRead(
                    'product.product',
                    [['active', '=', true], ['sale_ok', '=', true]],
                    ['id', 'display_name'], {limit: 100000}
                );
                this.state.selectedProducts = products.map(product => ({
                    id: product.id,
                    name: product.display_name,
                }));
                this.state.selectedProductMap = Object.fromEntries(
                    this.state.selectedProducts.map(product => [product.id, true])
                );
            }
            this.state.showProductDropdown = false;
            await this._autoSaveProducts();
        } catch (error) {
            this._restoreProductSelection(previousSelection);
            this._showMessage(
                'Product selection failed: ' + (error?.data?.message || error?.message || String(error)),
                'danger'
            );
        } finally {
            this.state.productSelectionLoading = false;
        }
    }

    async onToggleProductCheckbox(product) {
        const previousSelection = this._getProductSelectionSnapshot();
        const map = {...this.state.selectedProductMap};
        if (map[product.id]) {
            delete map[product.id];
            this.state.selectedProducts = this.state.selectedProducts.filter(p => p.id !== product.id);
        } else {
            map[product.id] = true;
            this.state.selectedProducts = [...this.state.selectedProducts, product];
        }
        this.state.selectedProductMap = map;
        try {
            await this._autoSaveProducts();
        } catch (error) {
            this._restoreProductSelection(previousSelection);
            this._showMessage(
                'Could not save product selection: ' + (error?.data?.message || error?.message || String(error)),
                'danger'
            );
        }
    }

    async onRemoveProduct(productId) {
        const previousSelection = this._getProductSelectionSnapshot();
        const map = {...this.state.selectedProductMap};
        delete map[productId];
        this.state.selectedProductMap = map;
        this.state.selectedProducts = this.state.selectedProducts.filter(p => p.id !== productId);
        try {
            await this._autoSaveProducts();
        } catch (error) {
            this._restoreProductSelection(previousSelection);
            this._showMessage(
                'Could not save product selection: ' + (error?.data?.message || error?.message || String(error)),
                'danger'
            );
        }
    }

    _getProductSelectionSnapshot() {
        return {
            products: [...this.state.selectedProducts],
            productMap: {...this.state.selectedProductMap},
        };
    }

    _restoreProductSelection(snapshot) {
        this.state.selectedProducts = snapshot.products;
        this.state.selectedProductMap = snapshot.productMap;
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

        // A pricelist can only be assigned to one segment at a time.
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
        if (type === 'success' || type === 'info') {
            setTimeout(() => {
                if (this.state.message === msg) this.state.message = '';
            }, 5000);
        }
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
        if (!this.state.cardId) {
            this._showMessage('The dynamic pricing card has not loaded yet. Please wait for the dashboard to finish loading and try again.', 'danger');
            return;
        }
        const deadStockEl = document.getElementById('dp_dead_stock_days');
        const salesHistoryEl = document.getElementById('dp_sales_history_days');
        const cronTimeEl = document.getElementById('dp_cron_time');

        if (!this.state.selectedProducts?.length) {
            this._showMessage('Select at least one product in Step 3 before saving.', 'warning');
            return;
        }
        if (!this.state.dpSegmentRules?.length) {
            this._showMessage('Add at least one customer segment in Step 4 before saving.', 'warning');
            return;
        }
        const invalidCustomer = this.state.dpSegmentRules.some(r => !r.customer_type);
        if (invalidCustomer) {
            this._showMessage('Choose a customer type for every segment.', 'danger');
            return;
        }
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
            dp_selected_product_ids: this.state.selectedProducts.map(p => p.id),

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
            const result = await this.orm.call(
                'vraja.ai.card',
                'action_save_dp_dashboard_data',
                [this.state.cardId, payload],
            );
            if (result?.success === false) {
                throw new Error(result.message || 'The server rejected the dashboard settings.');
            }

            // Open Step 5 on a successful save RPC. Confirm the generated CSV
            // and batches from persisted dashboard data, not a version-specific
            // response shape.
            this.goToStep('#dp_step4_section', '#dp_step5_section');
            const loaded = await this.loadDpDashboardData();
            if (loaded) {
                this._restoreSelectionsFromData();
                const hasCsv = Boolean(this.state.dpData?.dp_csv_attachment_id);
                const batches = this.state.dpData?.dp_batches || [];
                if (hasCsv && batches.length) {
                    this._showMessage(`Saved successfully: CSV generated and ${batches.length} batch(es) created.`, 'success');
                } else if (!hasCsv) {
                    this._showMessage('Settings saved, but the server did not generate a products CSV. Check server logs and verify selected products.', 'danger');
                } else {
                    this._showMessage('CSV generated, but no batches were created. Verify that at least one segment with a pricelist was saved.', 'danger');
                }
            } else {
                this._showMessage(
                    'Settings were saved and Step 5 is open, but dashboard data could not be reloaded. Use Refresh Status to retry.',
                    'warning'
                );
            }
        } catch (e) {
            console.error('Failed to save dynamic pricing dashboard settings:', e);
            this._showMessage('Save failed: ' + (e?.data?.message || e?.message || String(e)), 'danger');
        } finally {
            this.state.loading = false;
        }
    }

    _startPolling() {
        this._stopPolling();
        this._pollTimer = setInterval(async () => {
            const loaded = await this.loadDpDashboardData();
            if (!loaded) return;
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
        const loaded = await this.loadDpDashboardData();
        if (!loaded) return;
        this._restoreSelectionsFromData();
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
        } else if (!this.state.dpData?.dp_batches?.length) {
            this._showMessage('No batches are available. Complete Step 4 and click Save & Next first.', 'warning');
        } else if (this.state.dpData.dp_batches.some(b => b.error_message)) {
            const failed = this.state.dpData.dp_batches.find(b => b.error_message);
            this._showMessage('Batch needs attention: ' + failed.error_message, 'danger');
        } else if (this.state.dpData.dp_batches.some(b => b.state === 'draft')) {
            this._showMessage('Batches are ready. Click Run All Batches to start the analysis.', 'info');
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
        if (this.state.isRunning) return;
        this.state.loading = true;
        const loaded = await this.loadDpDashboardData();
        if (!loaded) {
            this.state.loading = false;
            return;
        }
        this._restoreSelectionsFromData();
        const allBatchesDone = this.state.dpData?.dp_batches?.length > 0 &&
            this.state.dpData.dp_batches.every(b => b.state === 'done');

        if (allBatchesDone) {
            this.state.loading = false;
            this.openStep('#dp_step6_section');
            return;
        }

        const batches = this.state.dpData?.dp_batches || [];
        if (!batches.length) {
            this.state.loading = false;
            this._showMessage('No batches found. Complete Step 4 and click Save & Next first.', 'warning');
            return;
        }
        if (batches.some(batch => batch.state === 'running')) {
            this.state.loading = false;
            this.state.isRunning = true;
            this._startPolling();
            this._showMessage('Analysis is already running. Refresh status to check progress.', 'info');
            return;
        }
        if (!batches.some(batch => batch.state === 'draft')) {
            this.state.loading = false;
            const failed = batches.find(batch => batch.error_message);
            this._showMessage(failed?.error_message || 'There are no draft batches available to run.', 'danger');
            return;
        }

        // Clear any previous error_message from batches so polling re-arms cleanly
        this.state.loading = true;
        this.state.isRunning = true;

        this._startPolling();
        try {
            await this.orm.call('vraja.ai.card', 'action_cron_dp_run_analysis', []);
            const refreshed = await this.loadDpDashboardData();
            if (!refreshed) throw new Error('The run was requested, but the latest batch status could not be loaded.');
            const latest = this.state.dpData?.dp_batches || [];
            const done = latest.length > 0 && latest.every(batch => batch.state === 'done');
            const failed = latest.find(batch => batch.error_message);
            if (done) {
                this._stopPolling();
                this.state.loading = false;
                this.state.isRunning = false;
                this._showMessage('Analysis complete! Review your results.', 'success');
                this.goToStep('#dp_step5_section', '#dp_step6_section');
            } else if (failed) {
                this._stopPolling();
                this.state.loading = false;
                this.state.isRunning = false;
                this._showMessage('Analysis failed: ' + failed.error_message, 'danger');
            }
        } catch (e) {
            this._stopPolling();
            this.state.loading = false;
            this.state.isRunning = false;
            this._showMessage('Could not run batches: ' + (e?.data?.message || e?.message || String(e)), 'danger');
        }
    }

    openBatchView() {
        this.env.services.action.doAction('dynamic_pricing_with_ai.vraja_dp_batch_action');
    }
}

// The XML template extends this shared template; extension templates are not
// standalone component templates in Owl.
DynamicPricingDashboard.template = "vraja_ai_dashboard_template";
registry.category("actions").add("dynamic_pricing_dashboard_template", DynamicPricingDashboard);
