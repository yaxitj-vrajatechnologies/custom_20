/** @odoo-module **/

/**
 * @module vraja_bank_reconciliation_ai
 * @file bank_recon_dashboard.js
 *
 * Bank Reconciliation AI Dashboard — OWL Component
 * -------------------------------------------------
 * This is the main client-side controller for the Bank Reconciliation AI Dashboard.
 * It manages the full lifecycle of a reconciliation run:
 *
 *   1. Idle      — User selects a bank journal and triggers the AI agent.
 *   2. Running   — A 7-step animated stepper visualises progress while the
 *                  RPC call executes on the server in the background.
 *   3. Results   — Tri-category accordion results (Matched / Rule / To-Check)
 *                  are displayed with per-step drill-down tables.
 *
 * The component is registered as a client action under the key
 * "vraja_bank_recon.dashboard" and rendered via the OWL template
 * "vraja_bank_recon.Dashboard" defined in bank_recon_dashboard.xml.
 *
 * @author   Vraja Technologies
 * @version  19.0
 */

import { registry } from "@web/core/registry";
import { Component, onWillStart, proxy } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

// ═══════════════════════════════════════════════════════════════════════════════
// CONSTANTS
// ═══════════════════════════════════════════════════════════════════════════════

/**
 * STEPS — Static definition of the 7-step AI reconciliation workflow.
 *
 * Each entry drives both the animated stepper shown during the "running" phase
 * and the accordion panels shown in the "results" phase.
 *
 * Properties:
 *   @property {number} id    - 1-based step index (matches server step keys step1…step7).
 *   @property {string} key   - Unique string identifier used for step lookup.
 *   @property {string} icon  - Emoji icon rendered in the stepper circle label.
 *   @property {string} label - Short display name shown beneath the stepper circle.
 *   @property {string} desc  - Description shown in the live stepper description bar
 *                              while the agent is running.
 */
const STEPS = [
    { id: 1, key: "planning",        icon: "🧠", label: "Planning",        desc: "Analysing journal context and defining strategy" },
    { id: 2, key: "data_collection", icon: "📥", label: "Data Collection", desc: "Fetching unreconciled bank statement lines" },
    { id: 3, key: "internal_review", icon: "🔍", label: "Internal Review", desc: "Loading open journal items and invoices" },
    { id: 4, key: "auto_matching",   icon: "⚙️", label: "Auto Matching",   desc: "Running exact and fuzzy amount matching" },
    { id: 5, key: "rule_application",icon: "📋", label: "Rule Application",desc: "Applying historical and pre-defined rules" },
    { id: 6, key: "categorization",  icon: "🗂️", label: "Categorization",  desc: "Sorting results into Matched / Rule / Check" },
    { id: 7, key: "final_analysis",  icon: "✅", label: "Final Analysis",  desc: "Generating analysis record and AI log entry" },
];

/**
 * STEP_DELAY_MS — Milliseconds to hold each stepper step in the "active" state
 * before advancing to the next one.
 *
 * This creates the visual illusion of sequential progress even though the
 * server RPC runs in parallel. Tune this value to control animation speed.
 *
 * @type {number}
 */
const STEP_DELAY_MS = 950;


// ═══════════════════════════════════════════════════════════════════════════════
// COMPONENT
// ═══════════════════════════════════════════════════════════════════════════════

export class BankReconDashboard extends Component {

    // ───────────────────────────────────────────────────────────────────────────
    // LIFECYCLE
    // ───────────────────────────────────────────────────────────────────────────

