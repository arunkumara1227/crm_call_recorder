import logging
from odoo import models, fields, api

_logger = logging.getLogger(__name__)


class QualityScore(models.Model):
    """
    Communication quality score per employee.
    Computed periodically from conversation data.
    Factors: response time, message volume, consistency, flagged messages.
    """
    _name = 'wa.quality.score'
    _description = 'Communication Quality Score'
    _order = 'score_date desc'
    _rec_name = 'display_name_custom'

    employee_session_id = fields.Many2one(
        'wa.employee.session', string='Employee Session',
        required=True, ondelete='cascade', index=True,
    )
    employee_id = fields.Many2one(
        related='employee_session_id.employee_id',
        store=True, string='Employee', index=True,
    )
    department_id = fields.Many2one(
        related='employee_session_id.department_id',
        store=True, string='Department',
    )
    score_date = fields.Date('Score Date', required=True, index=True)
    score = fields.Float('Overall Score (0-100)', digits=(5, 1))

    # ---- Breakdown ----
    response_time_score = fields.Float(
        'Response Time Score (0-25)', digits=(5, 1),
        help='Lower avg response time = higher score.',
    )
    volume_score = fields.Float(
        'Activity Volume Score (0-25)', digits=(5, 1),
        help='Based on message volume vs team average.',
    )
    consistency_score = fields.Float(
        'Consistency Score (0-25)', digits=(5, 1),
        help='Regular activity across working hours.',
    )
    compliance_score = fields.Float(
        'Compliance Score (0-25)', digits=(5, 1),
        help='No keyword alerts = full score. Alerts reduce it.',
    )

    # ---- Period Stats ----
    period_messages = fields.Integer('Messages in Period')
    period_sent = fields.Integer('Sent in Period')
    period_received = fields.Integer('Received in Period')
    period_conversations = fields.Integer('Active Conversations')
    period_alerts = fields.Integer('Alerts Triggered')
    avg_response_minutes = fields.Float('Avg Response (min)')
    avg_word_count = fields.Float('Avg Words per Message')
    peak_hour = fields.Integer('Most Active Hour')

    display_name_custom = fields.Char(compute='_compute_display_name_custom')

    _unique_score = models.Constraint(
        'UNIQUE (employee_session_id, score_date)',
        'Only one quality score per employee per day.',
    )

    @api.depends('employee_id', 'score_date', 'score')
    def _compute_display_name_custom(self):
        for rec in self:
            emp = rec.employee_id.name or '?'
            rec.display_name_custom = (
                f"{emp} - {rec.score_date} - Score: {rec.score:.0f}"
            )

    # ----------------------------------------------------------
    # Cron: Compute daily quality scores
    # ----------------------------------------------------------
    @api.model
    def _cron_compute_scores(self):
        """Compute daily quality scores for all monitored employees."""
        today = fields.Date.today()

        emp_sessions = self.env['wa.employee.session'].search([
            ('monitoring_enabled', '=', True),
        ])

        for emp_session in emp_sessions:
            # Check if already computed today
            existing = self.search([
                ('employee_session_id', '=', emp_session.id),
                ('score_date', '=', today),
            ])
            if existing:
                continue

            self._compute_score_for(emp_session, today)

    def _compute_score_for(self, emp_session, date):
        """Compute quality score for one employee for given date."""
        # Get messages from today
        date_start = fields.Datetime.to_datetime(date).replace(
            hour=0, minute=0, second=0
        )
        date_end = fields.Datetime.to_datetime(date).replace(
            hour=23, minute=59, second=59
        )

        logs = self.env['wa.communication.log'].search([
            ('employee_session_id', '=', emp_session.id),
            ('message_date', '>=', date_start),
            ('message_date', '<=', date_end),
        ])

        if not logs:
            return  # No activity, no score

        sent = logs.filtered(lambda l: l.direction == 'outgoing')
        received = logs.filtered(lambda l: l.direction == 'incoming')
        flagged = logs.filtered(lambda l: l.is_flagged)

        # ---- 1. Response Time Score (0-25) ----
        conversations = logs.mapped('conversation_id')
        response_times = conversations.mapped('avg_response_minutes')
        valid_rt = [rt for rt in response_times if rt > 0]
        avg_rt = sum(valid_rt) / len(valid_rt) if valid_rt else 0

        if avg_rt <= 0:
            rt_score = 25  # No incoming messages to respond to
        elif avg_rt <= 5:
            rt_score = 25  # Excellent: under 5 min
        elif avg_rt <= 15:
            rt_score = 20  # Good: under 15 min
        elif avg_rt <= 30:
            rt_score = 15  # Average: under 30 min
        elif avg_rt <= 60:
            rt_score = 10  # Slow: under 1 hour
        else:
            rt_score = max(0, 25 - (avg_rt / 12))  # Degrades for longer

        # ---- 2. Volume Score (0-25) ----
        total = len(logs)
        if total >= 50:
            vol_score = 25  # Very active
        elif total >= 30:
            vol_score = 20
        elif total >= 15:
            vol_score = 15
        elif total >= 5:
            vol_score = 10
        else:
            vol_score = 5

        # ---- 3. Consistency Score (0-25) ----
        # Check how many hours had activity (working hours 8-18)
        active_hours = set()
        for log in logs:
            if log.message_date:
                h = log.message_date.hour
                if 8 <= h <= 18:
                    active_hours.add(h)

        work_hours_covered = len(active_hours)
        if work_hours_covered >= 8:
            cons_score = 25
        elif work_hours_covered >= 6:
            cons_score = 20
        elif work_hours_covered >= 4:
            cons_score = 15
        elif work_hours_covered >= 2:
            cons_score = 10
        else:
            cons_score = 5

        # ---- 4. Compliance Score (0-25) ----
        alert_count = len(flagged)
        if alert_count == 0:
            comp_score = 25
        elif alert_count <= 2:
            comp_score = 15
        elif alert_count <= 5:
            comp_score = 10
        else:
            comp_score = max(0, 25 - (alert_count * 3))

        # ---- Overall ----
        overall = rt_score + vol_score + cons_score + comp_score

        # Find peak hour
        hour_counts = {}
        for log in logs:
            if log.message_date:
                h = log.message_date.hour
                hour_counts[h] = hour_counts.get(h, 0) + 1
        peak_hour = max(hour_counts, key=hour_counts.get) if hour_counts else 0

        # Avg word count
        word_counts = [l.word_count for l in sent if l.word_count]
        avg_wc = sum(word_counts) / len(word_counts) if word_counts else 0

        self.create({
            'employee_session_id': emp_session.id,
            'score_date': date,
            'score': round(overall, 1),
            'response_time_score': round(rt_score, 1),
            'volume_score': round(vol_score, 1),
            'consistency_score': round(cons_score, 1),
            'compliance_score': round(comp_score, 1),
            'period_messages': total,
            'period_sent': len(sent),
            'period_received': len(received),
            'period_conversations': len(conversations),
            'period_alerts': alert_count,
            'avg_response_minutes': round(avg_rt, 1),
            'avg_word_count': round(avg_wc, 1),
            'peak_hour': peak_hour,
        })
