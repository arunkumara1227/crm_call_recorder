"""SQL-view model aggregating `crm.call.recording` by `created_by_api_key_id`.

One row per **device** (= one `crm.call.api.key`). Used to render the
device-aggregated Recordings dashboard kanban — one card per connected
phone. Drill-down opens a tabbed form (Call Recordings + WhatsApp Messages).

(File name kept as `phone_summary.py` because models/__init__.py already
imports it; internal model is `crm.call.device.summary`.)
"""

from odoo import api, fields, models, tools


class CrmCallDeviceSummary(models.Model):
    _name = 'crm.call.device.summary'
    _description = 'CRM Call Recordings — Per-Device Summary'
    _auto = False
    _order = 'last_call_at desc'
    _rec_name = 'device_name'

    api_key_id = fields.Many2one(
        'crm.call.api.key', string='Device', readonly=True,
    )
    device_name = fields.Char(
        string='Device Name', related='api_key_id.name', readonly=True, store=False,
    )
    employee_id = fields.Many2one(
        'hr.employee', string='Employee',
        related='api_key_id.employee_id', readonly=True, store=False,
    )

    total_calls = fields.Integer(string='Total Calls', readonly=True)
    incoming_count = fields.Integer(string='Incoming', readonly=True)
    outgoing_count = fields.Integer(string='Outgoing', readonly=True)
    total_duration_sec = fields.Integer(string='Total Duration (s)', readonly=True)

    last_call_at = fields.Datetime(string='Last Call', readonly=True)
    first_call_at = fields.Datetime(string='First Call', readonly=True)

    avg_tone_score = fields.Float(string='Avg Tone Score', readonly=True, digits=(5, 1))
    harsh_calls_count = fields.Integer(string='Harsh Calls', readonly=True)

    done_transcripts_count = fields.Integer(string='Transcribed Calls', readonly=True)
    unique_contacts_count = fields.Integer(string='Unique Contacts', readonly=True)

    last_contact_phone = fields.Char(string='Last Contact', readonly=True)
    last_sim_label = fields.Char(string='Last SIM', readonly=True)

    # ─── Tab data sources (computed at view-render time) ───────────────
    recording_ids = fields.Many2many(
        'crm.call.recording', compute='_compute_recording_ids',
        string='Call Recordings',
    )

    # Stat-button counts (computed; light queries, hit each form render)
    wa_message_count = fields.Integer(
        compute='_compute_wa_stats', string='WA Messages',
    )
    wa_tone_count = fields.Integer(
        compute='_compute_wa_stats', string='WA Tone Records',
    )
    wa_log_count = fields.Integer(
        compute='_compute_wa_stats', string='WA Comm Logs',
    )
    wa_employee_session_id = fields.Many2one(
        'wa.employee.session', compute='_compute_wa_employee_session',
        string='WA Employee Session',
    )

    @api.depends('api_key_id')
    def _compute_recording_ids(self):
        Recording = self.env['crm.call.recording'].sudo()
        for rec in self:
            if rec.api_key_id:
                rec.recording_ids = Recording.search(
                    [('created_by_api_key_id', '=', rec.api_key_id.id)],
                    order='call_date desc',
                )
            else:
                rec.recording_ids = Recording

    @api.depends('api_key_id')
    def _compute_wa_employee_session(self):
        WaSession = self.env.get('wa.employee.session')
        for rec in self:
            if WaSession is None or not rec.api_key_id or not rec.api_key_id.employee_id:
                rec.wa_employee_session_id = False
                continue
            sess = WaSession.sudo().search(
                [('employee_id', '=', rec.api_key_id.employee_id.id)], limit=1,
            )
            rec.wa_employee_session_id = sess.id if sess else False

    @api.depends('wa_employee_session_id')
    def _compute_wa_stats(self):
        WaMessage = self.env.get('whatsapp.message')
        WaTone = self.env.get('wa.message.tone')
        WaLog = self.env.get('wa.communication.log')
        for rec in self:
            session = rec.wa_employee_session_id
            if not session:
                rec.wa_message_count = 0
                rec.wa_tone_count = 0
                rec.wa_log_count = 0
                continue
            # Messages
            if WaMessage is not None and session.session_id:
                rec.wa_message_count = WaMessage.sudo().search_count(
                    [('session_id', '=', session.session_id.id)],
                )
            else:
                rec.wa_message_count = 0
            # Tones
            if WaTone is not None:
                rec.wa_tone_count = WaTone.sudo().search_count(
                    [('employee_session_id', '=', session.id)],
                )
            else:
                rec.wa_tone_count = 0
            # Communication logs
            if WaLog is not None:
                rec.wa_log_count = WaLog.sudo().search_count(
                    [('employee_session_id', '=', session.id)],
                )
            else:
                rec.wa_log_count = 0

    # ─── Stat-button navigation actions ────────────────────────────────

    def action_open_wa_chat_view(self):
        """Open WA tracker's existing wa_chat_split_view scoped to this
        device's wa.employee.session. Reuses the right-panel Call Recordings
        feature we already wired in."""
        self.ensure_one()
        session = self.wa_employee_session_id
        if not session:
            return False
        # WA tracker's wa.employee.session.action_open_chats returns the
        # client action pre-configured for that session.
        if hasattr(session.sudo(), 'action_open_chats'):
            return session.sudo().action_open_chats()
        return {
            'type': 'ir.actions.client',
            'tag': 'wa_chat_split_view',
            'name': f'Chats — {session.employee_id.name}',
            'context': {
                'active_id': session.id,
                'default_employee_session_id': session.id,
            },
        }

    def action_open_wa_tones(self):
        self.ensure_one()
        session = self.wa_employee_session_id
        if not session:
            return False
        return {
            'type': 'ir.actions.act_window',
            'name': f'WA Tones — {session.employee_id.name}',
            'res_model': 'wa.message.tone',
            'view_mode': 'list,form',
            'domain': [('employee_session_id', '=', session.id)],
            'target': 'current',
        }

    def action_open_wa_logs(self):
        self.ensure_one()
        session = self.wa_employee_session_id
        if not session:
            return False
        return {
            'type': 'ir.actions.act_window',
            'name': f'Comm Logs — {session.employee_id.name}',
            'res_model': 'wa.communication.log',
            'view_mode': 'list,form',
            'domain': [('employee_session_id', '=', session.id)],
            'target': 'current',
        }

    def action_open_wa_session(self):
        self.ensure_one()
        session = self.wa_employee_session_id
        if not session:
            return False
        return {
            'type': 'ir.actions.act_window',
            'name': 'WhatsApp Session',
            'res_model': 'wa.employee.session',
            'res_id': session.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def init(self):
        # Drop the legacy phone-aggregated view from the previous iteration.
        self.env.cr.execute("DROP VIEW IF EXISTS crm_call_phone_summary CASCADE")
        tools.drop_view_if_exists(self.env.cr, self._table)
        # Start from crm_call_api_key so paired-but-no-recording devices
        # still produce a row (with all counters at 0). LEFT JOIN to
        # recordings + tones means a freshly registered device shows up
        # immediately, before its first upload.
        self.env.cr.execute(f"""
            CREATE OR REPLACE VIEW {self._table} AS
            SELECT
                ak.id::int AS id,
                ak.id AS api_key_id,
                COALESCE(COUNT(rec.id), 0)::int AS total_calls,
                COUNT(*) FILTER (WHERE rec.direction = 'incoming')::int AS incoming_count,
                COUNT(*) FILTER (WHERE rec.direction = 'outgoing')::int AS outgoing_count,
                COALESCE(SUM(rec.duration_seconds), 0)::int AS total_duration_sec,
                MAX(rec.call_date) AS last_call_at,
                MIN(rec.call_date) AS first_call_at,
                AVG(tone.tone_score)::float AS avg_tone_score,
                COUNT(tone.id) FILTER (WHERE tone.tone_label = 'Hard')::int AS harsh_calls_count,
                COUNT(*) FILTER (WHERE rec.transcription_status = 'done')::int AS done_transcripts_count,
                COUNT(DISTINCT rec.phone_digits)::int AS unique_contacts_count,
                (array_agg(rec.phone ORDER BY rec.call_date DESC NULLS LAST))[1] AS last_contact_phone,
                (array_agg(rec.sim_label ORDER BY rec.call_date DESC NULLS LAST)
                    FILTER (WHERE rec.sim_label IS NOT NULL AND rec.sim_label <> ''))[1] AS last_sim_label
            FROM crm_call_api_key ak
            LEFT JOIN crm_call_recording rec ON rec.created_by_api_key_id = ak.id
            LEFT JOIN crm_call_tone tone ON tone.recording_id = rec.id
            WHERE ak.active = true
            GROUP BY ak.id
        """)

    def action_open_device_recordings(self):
        """Drill-down: open the per-device form showing two notebook tabs
        (Call Recordings + WhatsApp Messages)."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.device_name or 'Device',
            'res_model': 'crm.call.device.summary',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'current',
        }