    /**
     * setup() — OWL lifecycle hook (replaces the constructor in OWL 2).
     *
     * Bootstraps all services and reactive state used throughout the component.
     * Called once when the component is first mounted.
     *
     * Services injected:
     *   - orm          : Used to call Python model methods over JSON-RPC.
     *   - action       : Used to open Odoo windows (act_window) programmatically.
     *   - notification : Used to display success / warning / danger toasts.
     *
     * State shape:
     *   - phase           {string}  'idle' | 'running' | 'results' — controls which
     *                               section of the template is rendered.
     *   - stats           {object}  KPI numbers fetched from the server (rates, counts).
     *   - bankJournals    {Array}   List of {id, name} bank journal options for the picker.
     *   - selectedJournalId {number|null} Currently selected journal ID.
     *   - steps           {Array}   Copy of STEPS with a mutable `status` field
     *                               ('pending' | 'active' | 'done' | 'error').
     *   - currentStepDesc {string}  Live description shown under the stepper.
     *   - results         {object|null} Tri-category result payload from the server.
     *   - stepData        {object|null} Per-step drill-down data (step2…step5 tables).
     *   - analysisId      {number|null} ID of the vraja.bank.recon.analysis record.
     *   - analysisName    {string}  Display name of the analysis (e.g. "BRA/00015").
     *   - briefOpen       {boolean} Controls visibility of the collapsible Agent Brief.
     *   - activeAccordion {number|null} Which step accordion is currently expanded.
     *   - step7ActiveTab  {string}  Active tab in the Step 7 overview ('matched'|'rule'|'check').
     *   - isRunning       {boolean} Guard flag — prevents duplicate concurrent runs.
     */
    setup() {
        this.orm          = useService("orm");
        this.action       = useService("action");
        this.notification = useService("notification");

        this.state = proxy({
            // ── Dashboard phase ─────────────────────────────────────────────
            phase: "idle",          // 'idle' → 'running' → 'results'

            // ── KPI stats (populated by _loadDashboardData) ─────────────────
            stats: {
                total_lines:            0,
                reconciled_lines:       0,
                unreconciled_lines:     0,
                ai_matched:             0,
                rule_matched:           0,
                time_saved_formatted:   "0h 0m",
                reconciliation_rate:    0,
            },

            // ── Journal picker ───────────────────────────────────────────────
            bankJournals:       [],    // [{id, name}, …] — bank-type journals only
            selectedJournalId:  null,  // ID of the currently selected journal

            // ── 7-step animation ─────────────────────────────────────────────
            steps:           STEPS.map(s => ({ ...s, status: "pending" })),
            currentStepDesc: "",       // Live description rendered below stepper

            // ── Analysis results ─────────────────────────────────────────────
            results:      null,  // { matched:[], rule:[], check:[], journal_name }
            stepData:     null,  // { step2:{…}, step3:{…}, step4:{…}, step5:{…} }
            analysisId:   null,  // vraja.bank.recon.analysis record ID
            analysisName: "",    // e.g. "BRA/2026/00015"

            // ── UI toggles ───────────────────────────────────────────────────
            briefOpen:       true,  // Agent Brief collapsed/expanded
            activeAccordion: 1,     // Which step accordion is open (1-7 or null)
            step7ActiveTab:  "check", // Active sub-tab in Step 7 overview

            // ── Concurrency guard ────────────────────────────────────────────
            isRunning: false,  // Prevents double-clicking "Run AI Agent"
        });

        // Load KPI stats and last analysis result as soon as the component mounts.
        onWillStart(async () => {
            await this._loadDashboardData();
        });
    }


    // ───────────────────────────────────────────────────────────────────────────
    // DATA LOADING
    // ───────────────────────────────────────────────────────────────────────────

    /**
     * _loadDashboardData() — Fetches all data required to render the dashboard.
     *
     * Calls the server method `vraja.bank.recon.dashboard.data::get_dashboard_data`
     * which returns a single dict containing:
     *   - KPI counters (total_lines, reconciled_lines, unreconciled_lines, ai_matched,
     *     rule_matched, time_saved_formatted, reconciliation_rate)
     *   - bank_journals: list of bank-type journal options for the select picker
     *   - last_analysis: the most recent analysis result payload (or null)
     *
     * If a previous analysis exists, the dashboard is automatically restored to the
     * "results" phase so the user can see the last run without re-triggering the agent.
     *
     * Called:
     *   - Once during `onWillStart` (initial page load).
     *   - Again after a successful AI run to refresh KPI numbers.
     *
     * @returns {Promise<void>}
     */
    async _loadDashboardData() {
        const data = await this.orm.call(
            "vraja.bank.recon.dashboard.data",
            "get_dashboard_data",
            []
        );

        // Populate reactive KPI stats used by the three top header cards.
        this.state.stats = {
            total_lines:          data.total_lines,
            reconciled_lines:     data.reconciled_lines,
            unreconciled_lines:   data.unreconciled_lines,
            ai_matched:           data.ai_matched,
            rule_matched:         data.rule_matched,
            time_saved_formatted: data.time_saved_formatted,
            reconciliation_rate:  data.reconciliation_rate,
        };

        // Populate journal picker options; pre-select the first journal if none chosen yet.
        this.state.bankJournals = data.bank_journals || [];
        if (this.state.bankJournals.length && !this.state.selectedJournalId) {
            this.state.selectedJournalId = this.state.bankJournals[0].id;
        }

        // If the server returned a previous analysis, restore the results phase
        // so the user immediately sees the last run on dashboard load.
        if (data.last_analysis) {
            this.state.results      = data.last_analysis;
            this.state.stepData     = data.last_analysis.step_data || null;
            this.state.analysisId   = data.last_analysis.analysis_id;
            this.state.analysisName = data.last_analysis.analysis_name || "";
            this.state.phase        = "results";
        }
    }


