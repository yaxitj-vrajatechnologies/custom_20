/** @odoo-module **/

/* Chat-only browser enhancements.  The RPC/button action remains Odoo's
 * standard form action, so the MCP/OpenAI request flow is not altered. */

/* ---- Ctrl/Cmd + Enter sends the message, like a normal chat app ---- */
document.addEventListener("keydown", (event) => {
    if (!(event.ctrlKey || event.metaKey) || event.key !== "Enter") {
        return;
    }
    const prompt = event.target.closest(".mcp_chat_composer textarea");
    if (!prompt) {
        return;
    }
    const form = prompt.closest(".mcp_chat_form");
    const sendButton = form?.querySelector(".mcp_chat_composer .mcp_chat_run:not([disabled])");
    if (sendButton) {
        event.preventDefault();
        sendButton.click();
    }
});

/* ---- Turn the read-only "allow_read/create/write/unlink" checkboxes into
 * clear "Allowed" / "Not allowed" badges.  The underlying Odoo widgets stay
 * in the DOM and remain the single source of truth. */
function syncPermissionRow(row) {
    const checkbox = row.querySelector(".mcp_chat_permission_value input[type='checkbox']");
    const valueHost = row.querySelector(".mcp_chat_permission_value");
    if (!checkbox || !valueHost) {
        return;
    }
    const allowed = checkbox.checked;
    let badge = valueHost.querySelector(".mcp_chat_permission_badge");
    if (!badge) {
        badge = document.createElement("span");
        badge.className = "mcp_chat_permission_badge";
        valueHost.appendChild(badge);
    }
    const label = allowed ? "Allowed" : "Not allowed";
    if (badge.textContent !== label) {
        badge.textContent = label;
    }
    badge.classList.toggle("is-allowed", allowed);
    badge.classList.toggle("is-denied", !allowed);
}

function syncAllPermissionRows() {
    document.querySelectorAll(".mcp_chat_permissions .mcp_chat_permission_row").forEach(syncPermissionRow);
}

/* ---- Send button: disabled (not hidden) until an instruction is typed.
 * mcpSendInFlight is a plain variable (not a DOM dataset) on purpose: Owl
 * replaces the .mcp_chat_composer/.mcp_chat_run nodes while the button's
 * action is running (that's what drives the "Loading" indicator), and a
 * flag stored on the old node's dataset is lost the moment that happens -
 * which is exactly what let the button re-enable mid-request. ---- */
let mcpSendInFlight = false;
let mcpAssistantMessageCountAtSend = 0;
const MCP_SCROLL_TO_LATEST_KEY = "vraja_mcp.scroll_to_latest";

function scrollToLatestResponseAfterReload() {
    const targetAssistantMessageCount = Number(
        sessionStorage.getItem(MCP_SCROLL_TO_LATEST_KEY)
    );
    if (!targetAssistantMessageCount) {
        return;
    }
    const histories = document.querySelectorAll(".mcp_chat_history");
    if (!histories.length) {
        return;
    }
    const assistantMessageCount = document.querySelectorAll(
        ".mcp_chat_history .mcp_chat_assistant"
    ).length;
    if (assistantMessageCount < targetAssistantMessageCount) {
        return;
    }
    histories.forEach((history) => {
        history.scrollTop = history.scrollHeight;
    });
    sessionStorage.removeItem(MCP_SCROLL_TO_LATEST_KEY);
}

function scrollHistoryToBottomOnFirstRender() {
    document.querySelectorAll(".mcp_chat_history").forEach((history) => {
        if (history._mcpScrolledInitially) {
            return;
        }
        if (!history.querySelector(".mcp_chat_message")) {
            return;
        }
        history._mcpScrolledInitially = true;
        history.scrollTop = history.scrollHeight;
    });
}

function releaseSendLockAfterResponse() {
    const assistantMessageCount = document.querySelectorAll(
        ".mcp_chat_history .mcp_chat_assistant"
    ).length;
    if (mcpSendInFlight && assistantMessageCount > mcpAssistantMessageCountAtSend) {
        mcpSendInFlight = false;
    }
}

function syncSendButtonState() {
    document.querySelectorAll(".mcp_chat_form .mcp_chat_composer").forEach((composer) => {
        const prompt = composer.querySelector("textarea");
        const sendButton = composer.querySelector(".mcp_chat_run");
        if (!prompt || !sendButton) {
            return;
        }
        const hasText = prompt.value.trim().length > 0;
        const hasAttachment = composer.querySelectorAll(
            "[name='attachment_ids'] .o_attachment, [name='attachment_ids'] .oe_attachment"
        ).length > 0;
        const canSend = hasText || hasAttachment;
        sendButton.disabled = !canSend || mcpSendInFlight;
        sendButton.classList.toggle("mcp_chat_run_disabled", !canSend || mcpSendInFlight);
    });
}

function lockComposerInputs(locked) {
    document.querySelectorAll(".mcp_chat_form .mcp_chat_composer").forEach((composer) => {
        const prompt = composer.querySelector("textarea");
        if (prompt) {
            prompt.readOnly = locked;
            prompt.classList.toggle("mcp_chat_locked", locked);
        }
        const attachmentField = composer.querySelector("[name='attachment_ids']");
        if (attachmentField) {
            attachmentField.classList.toggle("mcp_chat_locked", locked);
            attachmentField
                .querySelectorAll("button, input[type='file'], .o_attachment, .oe_attachment, [role='button']")
                .forEach((el) => {
                    el.disabled = locked;
                });
        }
    });
}

