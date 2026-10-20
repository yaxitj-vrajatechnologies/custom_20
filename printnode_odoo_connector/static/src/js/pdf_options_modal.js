import { Component, signal, t, useProps } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";

export class PdfOptionsModal extends Component {
    static template = "printnode_odoo_connector.PdfOptionsModal";
    static components = { Dialog };

    // Owl 3: the static `props` / `defaultProps` are ignored, the schema is declared with useProps.
    // `close` is injected by the dialog service, `onSelectOption` is passed by the report handler.
    props = useProps({
        close: t.function(),
        onSelectOption: t.function(),
    });

    // Owl 3: `useState` was removed and `t-model` needs a signal (a proxy is not accepted).
    copies = signal(1);

    select(option) {
        const copies = Math.min(100, Math.max(1, parseInt(this.copies(), 10) || 1));
        this.props.onSelectOption(option, copies);
        this.props.close();
    }
}
