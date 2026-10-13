/** @odoo-module **/

/**
 * Drag & drop support for the upload field of the AI Vendor Pricelist
 * Update form:
 *   - vendor_file            (Vendor Pricelist File)
 *
 * The standard Odoo "binary" widget only offers an "Upload your file"
 * button. This script lets the user drop a file straight onto the field; the
 * file is handed to the widget's own hidden <input type="file"> and a
 * "change" event is fired, so Odoo processes it exactly as if it had been
 * chosen with the button (data + filename fields are filled as usual).
 *
 * If the field already contains a file, the drop replaces it: the widget's
 * own "clear" button is pressed first, then the new file is dropped in once
 * the upload input is available again.
 *
 * Listeners are attached in the CAPTURE phase (trailing "true") so that
 * Odoo's own drag/drop handling cannot stop them with stopPropagation().
 */

const FIELD_NAMES = ["vendor_file"];
const FIELD_SELECTOR = FIELD_NAMES.map(
    (name) => `.o_field_widget[name="${name}"]`
).join(",");
const FILE_INPUT_SELECTOR = 'input[type="file"]';
const CLEAR_BUTTON_SELECTOR = ".o_clear_file_button";

function getContainer(target) {
    return target && target.closest ? target.closest(FIELD_SELECTOR) : null;
}

function hasFiles(ev) {
    const types = ev.dataTransfer && ev.dataTransfer.types;
    return !!types && Array.from(types).includes("Files");
}

function isDroppable(container) {
    return !!(
        container.querySelector(FILE_INPUT_SELECTOR) ||
        container.querySelector(CLEAR_BUTTON_SELECTOR)
    );
}

function setHighlight(container, on) {
    container.classList.toggle("o_binary_dragdrop_active", on);
}

function assignFile(input, file) {
    // Only one file is accepted by a binary field.
    const dt = new DataTransfer();
    dt.items.add(file);
    input.files = dt.files;
    input.dispatchEvent(new Event("change", { bubbles: true }));
}

function waitForInputAndAssign(fieldName, file, tries) {
    const container = document.querySelector(
        `.o_field_widget[name="${fieldName}"]`
    );
    const input = container && container.querySelector(FILE_INPUT_SELECTOR);
    if (input) {
        assignFile(input, file);
        return;
    }
    if (tries < 20) {
        setTimeout(() => waitForInputAndAssign(fieldName, file, tries + 1), 50);
    }
}

document.addEventListener(
    "dragenter",
    (ev) => {
        const container = getContainer(ev.target);
        if (!container || !hasFiles(ev)) {
            return;
        }
        ev.preventDefault();
        if (isDroppable(container)) {
            setHighlight(container, true);
        }
    },
    true
);

document.addEventListener(
    "dragover",
    (ev) => {
        const container = getContainer(ev.target);
        if (!container || !hasFiles(ev)) {
            return;
        }
        // Required so the browser allows a "drop" event to fire here at all.
        ev.preventDefault();
        if (isDroppable(container)) {
            setHighlight(container, true);
        }
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
        // Ignore moves between children of the same field (avoids flicker).
        if (ev.relatedTarget && container.contains(ev.relatedTarget)) {
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
        if (!container || !hasFiles(ev)) {
            return;
        }
        ev.preventDefault();
        ev.stopPropagation();
        setHighlight(container, false);

        const file = ev.dataTransfer.files && ev.dataTransfer.files[0];
        if (!file) {
            return;
        }

        const input = container.querySelector(FILE_INPUT_SELECTOR);
        if (input) {
            assignFile(input, file);
            return;
        }

        // A file is already set: clear it, then drop the new one in.
        const clearButton = container.querySelector(CLEAR_BUTTON_SELECTOR);
        if (!clearButton) {
            return; // read-only field: nothing to do
        }
        clearButton.click();
        waitForInputAndAssign(container.getAttribute("name"), file, 0);
    },
    true
);
