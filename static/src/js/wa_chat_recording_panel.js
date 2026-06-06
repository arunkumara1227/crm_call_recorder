/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { registry } from "@web/core/registry";

/**
 * Patch wa_chat_split_view (whatsapp_employee_tracker.WaChatView) to also
 * load + display call recordings for the currently-selected chat contact,
 * in a 3rd right-side panel rendered by our XML template inherit.
 *
 * WaChatView isn't exported in its source file, so we pull the class out
 * of the actions registry where whatsapp_employee_tracker registered it.
 */
const WaChatView = registry.category("actions").get("wa_chat_split_view", null);

if (WaChatView) {
    patch(WaChatView.prototype, {
        setup() {
            super.setup();
            this.state.callRecordings = [];
            this.state.callRecordingsLoading = false;
        },

        async selectConversation(convId) {
            await super.selectConversation(convId);
            await this._loadCallRecordings();
        },

        async _loadCallRecordings() {
            const phone = this.selectedConvPhone;
            if (!phone) {
                this.state.callRecordings = [];
                return;
            }
            this.state.callRecordingsLoading = true;
            try {
                const result = await this._jsonRpc(
                    "/crm_call_recorder/chat_recordings_for_phone",
                    {
                        phone: phone,
                        employee_session_id: this.state.employeeSessionId,
                    },
                );
                this.state.callRecordings = (result && result.recordings) || [];
            } catch (e) {
                console.warn("[crm_call_recorder] recordings fetch failed:", e);
                this.state.callRecordings = [];
            } finally {
                this.state.callRecordingsLoading = false;
            }
        },
    });
} else {
    console.warn(
        "[crm_call_recorder] WaChatView not in registry — call-recordings " +
        "panel disabled. Is whatsapp_employee_tracker installed?",
    );
}
