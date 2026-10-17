/** @odoo-module **/

import {registry} from "@web/core/registry";
import * as owl from "@odoo/owl";
import {useService} from "@web/core/utils/hooks";

const {Component, onMounted} = owl;
// Odoo 20 (Owl 3): useState hata hai, uski jagah proxy hai
const makeState = owl.useState || owl.proxy;

export class VrajaAIDashboard extends Component {

    setup() {
        this.orm = useService("orm");

        this.state = makeState({
            store: false,
            cardId: this.props?.action?.params?.card_id,
        });

        onMounted(async () => {
            await this.loadCardStore();
            this.setupCollapseToggles();
        });
    }

    async loadCardStore() {
        if (!this.state.cardId) {
            return;
        }

        const [card] = await this.orm.read(
            "vraja.ai.card",
            [this.state.cardId],
            ["vraja_common_store"]
        );

        this.state.store = card?.vraja_common_store || false;
    }

    setupCollapseToggles() {
        const toggles = document.querySelectorAll(".dashboard-toggle");

        toggles.forEach((toggle) => {
            const targetSelector = toggle.getAttribute("data-bs-target");
            const target = document.querySelector(targetSelector);
            const icon = toggle.querySelector(".toggle-icon");

            if (target && icon) {
                target.addEventListener("show.bs.collapse", function () {
                    icon.setAttribute("data-icon", "expand_more");
                });

                target.addEventListener("hide.bs.collapse", function () {
                    icon.setAttribute("data-icon", "expand_less");
                });
            }
        });
    }
}


VrajaAIDashboard.template = "vraja_ai_dashboard_template";

registry.category("actions").add("vraja_ai_dashboard_template", VrajaAIDashboard);
