"""Tone Report wizard — interactive dashboard with date + agent + phone filters.

Ported from `crm_call_recorder.wa.tone.report` with two adaptations:
- Filter dimension is `crm.call.api.key` ("Arun Infinx" etc.) instead of `hr.employee`.
- Added optional `phone_contains` Char for ad-hoc narrowing within an agent's calls.

Date-range bounds logic is verbatim from WA tracker.
"""

import datetime
from datetime import timedelta

from odoo import api, fields, models


class CrmCallToneReport(models.TransientModel):
    _name = 'crm.call.tone.report'
    _description = 'CRM Call Tone Report'

    channel = fields.Selection([
        ('calls', 'Call Recordings only'),
        ('whatsapp', 'WhatsApp Messages only'),
        ('both', 'Both channels combined'),
    ], string='Channel', default='calls', required=True,
       help='Which conversation channel to analyse. WhatsApp counts come '
            'from `wa.message.tone` filtered to the agent\'s employee, '
            'resolved via api_key.employee_id → wa.employee.session.')

    api_key_id = fields.Many2one(
        'crm.call.api.key', string='Agent (device)', required=True,
        help='Which device/agent uploaded the calls. Created in '
             'Call Recorder → API Keys. For WhatsApp counts, the linked '
             'employee\'s wa.employee.session is used.',
    )
    date_range = fields.Selection([
        ('today',         'Today'),
        ('yesterday',     'Yesterday'),
        ('this_week',     'This Week'),
        ('previous_week', 'Previous Week'),
        ('this_month',    'This Month'),
        ('last_month',    'Last Month'),
        ('custom',        'Custom Range'),
    ], string='Date Range', default='today', required=True)
    date_from = fields.Date(string='From')
    date_to = fields.Date(string='To')

    phone_contains = fields.Char(
        'Phone contains',
        help='Optional. Narrow the report to calls whose number contains '
             'these digits (e.g. last 5 digits of a contact).',
    )

    count_soft = fields.Integer(string='Soft / Polite', compute='_compute_counts')
    count_neutral = fields.Integer(string='Neutral', compute='_compute_counts')
    count_hard = fields.Integer(string='Hard / Critical', compute='_compute_counts')
    count_total = fields.Integer(string='Total Analyzed', compute='_compute_counts')

    # Per-channel breakdown (used by the Both-mode tile sub-buttons)
    count_soft_calls = fields.Integer(compute='_compute_counts')
    count_neutral_calls = fields.Integer(compute='_compute_counts')
    count_hard_calls = fields.Integer(compute='_compute_counts')
    count_soft_wa = fields.Integer(compute='_compute_counts')
    count_neutral_wa = fields.Integer(compute='_compute_counts')
    count_hard_wa = fields.Integer(compute='_compute_counts')

    @api.depends('channel', 'api_key_id', 'date_range', 'date_from', 'date_to', 'phone_contains')
    def _compute_counts(self):
        CallTone = self.env['crm.call.tone']
        WaTone = self.env.get('wa.message.tone')
        for rec in self:
            # Reset all
            rec.count_soft_calls = rec.count_neutral_calls = rec.count_hard_calls = 0
            rec.count_soft_wa = rec.count_neutral_wa = rec.count_hard_wa = 0
            if not rec.api_key_id:
                rec.count_soft = rec.count_neutral = rec.count_hard = 0
                rec.count_total = 0
                continue

            # ─── Calls side ───────────────────────────────
            if rec.channel in ('calls', 'both'):
                call_domain = rec._get_base_domain()
                rec.count_soft_calls = CallTone.search_count(call_domain + [('tone_label', '=', 'Soft')])
                rec.count_neutral_calls = CallTone.search_count(call_domain + [('tone_label', '=', 'Neutral')])
                rec.count_hard_calls = CallTone.search_count(call_domain + [('tone_label', '=', 'Hard')])

            # ─── WhatsApp side ────────────────────────────
            if rec.channel in ('whatsapp', 'both') and WaTone is not None:
                wa_domain = rec._get_wa_base_domain()
                if wa_domain is not None:
                    rec.count_soft_wa = WaTone.sudo().search_count(wa_domain + [('tone_label', '=', 'Soft')])
                    rec.count_neutral_wa = WaTone.sudo().search_count(wa_domain + [('tone_label', '=', 'Neutral')])
                    rec.count_hard_wa = WaTone.sudo().search_count(wa_domain + [('tone_label', '=', 'Hard')])

            rec.count_soft = rec.count_soft_calls + rec.count_soft_wa
            rec.count_neutral = rec.count_neutral_calls + rec.count_neutral_wa
            rec.count_hard = rec.count_hard_calls + rec.count_hard_wa
            rec.count_total = rec.count_soft + rec.count_neutral + rec.count_hard

    def _get_date_bounds(self):
        """Translate `date_range` into concrete `(from_date, to_date)`. Verbatim
        from WA tracker's logic."""
        self.ensure_one()
        today = fields.Date.context_today(self)
        dr = self.date_range or 'today'
        if dr == 'today':
            return today, today
        if dr == 'yesterday':
            y = today - timedelta(days=1)
            return y, y
        if dr == 'this_week':
            start = today - timedelta(days=today.weekday())
            return start, today
        if dr == 'previous_week':
            this_monday = today - timedelta(days=today.weekday())
            return (
                this_monday - timedelta(days=7),
                this_monday - timedelta(days=1),
            )
        if dr == 'this_month':
            return today.replace(day=1), today
        if dr == 'last_month':
            first_this = today.replace(day=1)
            last_prev = first_this - timedelta(days=1)
            return last_prev.replace(day=1), last_prev
        if dr == 'custom':
            return self.date_from, self.date_to
        return today, today

    def _get_base_domain(self):
        """Domain for `crm.call.tone` searches (the Calls side)."""
        self.ensure_one()
        domain = [('api_key_id', '=', self.api_key_id.id)]
        d_from, d_to = self._get_date_bounds()
        if d_from:
            start_dt = datetime.datetime.combine(d_from, datetime.time.min)
            domain.append(('call_date', '>=', start_dt))
        if d_to:
            end_dt = datetime.datetime.combine(d_to, datetime.time.max)
            domain.append(('call_date', '<=', end_dt))
        if self.phone_contains:
            digits = ''.join(c for c in (self.phone_contains or '') if c.isdigit())
            if digits:
                domain.append(('phone_digits', 'ilike', digits))
        return domain

    def _get_wa_base_domain(self):
        """Domain for `wa.message.tone` searches (the WhatsApp side).

        Resolves api_key.employee_id → wa.employee.session, then filters
        wa.message.tone by that session + date range. Returns None when no
        WA session can be resolved (e.g. employee_id not set on api_key).
        """
        self.ensure_one()
        if not self.api_key_id or not self.api_key_id.employee_id:
            return None
        WaSession = self.env.get('wa.employee.session')
        if WaSession is None:
            return None
        session = WaSession.sudo().search(
            [('employee_id', '=', self.api_key_id.employee_id.id)], limit=1,
        )
        if not session:
            return None
        domain = [('employee_session_id', '=', session.id)]
        d_from, d_to = self._get_date_bounds()
        if d_from:
            start_dt = datetime.datetime.combine(d_from, datetime.time.min)
            domain.append(('message_date', '>=', start_dt))
        if d_to:
            end_dt = datetime.datetime.combine(d_to, datetime.time.max)
            domain.append(('message_date', '<=', end_dt))
        return domain

    # ── Drill-down actions — per channel ─────────────────────────────
    def _open_calls(self, tone_label, display_name):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': f"{display_name} — {self.api_key_id.name}",
            'res_model': 'crm.call.tone',
            'view_mode': 'list,form',
            'domain': self._get_base_domain() + [('tone_label', '=', tone_label)],
            'target': 'current',
        }

    def _open_wa(self, tone_label, display_name):
        self.ensure_one()
        wa_domain = self._get_wa_base_domain()
        if wa_domain is None:
            return False
        return {
            'type': 'ir.actions.act_window',
            'name': f"{display_name} — {self.api_key_id.name} (WhatsApp)",
            'res_model': 'wa.message.tone',
            'view_mode': 'list,form',
            'domain': wa_domain + [('tone_label', '=', tone_label)],
            'target': 'current',
        }

    def action_view_soft_calls(self):
        return self._open_calls('Soft', 'Soft / Polite Calls')

    def action_view_neutral_calls(self):
        return self._open_calls('Neutral', 'Neutral Calls')

    def action_view_hard_calls(self):
        return self._open_calls('Hard', 'Hard / Critical Calls')

    def action_view_soft_wa(self):
        return self._open_wa('Soft', 'Soft / Polite Messages')

    def action_view_neutral_wa(self):
        return self._open_wa('Neutral', 'Neutral Messages')

    def action_view_hard_wa(self):
        return self._open_wa('Hard', 'Hard / Critical Messages')

    # Backwards-compatible single-button actions (legacy view callers).
    def action_view_soft(self):
        if self.channel == 'whatsapp':
            return self.action_view_soft_wa()
        return self.action_view_soft_calls()

    def action_view_neutral(self):
        if self.channel == 'whatsapp':
            return self.action_view_neutral_wa()
        return self.action_view_neutral_calls()

    def action_view_hard(self):
        if self.channel == 'whatsapp':
            return self.action_view_hard_wa()
        return self.action_view_hard_calls()
