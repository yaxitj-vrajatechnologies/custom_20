/** @odoo-module **/

import publicWidget from "@web/legacy/js/public/public_widget";
import { rpc } from "@web/core/network/rpc";

publicWidget.registry.CleaningForm = publicWidget.Widget.extend({

    selector: '.cleaning-form-card',

    async start() {

        await this._super(...arguments);

        // ─────────────────────────────
        // Recurring Toggle
        // ─────────────────────────────

        const checkbox = this.el.querySelector('#is_recurring');
        const recurringFields = this.el.querySelector('#recurring_fields');
        const endDate = this.el.querySelector('[name="end_date"]');
        const countrySelect = this.el.querySelector('#country_select');
        const stateWrapper = this.el.querySelector('#state_wrapper');
        const stateSelect = this.el.querySelector('#state_select');

        if (checkbox && recurringFields) {
            const toggleFields = () => {
                const isChecked = checkbox.checked;
                recurringFields.style.display = checkbox.checked ? 'block' : 'none';
                endDate.required = isChecked;
            };
            checkbox.addEventListener('change', toggleFields);
            toggleFields();
        }
        if (countrySelect && stateWrapper && stateSelect) {
            const filterStates = () => {
                const selectedCountry = countrySelect.value;

                stateWrapper.style.display = selectedCountry ? 'block' : 'none';

                Array.from(stateSelect.options).forEach(option => {
                    if (!option.value) return;

                    const optionCountry = option.dataset.countryId;
                    option.hidden = optionCountry !== selectedCountry;
                });

                stateSelect.value = '';
            };

            countrySelect.addEventListener('change', filterStates);
            filterStates();
        }

        // ─────────────────────────────
        // Slot Filter by Shift
        // ─────────────────────────────

        const shiftSelect = this.el.querySelector('[name="cleaning_shift_id"]');
        const slotSelect  = this.el.querySelector('[name="shift_slot_id"]');

        if (shiftSelect && slotSelect) {

            shiftSelect.addEventListener('change', async function () {

                const shiftId = this.value;

                slotSelect.innerHTML =
                    '<option value="">-- Select Slot --</option>';

                if (!shiftId) {
                    return;
                }

                const response = await fetch('/cleaning/get_slots', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        jsonrpc: '2.0',
                        method: 'call',
                        id: 1,
                        params: {
                            shift_id: parseInt(shiftId)
                        },
                    }),
                });

                const data = await response.json();

                const slots = data.result || [];

                if (slots.length) {

                    slots.forEach(sl => {

                        const opt = document.createElement('option');

                        opt.value = sl.id;
                        opt.textContent = sl.name;

                        slotSelect.appendChild(opt);
                    });

                } else {

                    slotSelect.innerHTML =
                        '<option value="">-- No slots available --</option>';
                }
            });
        }

        // ─────────────────────────────
        // Preferred Date Disable Logic
        // ─────────────────────────────

        const preferredDateInput =
            this.el.querySelector('.preferred-date-input');

        if (preferredDateInput) {

            const res = await rpc('/cleaning/get_disabled_dates', {});

            const weeklyOffDays =
                res.weekly_off_days || [];

            const disabledDates =
                res.disabled_dates || [];

            $(preferredDateInput).datepicker({

                // dateFormat: 'yy-mm-dd',
                dateFormat: 'dd/mm/yy',

                minDate: 0,

                beforeShowDay: function(date) {

                    // JS:
                    // Sunday = 0
                    // Monday = 1

                    let jsDay = date.getDay();

                    // Convert to Python style
                    // Monday = 0
                    // Sunday = 6

                    let convertedDay =
                        jsDay === 0 ? 6 : jsDay - 1;

                    // Disable weekly off

                    if (weeklyOffDays.includes(convertedDay)) {
                        return [false];
                    }

                    // Format date

                    const year = date.getFullYear();

                    const month =
                        String(date.getMonth() + 1).padStart(2, '0');

                    const day =
                        String(date.getDate()).padStart(2, '0');

                    const formattedDate =
                        `${year}-${month}-${day}`;

                    // Disable exception holidays

                    if (disabledDates.includes(formattedDate)) {
                        return [false];
                    }

                    return [true];
                }
            });

            // Open datepicker on icon click

            const calendarBtn =
                this.el.querySelector('.calendar-trigger');

            if (calendarBtn) {

                calendarBtn.addEventListener('click', () => {

                    $(preferredDateInput).datepicker('show');
                });
            }

            // Open on input click too

            preferredDateInput.addEventListener('click', () => {

                $(preferredDateInput).datepicker('show');
            });
        }

        // ─────────────────────────────
        // End Date Picker
        // ─────────────────────────────

        const endDateInput =
            this.el.querySelector('.end-date-input');

        if (endDateInput) {

            $(endDateInput).datepicker({

                dateFormat: 'dd/mm/yy',

                // Disable past dates
                minDate: 0,
            });

            // Open on icon click

            const endCalendarBtn =
                this.el.querySelector('.end-calendar-trigger');

            if (endCalendarBtn) {

                endCalendarBtn.addEventListener('click', () => {

                    $(endDateInput).datepicker('show');
                });
            }

            // Open on input click

            endDateInput.addEventListener('click', () => {

                $(endDateInput).datepicker('show');
            });
        }
    },
});