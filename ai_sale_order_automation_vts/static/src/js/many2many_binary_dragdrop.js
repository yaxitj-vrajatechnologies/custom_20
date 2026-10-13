/** @odoo-module **/

/**
 * Adds drag-and-drop support to every many2many_binary widget on the page
 * (this includes attachment_ids on the AI Sale Order Draft form).
 *
 * Confirmed DOM structure (from live inspection of this build):
 *
 * <div name="attachment_ids" class="o_field_widget ... o_field_many2many_binary">
 *   <div class="oe_fileupload">
 *     <div class="o_attachments"></div>
 *     <div class="oe_add">
 *       <span class="o_file_input">
 *         <span class="o_file_input_trigger">
 *           <button class="btn btn-secondary o_attach">...Source Files</button>
 *         </span>
 *         <input type="file" name="ufile" class="o_input_file d-none" multiple accept="*">
 *       </span>
 *     </div>
 *   </div>
 * </div>
 *
 * IMPORTANT: listeners are attached in the CAPTURE phase (the trailing
 * "true"), not the default bubble phase. Odoo's web client attaches its own
 * dragover/drop handling higher up the tree (to stop the browser's default
 * "open dropped file in a new tab" behaviour), and that code can call
 * stopPropagation(). A bubble-phase listener on document would never fire in
 * that case. Capture phase runs top-down BEFORE any bubble-phase code, so it
 * cannot be blocked that way.
 */

const FIELD_SELECTOR = ".o_field_many2many_binary";

function getContainer(target) {
    return target && target.closest ? target.closest(FIELD_SELECTOR) : null;
}

function setHighlight(container, on) {
    container.classList.toggle("o_m2m_dragdrop_active", on);
}

document.addEventListener(
    "dragenter",
    (ev) => {
        const container = getContainer(ev.target);
        if (!container) {
            return;
        }
        ev.preventDefault();
        setHighlight(container, true);
    },
    true
);

document.addEventListener(
    "dragover",
    (ev) => {
        const container = getContainer(ev.target);
        if (!container) {
            return;
        }
        // Required so the browser allows a "drop" event to fire here at all.
        ev.preventDefault();
        setHighlight(container, true);
    },
    true
);

document.addEventListener(
    "dragleave",
    (ev) => {
        const container = getContainer(ev.target);
        if (!container) {
            return;
        }
        setHighlight(container, false);
    },
    true
);

document.addEventListener(
    "drop",
    (ev) => {
        const container = getContainer(ev.target);
        if (!container) {
            return;
        }
        ev.preventDefault();
        ev.stopPropagation();
        setHighlight(container, false);

        const files = ev.dataTransfer && ev.dataTransfer.files;
        if (!files || !files.length) {
            return;
        }

        const input = container.querySelector("input[type=file]");
        if (!input) {
            return;
        }

        try {
            // dataTransfer.files is already a FileList; modern browsers allow
            // assigning it straight onto an <input type="file">.
            input.files = files;
        } catch (e) {
            const dt = new DataTransfer();
            for (const file of files) {
                dt.items.add(file);
            }
            input.files = dt.files;
        }

        input.dispatchEvent(new Event("change", { bubbles: true }));
    },
    true
);
