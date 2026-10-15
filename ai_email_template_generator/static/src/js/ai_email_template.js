/** @odoo-module **/

import {Component, proxy, useProps, onWillStart, onWillUnmount} from "@odoo/owl";
import {registry} from "@web/core/registry";
import {standardFieldProps} from "@web/views/fields/standard_field_props";
import {patch} from "@web/core/utils/patch";
import {FormController} from "@web/views/form/form_controller";

class AiCardSelector extends Component {
    static template = "ai_email_template_generator.AiCardSelector";
    props = useProps({...standardFieldProps});

    setup() {
        this.state = proxy({
            selected: this.props.record.data[this.props.name]
        });
    }

    selectCard(value) {
        this.props.record.update({[this.props.name]: value});
        this.state.selected = value;
    }

    isSelected(value) {
        return this.props.record.data[this.props.name] === value;
    }
}

registry.category("fields").add("ai_card_selector", {
    component: AiCardSelector,
});

patch(FormController.prototype, {
    async beforeExecuteActionButton(params) {
        if (params.name === "action_generate_template" || params.name === "action_regenerate") {
            await this.model.root.update({state: "running"});
        }
        return super.beforeExecuteActionButton(...arguments);
    },
    async afterExecuteActionButton(params) {
        if (params.name === "action_generate_template" || params.name === "action_regenerate") {
            const state = this.model.root.data.state;
            if (state === "failed" || state === "running") {
                await this.model.root.update({state: "draft"});
            }
        }
        return super.afterExecuteActionButton(...arguments);
    }

});