    // ───────────────────────────────────────────────────────────────────────────
    // UTILITY
    // ───────────────────────────────────────────────────────────────────────────

    /**
     * sleep(ms) — Returns a Promise that resolves after `ms` milliseconds.
     *
     * Used to introduce deliberate delays between stepper animation steps so
     * each step is visually displayed for a human-readable duration before
     * transitioning to the next one.
     *
     * @param   {number}   ms - Duration in milliseconds.
     * @returns {Promise<void>}
     */
    sleep(ms) {
        return new Promise(resolve => setTimeout(resolve, ms));
    }

    /**
     * formatAmount(amount) — Formats a numeric amount into a locale string.
     *
     * Uses the Indian number format (en-IN) with exactly 2 decimal places.
     * Always returns the absolute value — negative amounts are shown without
     * a minus sign to keep table display clean.
     *
     * @param   {number} amount - Raw numeric amount (can be negative or null/undefined).
     * @returns {string}        Formatted string, e.g. "1,02,345.67".
     */
    formatAmount(amount) {
        return new Intl.NumberFormat("en-IN", {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2,
        }).format(Math.abs(amount || 0));
    }


    // ───────────────────────────────────────────────────────────────────────────
    // COMPUTED TOTALS (getter properties)
    // ───────────────────────────────────────────────────────────────────────────

    /**
     * matchedTotal — Formatted sum of all "Matched" transaction amounts.
     *
     * Sums the `amount` field of every entry in `state.results.matched`.
     * Returns "0.00" if no analysis result is loaded yet.
     *
     * @returns {string} Formatted total amount string.
     */
    get matchedTotal() {
        if (!this.state.results) return "0.00";
        const sum = this.state.results.matched.reduce((s, l) => s + (l.amount || 0), 0);
        return this.formatAmount(sum);
    }

    /**
     * ruleTotal — Formatted sum of all "Rule-Based" transaction amounts.
     *
     * Sums the `amount` field of every entry in `state.results.rule`.
     * Returns "0.00" if no analysis result is loaded yet.
     *
     * @returns {string} Formatted total amount string.
     */
    get ruleTotal() {
        if (!this.state.results) return "0.00";
        const sum = this.state.results.rule.reduce((s, l) => s + (l.amount || 0), 0);
        return this.formatAmount(sum);
    }

    /**
     * checkTotal — Formatted sum of all "To-Check" transaction amounts.
     *
     * Sums the `amount` field of every entry in `state.results.check`.
     * Returns "0.00" if no analysis result is loaded yet.
     *
     * @returns {string} Formatted total amount string.
     */
    get checkTotal() {
        if (!this.state.results) return "0.00";
        const sum = this.state.results.check.reduce((s, l) => s + (l.amount || 0), 0);
        return this.formatAmount(sum);
    }


    // ───────────────────────────────────────────────────────────────────────────
    // UI EVENT HANDLERS
    // ───────────────────────────────────────────────────────────────────────────

    /**
     * onJournalChange(ev) — Handles the bank journal <select> change event.
     *
     * Reads the selected option value from the DOM event and updates the reactive
     * `selectedJournalId` state. The parsed integer is used as the argument to
     * `run_full_ai_analysis` and as the domain filter in the KPI card navigations.
     *
     * @param {Event} ev - Native DOM change event from the <select> element.
     */
    onJournalChange(ev) {
        this.state.selectedJournalId = parseInt(ev.target.value, 10);
    }

