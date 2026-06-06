import logging
from datetime import timedelta

from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class EmployeeWhatsAppSession(models.Model):
    """Links an employee to their company WhatsApp session with tracking."""
    _name = 'wa.employee.session'
    _description = 'Employee WhatsApp Session Assignment'
    _rec_name = 'employee_id'
    _order = 'employee_id'

    employee_id = fields.Many2one(
        'hr.employee', string='Employee',
        required=True, ondelete='cascade', index=True,
    )
    session_id = fields.Many2one(
        'whatsapp.session', string='WhatsApp Session',
        required=True, ondelete='restrict', index=True,
        help='The WhatsApp session assigned to this employee.',
    )
    department_id = fields.Many2one(
        related='employee_id.department_id', store=True,
        string='Department',
    )
    manager_id = fields.Many2one(
        related='employee_id.parent_id', store=True,
        string='Manager',
    )
    job_title = fields.Char(
        related='employee_id.job_title', store=True,
    )
    session_status = fields.Selection(
        related='session_id.status', string='WA Status',
    )
    phone_number = fields.Char(
        'Assigned Phone', required=True,
        help='Company WhatsApp number assigned to this employee.',
    )
    active = fields.Boolean(default=True)
    monitoring_enabled = fields.Boolean(
        'Enable Monitoring', default=True,
        help='Track all messages on this session.',
    )
    # ---- Auto-Reply Settings ----
    auto_reply_enabled = fields.Boolean(
        'Enable Auto-Reply', default=False,
        help='Automatically reply with product suggestions when employee does not respond in time.',
    )
    auto_reply_timeout = fields.Integer(
        'Reply Timeout (seconds)', default=120,
        help='Seconds to wait for employee response before auto-replying. Default: 120 (2 minutes). Set low for testing.',
    )
    auto_reply_greeting = fields.Char(
        'Greeting Message', default='Hi! Thank you for reaching out.',
        help='Greeting text before product suggestions.',
    )
    auto_reply_no_match = fields.Char(
        'No Match Message',
        default='Sorry, I could not find matching products. An agent will assist you shortly.',
        help='Message when no products match the query.',
    )
    auto_reply_max_products = fields.Integer(
        'Max Products to Suggest', default=5,
    )
    notes = fields.Text('Notes')

    # ---- Computed Stats ----
    total_messages = fields.Integer(
        compute='_compute_stats', string='Total Messages', store=True,
    )
    total_sent = fields.Integer(
        compute='_compute_stats', string='Messages Sent', store=True,
    )
    total_received = fields.Integer(
        compute='_compute_stats', string='Messages Received', store=True,
    )
    unique_contacts = fields.Integer(
        compute='_compute_stats', string='Unique Contacts', store=True,
    )
    alert_count = fields.Integer(
        compute='_compute_alert_count', string='Active Alerts',
    )
    avg_response_minutes = fields.Float(
        compute='_compute_response_time', string='Avg Response (min)',
    )
    last_activity = fields.Datetime(
        compute='_compute_last_activity', string='Last Activity',
    )
    quality_score = fields.Float(
        compute='_compute_quality_score', string='Quality Score',
    )
    today_sent = fields.Integer(
        compute='_compute_today_stats', string='Sent Today',
    )
    today_received = fields.Integer(
        compute='_compute_today_stats', string='Received Today',
    )

    _employee_unique = models.Constraint(
        'UNIQUE (employee_id)',
        'Each employee can only have one WhatsApp session assignment.',
    )
    _session_unique = models.Constraint(
        'UNIQUE (session_id)',
        'Each WhatsApp session can only be assigned to one employee.',
    )

    # ----------------------------------------------------------
    # Computed Fields
    # ----------------------------------------------------------
    @api.depends('session_id')
    def _compute_stats(self):
        for rec in self:
            if rec.session_id:
                messages = self.env['whatsapp.message'].search([
                    ('session_id', '=', rec.session_id.id),
                ])
                rec.total_messages = len(messages)
                rec.total_sent = len(messages.filtered(
                    lambda m: m.direction == 'outgoing'
                ))
                rec.total_received = len(messages.filtered(
                    lambda m: m.direction == 'incoming'
                ))
                rec.unique_contacts = len(set(messages.mapped('phone')))
            else:
                rec.total_messages = 0
                rec.total_sent = 0
                rec.total_received = 0
                rec.unique_contacts = 0

    def _compute_alert_count(self):
        for rec in self:
            rec.alert_count = self.env['wa.keyword.alert.log'].search_count([
                ('employee_session_id', '=', rec.id),
                ('status', '=', 'new'),
            ])

    def _compute_response_time(self):
        """Calculate average response time for outgoing replies."""
        for rec in self:
            if not rec.session_id:
                rec.avg_response_minutes = 0.0
                continue

            # Get conversations with response times
            scores = self.env['wa.quality.score'].search([
                ('employee_session_id', '=', rec.id),
            ])
            if scores:
                avg = sum(scores.mapped('avg_response_minutes')) / len(scores)
                rec.avg_response_minutes = round(avg, 1)
            else:
                rec.avg_response_minutes = 0.0

    def _compute_last_activity(self):
        for rec in self:
            if rec.session_id:
                last_msg = self.env['whatsapp.message'].search([
                    ('session_id', '=', rec.session_id.id),
                ], order='create_date desc', limit=1)
                rec.last_activity = last_msg.create_date if last_msg else False
            else:
                rec.last_activity = False

    def _compute_quality_score(self):
        for rec in self:
            scores = self.env['wa.quality.score'].search([
                ('employee_session_id', '=', rec.id),
            ])
            if scores:
                rec.quality_score = round(
                    sum(scores.mapped('score')) / len(scores), 1
                )
            else:
                rec.quality_score = 0.0

    def _compute_today_stats(self):
        today_start = fields.Datetime.now().replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        for rec in self:
            if rec.session_id:
                domain = [
                    ('session_id', '=', rec.session_id.id),
                    ('create_date', '>=', today_start),
                ]
                rec.today_sent = self.env['whatsapp.message'].search_count(
                    domain + [('direction', '=', 'outgoing')]
                )
                rec.today_received = self.env['whatsapp.message'].search_count(
                    domain + [('direction', '=', 'incoming')]
                )
            else:
                rec.today_sent = 0
                rec.today_received = 0

    # ----------------------------------------------------------
    # Actions
    # ----------------------------------------------------------
    def action_view_messages(self):
        """View all messages for this employee's session."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Messages - %s', self.employee_id.name),
            'res_model': 'whatsapp.message',
            'view_mode': 'list,form',
            'domain': [('session_id', '=', self.session_id.id)],
            'context': {'search_default_group_direction': 1},
        }

    def action_view_alerts(self):
        """View keyword alerts for this employee."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Alerts - %s', self.employee_id.name),
            'res_model': 'wa.keyword.alert.log',
            'view_mode': 'kanban,list,form',
            'domain': [('employee_session_id', '=', self.id)],
        }

    def action_open_chats(self):
        """Open employee chats from dashboard kanban card click."""
        self.ensure_one()
        return {
            'type': 'ir.actions.client',
            'tag': 'wa_chat_split_view',
            'name': _('Chats - %s', self.employee_id.name),
            'context': {'active_employee_session_id': self.id},
        }

    def action_view_conversations(self):
        """View conversation threads for this employee."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Chats - %s', self.employee_id.name),
            'res_model': 'wa.conversation',
            'view_mode': 'kanban,list,form',
            'domain': [('employee_session_id', '=', self.id)],
        }

    def action_view_quality_scores(self):
        """View quality scores for this employee."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Quality Scores - %s', self.employee_id.name),
            'res_model': 'wa.quality.score',
            'view_mode': 'list,form',
            'domain': [('employee_session_id', '=', self.id)],
        }

    def action_refresh_stats(self):
        """Manually recompute stats."""
        self._compute_stats()
        self._compute_alert_count()
        self._compute_response_time()
        self._compute_last_activity()
        self._compute_quality_score()
        self._compute_today_stats()
