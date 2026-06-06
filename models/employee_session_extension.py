"""Extend `wa.employee.session` with call-channel computed fields so the
unified Communications Dashboard kanban can show WhatsApp AND Call stats
side-by-side per employee.

Mirrors the WA-side compute pattern from
[crm_call_recorder.models.employee_session.WaEmployeeSession],
keeping the kanban visually symmetric (Total / Out today / In today /
Harsh + tone score + last call).
"""

from datetime import datetime

from odoo import api, fields, models


class WaEmployeeSessionCallExtension(models.Model):
    _inherit = 'wa.employee.session'

    # ─── Bridge ─────────────────────────────────────────────────────────
    call_api_key_ids = fields.One2many(
        'crm.call.api.key', 'employee_id',
        string='Call Recorder API Keys',
        related='employee_id.call_api_key_ids',
        readonly=True,
    )

    # ─── Computed call-channel stats (stored for kanban grouping) ───────
    total_call_recordings = fields.Integer(
        compute='_compute_call_stats', store=True, string='Total Calls',
    )
    calls_today_in = fields.Integer(
        compute='_compute_call_today_stats', store=True, string='Calls In Today',
    )
    calls_today_out = fields.Integer(
        compute='_compute_call_today_stats', store=True, string='Calls Out Today',
    )
    harsh_calls_count = fields.Integer(
        compute='_compute_call_tone_stats', store=True, string='Harsh Calls',
    )
    call_avg_tone_score = fields.Float(
        compute='_compute_call_tone_stats', store=True, string='Call Tone Score',
        digits=(5, 1),
    )
    last_call_at = fields.Datetime(
        compute='_compute_call_stats', store=True, string='Last Call',
    )
    avg_call_duration_sec = fields.Float(
        compute='_compute_call_stats', store=True, string='Avg Call Duration (s)',
        digits=(8, 1),
    )

    @api.depends('employee_id', 'call_api_key_ids')
    def _compute_call_stats(self):
        Recording = self.env['crm.call.recording'].sudo()
        for rec in self:
            key_ids = rec.call_api_key_ids.ids
            if not key_ids:
                rec.total_call_recordings = 0
                rec.last_call_at = False
                rec.avg_call_duration_sec = 0.0
                continue
            domain = [('created_by_api_key_id', 'in', key_ids)]
            recordings = Recording.search(domain)
            rec.total_call_recordings = len(recordings)
            if recordings:
                rec.last_call_at = max(recordings.mapped('call_date') or [False])
                durations = [r.duration_seconds or 0 for r in recordings]
                rec.avg_call_duration_sec = (sum(durations) / len(durations)) if durations else 0.0
            else:
                rec.last_call_at = False
                rec.avg_call_duration_sec = 0.0

    @api.depends('employee_id', 'call_api_key_ids')
    def _compute_call_today_stats(self):
        Recording = self.env['crm.call.recording'].sudo()
        today_start = datetime.combine(fields.Date.today(), datetime.min.time())
        for rec in self:
            key_ids = rec.call_api_key_ids.ids
            if not key_ids:
                rec.calls_today_in = 0
                rec.calls_today_out = 0
                continue
            base_domain = [
                ('created_by_api_key_id', 'in', key_ids),
                ('call_date', '>=', fields.Datetime.to_string(today_start)),
            ]
            rec.calls_today_in = Recording.search_count(
                base_domain + [('direction', '=', 'incoming')]
            )
            rec.calls_today_out = Recording.search_count(
                base_domain + [('direction', '=', 'outgoing')]
            )

    @api.depends('employee_id', 'call_api_key_ids')
    def _compute_call_tone_stats(self):
        Tone = self.env['crm.call.tone'].sudo()
        for rec in self:
            key_ids = rec.call_api_key_ids.ids
            if not key_ids:
                rec.harsh_calls_count = 0
                rec.call_avg_tone_score = 0.0
                continue
            domain = [
                ('recording_id.created_by_api_key_id', 'in', key_ids),
            ]
            tones = Tone.search(domain)
            rec.harsh_calls_count = len(tones.filtered(lambda t: t.tone_label == 'Hard'))
            if tones:
                scores = tones.mapped('tone_score')
                rec.call_avg_tone_score = (sum(scores) / len(scores)) if scores else 0.0
            else:
                rec.call_avg_tone_score = 0.0

    def action_view_call_recordings_from_session(self):
        """Stat-button on the form: open Recordings filtered to this
        employee's devices."""
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id(
            'crm_call_recorder.action_crm_call_recording'
        )
        action['domain'] = [
            ('created_by_api_key_id', 'in', self.call_api_key_ids.ids),
        ]
        return action