    /**
     * toggleBrief() — Toggles the collapsible "Agent Brief" section in the header.
     *
     * The brief explains to the user what the AI agent does and what each
     * classification (Matched / Rule-Based / To-Check) means.
     * Toggling is controlled by the `briefOpen` boolean flag in state.
     */
    toggleBrief() {
        this.state.briefOpen = !this.state.briefOpen;
    }

    /**
     * toggleAccordion(stepId) — Expands or collapses a step accordion panel.
     *
     * Implements a single-open accordion pattern: clicking the currently open
     * accordion closes it (sets activeAccordion to null); clicking any other
     * step opens it and implicitly closes the previously open one.
     *
     * @param {number} stepId - The 1-based step number (1 through 7).
     */
    toggleAccordion(stepId) {
        if (this.state.activeAccordion === stepId) {
            // Clicking the already-open accordion closes it.
            this.state.activeAccordion = null;
        } else {
            // Open the clicked accordion; OWL reactivity closes the previous one automatically.
            this.state.activeAccordion = stepId;
        }
    }

    /**
     * setStep7Tab(tabName) — Switches the active sub-tab in the Step 7 overview panel.
     *
     * Step 7 shows a tabbed view of all three result categories.
     * Valid tab names are: 'matched', 'rule', 'check'.
     *
     * @param {string} tabName - The tab key to activate.
     */
    setStep7Tab(tabName) {
        this.state.step7ActiveTab = tabName;
    }

    /**
     * runAgain() — Resets the dashboard back to the "idle" phase.
     *
     * Clears all analysis result data and resets the stepper to the initial
     * "pending" state so the user can trigger a fresh AI run on the same or
     * a different journal. The KPI stats are NOT reset — they reflect
     * historical data and are only refreshed after a new run completes.
     */
    runAgain() {
        this.state.phase        = "idle";
        this.state.results      = null;
        this.state.analysisId   = null;
        this.state.analysisName = "";
        this.state.steps        = STEPS.map(s => ({ ...s, status: "pending" }));
    }


    // ───────────────────────────────────────────────────────────────────────────
    // KPI CARD NAVIGATION ACTIONS
    // Each method opens a filtered Odoo list view relevant to the KPI card clicked.
    // ───────────────────────────────────────────────────────────────────────────

    /**
     * openAnalysisHistory() — Opens the full AI log history for bank reconciliation.
     *
     * Navigates to the `vraja.ai.log` list view filtered to records where
     * `vraja_common_log_store = 'bank_recon'`. This shows every historical
     * AI run regardless of outcome.
     *
     * Triggered by: "History" button in the dashboard header.
     */
    openAnalysisHistory() {
        this.action.doAction({
            type:      "ir.actions.act_window",
            name:      "AI Logs",
            res_model: "vraja.ai.log",
            domain:    [["vraja_common_log_store", "=", "bank_recon"]],
            views:     [[false, "list"], [false, "form"]],
        });
    }

    /**
     * openReconciliationRate() — Opens the list of reconciled bank statement lines.
     *
     * Navigates to `account.bank.statement.line` filtered to lines that have
     * already been reconciled (`is_reconciled = true`) for bank-type journals.
     * If a journal is selected on the dashboard, the domain is further scoped
     * to that specific journal.
     *
     * Triggered by: clicking the "Reconciliation Rate %" KPI card.
     */
    openReconciliationRate() {
        const domain = [
            ["is_reconciled", "=", true],
            ["journal_id.type", "in", ["bank"]],
        ];
        // Narrow down to the currently selected journal when available.
        if (this.state.selectedJournalId) {
            domain.push(["journal_id", "=", this.state.selectedJournalId]);
        }
        this.action.doAction({
            type:      "ir.actions.act_window",
            name:      "Reconciled Statement Lines",
            res_model: "account.bank.statement.line",
            views:     [[false, "list"], [false, "form"]],
            domain,
        });
    }

