/** @odoo-module **/

import { Component, useState, useRef, onWillStart, onMounted, onWillUnmount } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

class WaChatView extends Component {
    static template = "crm_call_recorder.ChatView";
    static props = { "*": true };

    setup() {
        this.messagesRef = useRef("messagesContainer");

        this.state = useState({
            conversations: [],
            messages: [],
            selectedConvId: null,
            searchQuery: "",
            loading: false,
            employeeSessionId: null,
            employeeSessions: [],
        });

        // Priority: context > localStorage
        const contextId = (this.props.action && this.props.action.context && this.props.action.context.active_employee_session_id) || null;
        let savedId = null;
        try { savedId = localStorage.getItem("wa_tracker_emp_session"); } catch(e) {}
        let savedConv = null;
        try { savedConv = localStorage.getItem("wa_tracker_conv_id"); } catch(e) {}

        this.state.employeeSessionId = contextId || (savedId ? parseInt(savedId) : null);
        this._pendingConvId = savedConv ? parseInt(savedConv) : null;

        // If opened from dashboard, save the employee session
        if (contextId) {
            try { localStorage.setItem("wa_tracker_emp_session", String(contextId)); } catch(e) {}
        }

        // ─── Real-time push via bus.bus ──────────────────────────────
        // Server fires "wa.message.created" notifications on the
        // "wa.tracker.update" channel after every whatsapp.message create.
        // We subscribe here and re-fetch the affected conversation so the
        // operator doesn't need to click Refresh.
        try {
            this.busService = useService("bus_service");
            this._busHandler = this._onBusNotification.bind(this);
            this.busService.addChannel("wa.tracker.update");
            this.busService.addEventListener("notification", this._busHandler);
        } catch (e) {
            // bus_service should always be present on Odoo 17+. If it isn't,
            // log + carry on — manual Refresh still works.
            console.warn("WaChatView: bus_service unavailable; live updates disabled.", e);
        }

        onWillStart(async () => {
            await this.loadEmployeeSessions();
            await this.loadConversations();
        });

        onMounted(() => {
            if (this._pendingConvId) {
                const id = this._pendingConvId;
                if (this.state.conversations.find(c => c.id === id)) {
                    this.selectConversation(id);
                }
            }
        });

        onWillUnmount(() => {
            if (this.busService && this._busHandler) {
                try {
                    this.busService.removeEventListener("notification", this._busHandler);
                } catch (e) {}
            }
        });
    }

    // ──────────────────────────────────────────────────────────────────
    // Bus push handler
    // ──────────────────────────────────────────────────────────────────

    _onBusNotification({ detail }) {
        if (!Array.isArray(detail)) return;
        for (const { type, payload } of detail) {
            if (type !== "wa.message.created") continue;
            this._handleIncomingMessage(payload || {});
        }
    }

    _handleIncomingMessage(payload) {
        const incomingDigits = String(payload.phone || "").replace(/\D/g, "");
        if (!incomingDigits) return;

        // Case 1 — message belongs to the conversation currently being viewed.
        const openPhone = String(this.selectedConvPhone || "").replace(/\D/g, "");
        if (openPhone && this._phoneMatches(openPhone, incomingDigits)) {
            this.refreshMessages();
            return;
        }
        // Case 2 — message belongs to a known conversation in the sidebar.
        const conv = this.state.conversations.find((c) => {
            const d = String(c.phone || "").replace(/\D/g, "");
            return this._phoneMatches(d, incomingDigits);
        });
        if (conv) {
            // Local-only unread bump — immediate visual feedback, no HTTP.
            conv.unread_count = (conv.unread_count || 0) + 1;
            return;
        }
        // Case 3 — brand-new conversation. Re-pull the sidebar list so the
        // new row appears.
        this.loadConversations();
    }

    _phoneMatches(a, b) {
        if (!a || !b) return false;
        if (a === b) return true;
        // Tolerate country-code mismatches — match on last 10 digits.
        return a.length >= 10 && b.length >= 10 && a.slice(-10) === b.slice(-10);
    }