function syncOperationOptions() {
    const field = document.getElementById("mcp_chat_operation_field");
    const select = field?.querySelector("select");
    const permissions = document.querySelector(".mcp_chat_permissions");
    if (!select) {
        return;
    }
    if (!select._mcpOperationOptions) {
        select._mcpOperationOptions = Array.from(select.options).map((option) => ({
            value: option.value,
            label: option.text,
        }));
    }
    if (!permissions) {
        if (select.options.length) {
            select.replaceChildren();
        }
        return;
    }

    const allowedFor = {};
    permissions.querySelectorAll(".mcp_chat_permission_row").forEach((row) => {
        const key = row.dataset.permission;
        const checkbox = row.querySelector(".mcp_chat_permission_value input[type='checkbox']");
        allowedFor[key] = !!checkbox?.checked;
    });

    const selectedValue = select.value;
    const allowedOptions = select._mcpOperationOptions.filter(
        (option) => option.value && allowedFor[option.value]
    );

    // Do not leave hidden/disabled options behind: only permitted operations
    // are inserted into the dropdown for the currently selected model.
    const displayedValues = Array.from(select.options).map((option) => option.value);
    const allowedValues = allowedOptions.map((option) => option.value);
    if (displayedValues.join("\u0000") !== allowedValues.join("\u0000")) {
        select.replaceChildren(...allowedOptions.map((option) => {
            const element = document.createElement("option");
            element.value = option.value;
            element.textContent = option.label;
            return element;
        }));
    }

    const nextValue = allowedOptions.some((option) => option.value === selectedValue)
        ? selectedValue
        : allowedOptions[0]?.value || "";
    if (select.value !== nextValue) {
        select.value = nextValue;
        select.dispatchEvent(new Event("change", {bubbles: true}));
    }
}

function syncAll() {
    // The history field can be fully replaced after Odoo receives the RPC
    // response.  Check the complete chat, not only an old history node.
    releaseSendLockAfterResponse();
    syncAllPermissionRows();
    syncOperationOptions();
    syncHistoryObservers();
    watchForErrorDialogs();
    syncSendButtonState();
    lockComposerInputs(mcpSendInFlight);
    scrollToLatestResponseAfterReload();
    scrollHistoryToBottomOnFirstRender();
}

document.addEventListener("input", (event) => {
    if (event.target.matches(".mcp_chat_composer textarea")) {
        syncSendButtonState();
    }
});

document.addEventListener("click", (event) => {
    if (event.target.closest(".mcp_chat_history .mcp_chat_message_content, .mcp_chat_history .mcp_chat_bubble_header")) {
        event.stopPropagation();
    }
}, true);

document.addEventListener("click", (event) => {
    const sendButton = event.target.closest(".mcp_chat_composer .mcp_chat_run");
    if (!sendButton) {
        return;
    }
    if (mcpSendInFlight) {
        event.preventDefault();
        event.stopPropagation();
        return;
    }
    if (sendButton.disabled) {
        return;
    }
    mcpSendInFlight = true;
    mcpAssistantMessageCountAtSend = document.querySelectorAll(
        ".mcp_chat_history .mcp_chat_assistant"
    ).length;
    sessionStorage.setItem(
        MCP_SCROLL_TO_LATEST_KEY,
        String(mcpAssistantMessageCountAtSend + 1)
    );
    sendButton.disabled = true;
    sendButton.classList.add("mcp_chat_run_disabled");
    lockComposerInputs(true);
}, true)

/* ---- Clear the lock only when a new assistant answer is rendered.  Kanban
 * also mutates while Odoo shows the button-loading state, so clearing on any
 * DOM mutation would re-enable Send while the API request is still running. */
function watchHistoryForCompletion(historyEl) {
    if (historyEl._mcpCompletionObserver) {
        return;
    }
    const observer = new MutationObserver(() => {
        const assistantMessageCount = historyEl.querySelectorAll(".mcp_chat_assistant").length;
        if (mcpSendInFlight && assistantMessageCount > mcpAssistantMessageCountAtSend) {
            mcpSendInFlight = false;
            syncSendButtonState();
        }
    });
    observer.observe(historyEl, {childList: true, subtree: true});
    historyEl._mcpCompletionObserver = observer;
}

function syncHistoryObservers() {
    document.querySelectorAll(".mcp_chat_history_kanban").forEach(watchHistoryForCompletion);
}

// Form fields are mounted/replaced by Owl after model changes.  Observe those
// renders instead of polling, so a single typed character updates Send at once
// and the operation list is refreshed as soon as MCP rights arrive.
const chatObserver = new MutationObserver((mutations) => {
    if (mutations.some((mutation) => mutation.type === "childList" || mutation.type === "attributes")) {
        syncAll();
    }
});

function watchForErrorDialogs() {
    const container = document.querySelector(".o_dialog_container") || document.body;
    if (container._mcpErrorDialogObserver) {
        return;
    }
    const observer = new MutationObserver((mutations) => {
        if (!mcpSendInFlight) {
            return;
        }
        mutations.forEach((mutation) => {
            mutation.removedNodes.forEach((node) => {
                if (node.nodeType === 1 && node.matches?.(".modal, .o_dialog")) {
                    mcpSendInFlight = false;
                    lockComposerInputs(false);
                    syncSendButtonState();
                }
            });
        });
    });
    observer.observe(container, {childList: true, subtree: true});
    container._mcpErrorDialogObserver = observer;
}

document.addEventListener("DOMContentLoaded", () => {
    watchForErrorDialogs();
    syncAll();
    chatObserver.observe(document.body, {
        childList: true,
        subtree: true,
        attributes: true,
        attributeFilter: ["checked", "value"],
    });
});

// Odoo updates related boolean fields from the model onchange without always
// replacing their checkbox DOM node.  Recheck them briefly so the operation
// list follows that onchange immediately, before the form is saved.
setInterval(syncAll, 250);
