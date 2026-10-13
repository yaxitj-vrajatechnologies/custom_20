/** @odoo-module **/

/**
 * Extends drag-and-drop file upload to the ENTIRE chat composer block
 * (".mcp_chat_composer": the "Message" textarea where the instruction is
 * typed, the attachment_ids many2many_binary field, and the footer/Send
 * button) instead of only the many2many_binary widget's own small drop
 * strip.
 *
 * Dropping a file anywhere on the composer - including directly onto the
 * textarea while typing an instruction, or onto the footer/Send button area
 * - is forwarded to the hidden <input type="file"> that the many2many_binary
 * widget already renders for "attachment_ids", exactly as if the user had
 * clicked "Attach" and picked the file(s) themselves. The widget then adds
 * the attachment chip(s) the normal Odoo way, so the rest of the module
 * (send-button enable/disable, attachment lock while sending, etc. in
 * mcp_chat.js) keeps working unchanged.
 *
 * CAPTURE PHASE: same reasoning as many2many_binary_dragdrop.js. Odoo's web
 * client also listens for dragover/drop higher up the DOM to stop the
 * browser's default "open dropped file in a new tab" behaviour, and that
 * code can call stopPropagation(). A bubble-phase listener on document would
 * then never fire, so every listener here is registered with capture=true,
 * which runs top-down before any bubble-phase handler can block it.
 *
 * DRAG COUNTER: the composer has several children (label, textarea,
 * attachments row, footer, Send button...). Moving the pointer from one
 * child to another fires dragleave on the child being left even though the
 * pointer never actually left the composer, which would flicker the
 * highlight off mid-drag. A per-composer enter/leave counter (rather than a
 * simple boolean) fixes that: the highlight is only cleared once the
 * composer's net enter/leave count returns to zero.
 */

const COMPOSER_SELECTOR = ".mcp_chat_composer";
const DRAGOVER_CLASS = "mcp_composer_dragover";

function getComposer(target) {
    return target && target.closest ? target.closest(COMPOSER_SELECTOR) : null;
}

function isComposerLocked(composer) {
    // mcp_chat.js sets textarea.readOnly (and adds .mcp_chat_locked) while a
    // request is in flight; don't accept drops in that state.
    const textarea = composer.querySelector("textarea");
    return !!textarea && textarea.readOnly;
}

function getAttachmentFileInput(composer) {
    return composer.querySelector("[name='attachment_ids'] input[type='file']");
}

document.addEventListener(
    "dragenter",
    (ev) => {
        const composer = getComposer(ev.target);
        if (!composer || isComposerLocked(composer)) {
            return;
        }
        ev.preventDefault();
        composer._mcpDragCounter = (composer._mcpDragCounter || 0) + 1;
        composer.classList.add(DRAGOVER_CLASS);
    },
    true
);

document.addEventListener(
    "dragover",
    (ev) => {
        const composer = getComposer(ev.target);
        if (!composer || isComposerLocked(composer)) {
            return;
        }
        // Required so the browser allows a "drop" event to fire here at all.
        ev.preventDefault();
        if (ev.dataTransfer) {
            ev.dataTransfer.dropEffect = "copy";
        }
    },
    true
);

document.addEventListener(
    "dragleave",
    (ev) => {
        const composer = getComposer(ev.target);
        if (!composer) {
            return;
        }
        composer._mcpDragCounter = Math.max(0, (composer._mcpDragCounter || 0) - 1);
        if (composer._mcpDragCounter === 0) {
            composer.classList.remove(DRAGOVER_CLASS);
        }
    },
    true
);

document.addEventListener(
    "drop",
    (ev) => {
        const composer = getComposer(ev.target);
        if (!composer) {
            return;
        }
        ev.preventDefault();
        ev.stopPropagation();
        composer._mcpDragCounter = 0;
        composer.classList.remove(DRAGOVER_CLASS);

        if (isComposerLocked(composer)) {
            return;
        }

        const files = ev.dataTransfer && ev.dataTransfer.files;
        if (!files || !files.length) {
            return;
        }

        const input = getAttachmentFileInput(composer);
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

// If a drag leaves the browser window entirely (or the user cancels it with
// Esc), no dragleave with a matching enter ever reaches the composer, so the
// highlight and counter would otherwise get stuck on. Clear them globally
// whenever a drag operation ends anywhere on the page.
document.addEventListener(
    "dragend",
    () => {
        document.querySelectorAll(COMPOSER_SELECTOR + "." + DRAGOVER_CLASS).forEach((composer) => {
            composer._mcpDragCounter = 0;
            composer.classList.remove(DRAGOVER_CLASS);
        });
    },
    true
);