    /**
     * openUnreconciledLines() — Opens the list of pending unreconciled bank statement lines.
     *
     * Navigates to `account.bank.statement.line` filtered to lines that have
     * NOT yet been reconciled (`is_reconciled = false`) for bank-type journals.
     * If a journal is selected, the domain is scoped to that journal.
     *
     * Triggered by:
     *   - Clicking the "Unreconciled Lines" KPI card.
     *   - Clicking the "X Pending" button in the dashboard header (top-right).
     */
    openUnreconciledLines() {
        const domain = [
            ["is_reconciled", "=", false],
            ["journal_id.type", "in", ["bank"]],
        ];
        // Narrow down to the currently selected journal when available.
        if (this.state.selectedJournalId) {
            domain.push(["journal_id", "=", this.state.selectedJournalId]);
        }
        this.action.doAction({
            type:      "ir.actions.act_window",
            name:      "Unreconciled Statement Lines",
            res_model: "account.bank.statement.line",
            views:     [[false, "list"], [false, "form"]],
            domain,
        });
    }

    /**
     * openAIMatchedLines() — Opens AI log records that have been fully reconciled.
     *
     * Navigates to `vraja.ai.log` filtered to bank reconciliation logs where
     * `bank_recon_state = 'reconciled'`. This gives the user a historical view
     * of every AI run that has been confirmed and reconciled in Odoo.
     *
     * Triggered by: clicking the "AI Matched (All Time)" KPI card.
     */
    openAIMatchedLines() {
        this.action.doAction({
            type:      "ir.actions.act_window",
            name:      "AI Matched Logs",
            res_model: "vraja.ai.log",
            domain: [
                ["vraja_common_log_store", "=", "bank_recon"],
                ["bank_recon_state",       "=", "reconciled"],
            ],
            views: [[false, "list"], [false, "form"]],
        });
    }


    // ───────────────────────────────────────────────────────────────────────────
    // CORE: AI AGENT EXECUTION
    // ───────────────────────────────────────────────────────────────────────────

    /**
     * runAIAgent() — Triggers the full 7-step AI reconciliation analysis.
     *
     * Execution flow:
     *   1. Guard checks: abort if already running or no journal selected.
     *   2. Reset state: switch to 'running' phase, clear previous results,
     *      reset all stepper steps to 'pending'.
     *   3. Fire the RPC: call `run_full_ai_analysis` on the server in the
     *      background (non-awaited at this point).
     *   4. Animate stepper: loop through each of the 7 steps, marking them
     *      'active' then 'done' with a STEP_DELAY_MS pause in between.
     *      This runs in parallel with the server RPC.
     *   5. Await RPC result: once the animation loop finishes, await the
     *      server response.
     *   6. On success: populate results, switch to 'results' phase, refresh KPIs.
     *   7. On failure: mark last step 'error', show notification, revert to 'idle'.
     *
     * The parallel animation + RPC pattern ensures the UI feels responsive
     * even if the server takes longer than the total animation time.
     *
     * @returns {Promise<void>}
     */
    async runAIAgent() {
        // Guard: prevent duplicate concurrent runs (e.g., double-click).
        if (this.state.isRunning) return;

        // Guard: a journal must be selected before triggering the agent.
        if (!this.state.selectedJournalId) {
            this.notification.add("Please select a bank journal first.", { type: "warning" });
            return;
        }

        // ── 1. Reset state to the running phase ─────────────────────────────
        this.state.isRunning = true;
        this.state.phase     = "running";
        this.state.results   = null;
        this.state.steps     = STEPS.map(s => ({ ...s, status: "pending" }));

        // ── 2. Fire the server RPC in the background (non-blocking) ─────────
        // The Promise is stored so we can await it after the animation loop.
        const rpcPromise = this.orm.call(
            "vraja.bank.recon.dashboard.data",
            "run_full_ai_analysis",
            [this.state.selectedJournalId]
        );

        // ── 3. Animate through the 7 steps while the RPC runs in parallel ───
        for (let i = 0; i < STEPS.length; i++) {
            this.state.steps[i].status = "active";          // Highlight current step.
            this.state.currentStepDesc = STEPS[i].desc;     // Update the live description bar.
            if (i > 0) this.state.steps[i - 1].status = "done"; // Mark previous step done.
            await this.sleep(STEP_DELAY_MS);                // Hold for visual effect.
        }

        // ── 4. Await the server result and handle success / failure ──────────
        try {
            const result = await rpcPromise;

            // Mark the final step as done and briefly show a "complete" message.
            this.state.steps[6].status = "done";
            this.state.currentStepDesc = "Analysis complete!";
            await this.sleep(500);

            if (result && result.success) {
                // Populate reactive state with server result data.
                this.state.results      = result.results;
                this.state.stepData     = result.step_data || null;
                this.state.analysisId   = result.analysis_id;
                this.state.analysisName = result.analysis_name || "";
                this.state.phase        = "results";
                this.state.activeAccordion = 1; // Default to Step 1 accordion open.

                // Refresh the header KPI cards to reflect the newly reconciled data.
                await this._loadDashboardData();

                this.notification.add(
                    `✅ Analysis ${result.analysis_name} completed successfully!`,
                    { type: "success" }
                );
            } else {
                // Server returned a non-success response (e.g., no statement lines found).
                this.state.steps[6].status = "error";
                this.notification.add(
                    result.error || "AI Analysis failed. Please try again.",
                    { type: "danger" }
                );
                await this.sleep(1200);
                this.state.phase = "idle"; // Revert so the user can try again.
            }
        } catch (err) {
            // Network error or unhandled Python exception on the server side.
            this.state.steps[6].status = "error";
            this.state.currentStepDesc = "An error occurred.";
            this.notification.add("An error occurred during AI analysis.", { type: "danger" });
            console.error("BankReconDashboard.runAIAgent:", err);
            await this.sleep(1200);
            this.state.phase = "idle"; // Revert so the user can try again.
        } finally {
            // Always release the running guard, regardless of outcome.
            this.state.isRunning = false;
        }
    }


