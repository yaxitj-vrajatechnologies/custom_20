import { registry } from "@web/core/registry";
import { user } from "@web/core/user";
import { _t } from "@web/core/l10n/translation";
import { getReportUrl } from "@web/webclient/actions/reports/utils";
import { PdfOptionsModal } from "./pdf_options_modal";

/**
 * Intercepts PDF report actions. If the report is configured to print via
 * PrintNode and the printer is online, ask the user how to proceed; otherwise
 * return false so the standard report handling (download) runs unchanged.
 */
async function printnodeReportHandler(action, options, env) {
    if (action.report_type !== "qweb-pdf" || action.print_type === "download") {
        return false;
    }
    const info = await env.services.orm.call(
        "ir.actions.report",
        "printnode_print_action_for_report",
        [action.report_name]
    );
    if (!info || info.action !== "printnode") {
        return false;
    }
    const notify = (message, type) =>
        env.services.notification.add(message, { type, sticky: false });

    if (!info.is_online) {
        notify(_t("Please connect to this printer %s", info.printer_name), "warning");
        return true;
    }
    if (!info.is_color_printer && info.is_qweb_color_print) {
        notify(_t("This report is color printed. Please select color printer %s", info.printer_name), "warning");
        return true;
    }
    if (info.is_color_printer && !info.is_qweb_color_print) {
        notify(_t("This report is not color printed. Please select normal printer %s", info.printer_name), "warning");
        return true;
    }

    let choice = action.print_type;
    let copies = 1;
    if (!choice) {
        const result = await new Promise((resolve) => {
            env.services.dialog.add(
                PdfOptionsModal,
                { onSelectOption: (option, n) => resolve({ option, copies: n }) },
                { onClose: () => resolve({ option: "close" }) }
            );
        });
        choice = result.option;
        copies = result.copies || 1;
    }
    if (choice === "close") {
        return true;
    }
    if (choice === "open") {
        window.open(getReportUrl(action, "pdf", user.context));
        return true;
    }

    env.services.ui.block();
    try {
        await env.services.orm.call(
            "ir.actions.report",
            "direct_document_print",
            [action.id || info.report_id, action.report_name, action.context?.active_ids || []],
            {
                data: { ...(action.data || {}), value_number: copies },
                context: action.context || {},
            }
        );
        notify(_t("Document sent to the printer %s", info.printer_name), "info");
    } finally {
        env.services.ui.unblock();
    }
    if (options?.onClose) {
        options.onClose();
    }
    return true;
}

registry
    .category("ir.actions.report handlers")
    .add("printnode_odoo_connector.print", printnodeReportHandler);