    _saveState() {
        try {
            if (this.state.employeeSessionId) {
                localStorage.setItem("wa_tracker_emp_session", String(this.state.employeeSessionId));
            } else {
                localStorage.removeItem("wa_tracker_emp_session");
            }
            if (this.state.selectedConvId) {
                localStorage.setItem("wa_tracker_conv_id", String(this.state.selectedConvId));
            } else {
                localStorage.removeItem("wa_tracker_conv_id");
            }
        } catch(e) {}
    }

    async _jsonRpc(url, params) {
        const response = await fetch(url, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                jsonrpc: "2.0",
                method: "call",
                id: Date.now(),
                params: params || {},
            }),
        });
        const data = await response.json();
        if (data.error) {
            console.error("RPC Error:", data.error);
            return [];
        }
        return data.result;
    }

    async loadEmployeeSessions() {
        try {
            const result = await this._jsonRpc("/wa_tracker/employee_sessions", {});
            this.state.employeeSessions = result || [];

            // Auto-select if only one session exists
            if (!this.state.employeeSessionId && this.state.employeeSessions.length === 1) {
                this.state.employeeSessionId = this.state.employeeSessions[0].id;
                this._saveState();
            }
        } catch (e) {
            console.error("Failed to load employee sessions:", e);
        }
    }

    async loadConversations() {
        try {
            const result = await this._jsonRpc("/wa_tracker/conversations", {
                employee_session_id: this.state.employeeSessionId,
            });
            this.state.conversations = result || [];
        } catch (e) {
            console.error("Failed to load conversations:", e);
        }
    }

    async onEmployeeChange(ev) {
        const val = ev.target.value;
        this.state.employeeSessionId = val ? parseInt(val) : null;
        this.state.selectedConvId = null;
        this.state.messages = [];
        this._saveState();
        await this.loadConversations();
    }

    async selectConversation(convId) {
        this.state.selectedConvId = convId;
        this.state.loading = true;
        this._saveState();

        try {
            const result = await this._jsonRpc("/wa_tracker/messages", {
                conversation_id: convId,
            });
            this.state.messages = result || [];
            setTimeout(() => {
                const container = this.messagesRef.el;
                if (container) {
                    container.scrollTop = container.scrollHeight;
                }
            }, 100);
        } catch (e) {
            console.error("Failed to load messages:", e);
        }
        this.state.loading = false;
    }

    async refreshMessages() {
        if (this.state.selectedConvId) {
            await this.selectConversation(this.state.selectedConvId);
        }
    }

    get filteredConversations() {
        const q = (this.state.searchQuery || "").toLowerCase();
        if (!q) return this.state.conversations;
        return this.state.conversations.filter(
            (c) =>
                (c.contact_name || "").toLowerCase().includes(q) ||
                (c.phone || "").includes(q)
        );
    }

    get selectedConvName() {
        const conv = this.state.conversations.find(c => c.id === this.state.selectedConvId);
        return conv ? conv.contact_name : "";
    }

    get selectedConvPhone() {
        const conv = this.state.conversations.find(c => c.id === this.state.selectedConvId);
        return conv ? conv.phone : "";
    }

    get selectedConvEmployee() {
        const conv = this.state.conversations.find(c => c.id === this.state.selectedConvId);
        return conv ? conv.employee_name : "";
    }

    formatTime(dateStr) {
        if (!dateStr || dateStr === "False" || dateStr === "false") return "";
        try {
            const d = new Date(dateStr.replace(" ", "T"));
            if (isNaN(d.getTime())) return "";
            const now = new Date();
            const isToday = d.toDateString() === now.toDateString();
            if (isToday) {
                return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
            }
            const yesterday = new Date(now);
            yesterday.setDate(yesterday.getDate() - 1);
            if (d.toDateString() === yesterday.toDateString()) {
                return "Yesterday";
            }
            return d.toLocaleDateString([], { month: "short", day: "numeric" });
        } catch {
            return "";
        }
    }

    onSearchInput(ev) {
        this.state.searchQuery = ev.target.value;
    }
}

registry.category("actions").add("wa_chat_split_view", WaChatView, { force: true });