    // ───────────────────────────────────────────────────────────────────────────
    // CONFIRM & REVIEW
    // ───────────────────────────────────────────────────────────────────────────

    /**
     * confirmAndReview() — Finalises the AI analysis and triggers Odoo reconciliation.
     *
     * Calls `vraja.bank.recon.dashboard.data::confirm_and_review` with the current
     * `analysisId`. The server performs the following actions:
     *   - Auto-reconciles all "Matched" lines (exact journal item counterparts found).
     *   - Sends "Rule-Based" lines to Odoo's native reconciliation widget with a
     *     suggested write-off account (e.g., bank charges, fees).
     *   - Leaves "To-Check" lines unreconciled for manual human review.
     *
     * On success, the server returns an `ir.actions.act_window` payload that opens
     * the Odoo bank reconciliation view for any remaining outstanding items.
     *
     * @returns {Promise<void>}
     */
    async confirmAndReview() {
        // Guard: no analysis to confirm if analysisId is not set.
        if (!this.state.analysisId) return;

        try {
            const result = await this.orm.call(
                "vraja.bank.recon.dashboard.data",
                "confirm_and_review",
                [this.state.analysisId]
            );

            if (result && result.success && result.action) {
                this.notification.add("Reconciliation completed successfully!", { type: "success" });
                // Navigate to the server-provided action (Odoo's bank reconciliation widget).
                this.action.doAction(result.action);
            } else {
                this.notification.add(
                    result.error || "Could not complete reconciliation.",
                    { type: "danger" }
                );
            }
        } catch (err) {
            this.notification.add("Error during reconciliation.", { type: "danger" });
            console.error("confirmAndReview:", err);
        }
    }
}

// ═══════════════════════════════════════════════════════════════════════════════
// REGISTRATION
// ═══════════════════════════════════════════════════════════════════════════════

/**
 * Link the OWL component class to its XML template.
 * The template name must match the `t-name` attribute in bank_recon_dashboard.xml.
 */
BankReconDashboard.template = "vraja_bank_recon.Dashboard";

/**
 * Register the component as a client action so Odoo's action manager
 * can render it when the menu item or button with tag "vraja_bank_recon.dashboard"
 * is triggered (defined in bank_recon_dashboard_actions.xml).
 */
registry.category("actions").add("vraja_bank_recon.dashboard", BankReconDashboard);