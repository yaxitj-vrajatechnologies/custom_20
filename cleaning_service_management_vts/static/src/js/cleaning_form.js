/** @odoo-module **/

import { Interaction } from "@web/public/interaction";
import { registry } from "@web/core/registry";
import { rpc } from "@web/core/network/rpc";

export class CleaningForm extends Interaction {
    static selector = ".cleaning-form-card";

    dynamicContent = {
        "#is_recurring": { "t-on-change": () => this.toggleRecurring() },
        "#country_select": { "t-on-change": () => this.filterStates() },
        "[name='cleaning_shift_id']": { "t-on-change": (ev) => this.onShiftChange(ev) },
        ".preferred-date-input": { "t-on-change": (ev) => this.onPreferredDateChange(ev) },
        ".calendar-trigger:not(.end-calendar-trigger)": {
            "t-on-click": () => this.showPicker(".preferred-date-input"),
        },
        ".end-calendar-trigger": {
            "t-on-click": () => this.showPicker(".end-date-input"),
        },
    };

    async willStart() {
        this.weeklyOffDays = [];
        this.disabledDates = [];
        if (this.el.querySelector(".preferred-date-input")) {
            try {
                const res = await rpc("/cleaning/get_disabled_dates", {});
                this.weeklyOffDays = res.weekly_off_days || [];
                this.disabledDates = res.disabled_dates || [];
            } catch (e) {
                console.error("get_disabled_dates failed", e);
            }
        }
    }

    start() {
        const today = this._today();
        for (const sel of [".preferred-date-input", ".end-date-input"]) {
            const input = this.el.querySelector(sel);
            if (input) {
                input.min = today;
                // after a validation error the server sends back dd/mm/yyyy
                input.value = this._toIso(input.value);
            }
        }
        this.toggleRecurring();
        this.filterStates();
    }

    _today() {
        const d = new Date();
        const p = (n) => String(n).padStart(2, "0");
        return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
    }

    _toIso(value) {
        const m = /^(\d{2})\/(\d{2})\/(\d{4})$/.exec(value || "");
        return m ? `${m[3]}-${m[2]}-${m[1]}` : value || "";
    }

    showPicker(selector) {
        const input = this.el.querySelector(selector);
        if (!input) {
            return;
        }
        try {
            input.showPicker();
        } catch (e) {
            input.focus();
        }
    }

    toggleRecurring() {
        const checkbox = this.el.querySelector("#is_recurring");
        const recurringFields = this.el.querySelector("#recurring_fields");
        const endDate = this.el.querySelector('[name="end_date"]');
        if (checkbox && recurringFields) {
            recurringFields.style.display = checkbox.checked ? "block" : "none";
            if (endDate) {
                endDate.required = checkbox.checked;
            }
        }
    }

    filterStates() {
        const countrySelect = this.el.querySelector("#country_select");
        const stateWrapper = this.el.querySelector("#state_wrapper");
        const stateSelect = this.el.querySelector("#state_select");
        if (countrySelect && stateWrapper && stateSelect) {
            const selectedCountry = countrySelect.value;
            stateWrapper.style.display = selectedCountry ? "block" : "none";
            Array.from(stateSelect.options).forEach((option) => {
                if (!option.value) {
                    return;
                }
                option.hidden = option.dataset.countryId !== selectedCountry;
            });
            stateSelect.value = "";
        }
    }

    async onShiftChange(ev) {
        const slotSelect = this.el.querySelector('[name="shift_slot_id"]');
        if (!slotSelect) {
            return;
        }
        const shiftId = ev.target.value;
        slotSelect.innerHTML = '<option value="">-- Select Slot --</option>';
        if (!shiftId) {
            return;
        }
        let slots = [];
        try {
            slots = (await this.waitFor(rpc("/cleaning/get_slots", { shift_id: parseInt(shiftId) }))) || [];
        } catch (e) {
            console.error("get_slots failed", e);
        }
        if (slots.length) {
            slots.forEach((sl) => {
                const opt = document.createElement("option");
                opt.value = sl.id;
                opt.textContent = sl.name;
                slotSelect.appendChild(opt);
            });
        } else {
            slotSelect.innerHTML = '<option value="">-- No slots available --</option>';
        }
    }

    onPreferredDateChange(ev) {
        const input = ev.target;
        input.setCustomValidity("");
        if (!input.value) {
            return;
        }
        const [y, m, d] = input.value.split("-").map(Number);
        const jsDay = new Date(y, m - 1, d).getDay();
        const pyDay = jsDay === 0 ? 6 : jsDay - 1; // Monday = 0
        if (this.weeklyOffDays.includes(pyDay) || this.disabledDates.includes(input.value)) {
            input.setCustomValidity("This date is not available for booking.");
            input.reportValidity();
            input.value = "";
        }
    }
}

registry.category("public.interactions").add("cleaning_service_management_vts.cleaning_form", CleaningForm);
