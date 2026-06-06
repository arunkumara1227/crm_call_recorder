import datetime
from datetime import timedelta

from odoo import models, fields, api


class WaToneReport(models.TransientModel):
    """Interactive Tone Report — filter by employee + date range, drill
    down from aggregate counts to the individual tone messages."""
    _name = 'wa.tone.report'
    _description = 'WhatsApp Tone Report'

    employee_id = fields.Many2one(
        'hr.employee', string='Employee', required=True,
    )
    date_range = fields.Selection([
        ('today', 'Today'),
        ('yesterday', 'Yesterday'),
        ('this_week', 'This Week'),
        ('previous_week', 'Previous Week'),
        ('this_month', 'This Month'),
        ('last_month', 'Last Month'),
        ('custom', 'Custom Range'),
    ], string='Date Range', default='today', required=True)
    date_from = fields.Date(string='From')
    date_to = fields.Date(string='To')

    count_soft = fields.Integer(
        string='Soft / Polite', compute='_compute_counts',
    )
    count_neutral = fields.Integer(
        string='Neutral', compute='_compute_counts',
    )
    count_hard = fields.Integer(
        string='Hard / Critical', compute='_compute_counts',
    )
    count_total = fields.Integer(
        string='Total Analyzed', compute='_compute_counts',
    )

    @api.depends('employee_id', 'date_range', 'date_from', 'date_to')
    def _compute_counts(self):
        Tone = self.env['wa.message.tone']
        for rec in self:
            if not rec.employee_id:
                rec.count_soft = rec.count_neutral = rec.count_hard = 0
                rec.count_total = 0
                continue
            domain = rec._get_base_domain()
            rec.count_soft = Tone.search_count(
                domain + [('tone_label', '=', 'Soft')]
            )
            rec.count_neutral = Tone.search_count(
                domain + [('tone_label', '=', 'Neutral')]
            )
            rec.count_hard = Tone.search_count(
                domain + [('tone_label', '=', 'Hard')]
            )
            rec.count_total = (
                rec.count_soft + rec.count_neutral + rec.count_hard
            )

    def _get_date_bounds(self):
        """Translate the selected date_range into concrete (from, to) dates."""
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
        """Base domain for wa.message.tone — employee + date window."""
        self.ensure_one()
        domain = [('employee_id', '=', self.employee_id.id)]
        d_from, d_to = self._get_date_bounds()
        if d_from:
            start_dt = datetime.datetime.combine(d_from, datetime.time.min)
            domain.append(('message_date', '>=', start_dt))
        if d_to:
            end_dt = datetime.datetime.combine(d_to, datetime.time.max)
            domain.append(('message_date', '<=', end_dt))
        return domain

    def _open_tone_messages(self, tone_label, display_name):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': f"{display_name} — {self.employee_id.name}",
            'res_model': 'wa.message.tone',
            'view_mode': 'list,form',
            'domain': self._get_base_domain()
                + [('tone_label', '=', tone_label)],
            'target': 'current',
        }

    def action_view_soft(self):
        return self._open_tone_messages('Soft', 'Soft / Polite Messages')

    def action_view_neutral(self):
        return self._open_tone_messages('Neutral', 'Neutral Messages')

    def action_view_hard(self):
        return self._open_tone_messages('Hard', 'Hard / Critical Messages')
