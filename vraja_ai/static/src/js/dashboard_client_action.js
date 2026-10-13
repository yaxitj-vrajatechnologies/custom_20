/** @odoo-module **/

import {registry} from "@web/core/registry";
import {Component, onMounted, useState} from "@odoo/owl";
import {useService} from "@web/core/utils/hooks";

export class VrajaAIDashboard extends Component {

    setup() {
        this.orm = useService("orm");

        this.state = useState({
            store: false,
            cardId: this.props.action?.params?.card_id,
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
                    icon.classList.remove("fa-chevron-up");
                    icon.classList.add("fa-chevron-down");
                });

                target.addEventListener("hide.bs.collapse", function () {
                    icon.classList.remove("fa-chevron-down");
                    icon.classList.add("fa-chevron-up");
                });
            }
        });
    }
}


VrajaAIDashboard.template = "vraja_ai_dashboard_template";

registry.category("actions").add("vraja_ai_dashboard_template", VrajaAIDashboard);
