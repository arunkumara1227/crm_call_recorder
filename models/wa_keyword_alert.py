import re
import logging
from odoo import models, fields, api, _

_logger = logging.getLogger(__name__)


class KeywordAlertRule(models.Model):
    """Configurable keyword rules for flagging messages."""
    _name = 'wa.keyword.alert.rule'
    _description = 'WhatsApp Keyword Alert Rule'
    _order = 'severity desc, name'

    name = fields.Char('Rule Name', required=True)
    active = fields.Boolean(default=True)
    keywords = fields.Text(
        'Keywords', required=True,
        help='One keyword or phrase per line. Case-insensitive matching.',
    )
    severity = fields.Selection([
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('critical', 'Critical'),
    ], string='Severity', default='medium', required=True)
    match_type = fields.Selection([
        ('contains', 'Contains (anywhere in message)'),
        ('exact_word', 'Exact Word Match'),
        ('regex', 'Regular Expression'),
    ], string='Match Type', default='contains', required=True)
    category = fields.Selection([
        ('policy', 'Policy Violation'),
        ('profanity', 'Profanity / Inappropriate'),
        ('data_leak', 'Data Leak Risk'),
        ('competitor', 'Competitor Mention'),
        ('complaint', 'Customer Complaint'),
        ('soft_language', 'Soft Language (Polite/Friendly)'),
        ('hard_language', 'Hard Language (Harsh/Aggressive)'),
        ('custom', 'Custom'),
    ], string='Category', default='custom', required=True)
    description = fields.Text('Description')
    alert_count = fields.Integer(
        compute='_compute_alert_count', string='Alerts Triggered',
    )

    def _compute_alert_count(self):
        for rec in self:
            rec.alert_count = self.env['wa.keyword.alert.log'].search_count([
                ('rule_id', '=', rec.id),
            ])

    def action_view_alerts(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Alerts - %s', self.name),
            'res_model': 'wa.keyword.alert.log',
            'view_mode': 'list,form',
            'domain': [('rule_id', '=', self.id)],
        }

    def _check_text(self, text):
        """
        Check if text matches any keyword in this rule.
        Returns list of matched keywords.
        """
        if not text or not self.keywords:
            return []

        text_lower = text.lower()
        matches = []

        for line in self.keywords.strip().split('\n'):
            keyword = line.strip()
            if not keyword:
                continue

            if self.match_type == 'contains':
                if keyword.lower() in text_lower:
                    matches.append(keyword)

            elif self.match_type == 'exact_word':
                # Word boundary match
                pattern = r'\b' + re.escape(keyword) + r'\b'
                if re.search(pattern, text, re.IGNORECASE):
                    matches.append(keyword)

            elif self.match_type == 'regex':
                try:
                    if re.search(keyword, text, re.IGNORECASE):
                        matches.append(keyword)
                except re.error:
                    _logger.warning(
                        "Invalid regex in alert rule %s: %s", self.name, keyword
                    )

        return matches


class KeywordAlertLog(models.Model):
    """Log of triggered keyword alerts."""
    _name = 'wa.keyword.alert.log'
    _description = 'WhatsApp Keyword Alert Log'
    _order = 'create_date desc'
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
    log_entry_id = fields.Many2one(
        'wa.communication.log', string='Message Log',
        ondelete='cascade',
    )
    rule_id = fields.Many2one(
        'wa.keyword.alert.rule', string='Alert Rule',
        required=True, ondelete='cascade',
    )
    severity = fields.Selection(
        related='rule_id.severity', store=True,
    )
    category = fields.Selection(
        related='rule_id.category', store=True,
    )
    matched_keywords = fields.Char('Matched Keywords')
    message_text = fields.Text('Message Content')
    message_direction = fields.Selection([
        ('incoming', 'Incoming'),
        ('outgoing', 'Outgoing'),
    ], string='Direction')
    phone = fields.Char('Contact Phone')
    partner_id = fields.Many2one('res.partner', string='Contact')
    message_date = fields.Datetime('Message Date')
    status = fields.Selection([
        ('new', 'New'),
        ('reviewed', 'Reviewed'),
        ('escalated', 'Escalated'),
        ('dismissed', 'Dismissed'),
    ], string='Status', default='new', required=True, index=True)
    reviewer_id = fields.Many2one(
        'res.users', string='Reviewed By',
    )
    review_date = fields.Datetime('Review Date')
    review_notes = fields.Text('Review Notes')
    display_name_custom = fields.Char(
        compute='_compute_display_name', string='Alert',
    )

    def _compute_display_name(self):
        for rec in self:
            emp = rec.employee_id.name or '?'
            rule = rec.rule_id.name or '?'
            rec.display_name_custom = f"[{rec.severity or '?'}] {emp} - {rule}"

    # ----------------------------------------------------------
    # Alert Actions
    # ----------------------------------------------------------
    def action_mark_reviewed(self):
        self.write({
            'status': 'reviewed',
            'reviewer_id': self.env.uid,
            'review_date': fields.Datetime.now(),
        })

    def action_escalate(self):
        self.write({
            'status': 'escalated',
            'reviewer_id': self.env.uid,
            'review_date': fields.Datetime.now(),
        })

    def action_dismiss(self):
        self.write({
            'status': 'dismissed',
            'reviewer_id': self.env.uid,
            'review_date': fields.Datetime.now(),
        })

    # ----------------------------------------------------------
    # Check a message against all active rules
    # ----------------------------------------------------------
    @api.model
    def _check_message(self, log_entry, emp_session):
        """Check a communication log entry against all active alert rules."""
        if not log_entry.message_text:
            return

        rules = self.env['wa.keyword.alert.rule'].search([
            ('active', '=', True),
        ])

        for rule in rules:
            matches = rule._check_text(log_entry.message_text)
            if matches:
                self.create({
                    'employee_session_id': emp_session.id,
                    'log_entry_id': log_entry.id,
                    'rule_id': rule.id,
                    'matched_keywords': ', '.join(matches),
                    'message_text': log_entry.message_text,
                    'message_direction': log_entry.direction,
                    'phone': log_entry.phone,
                    'partner_id': log_entry.partner_id.id if log_entry.partner_id else False,
                    'message_date': log_entry.message_date,
                })
                _logger.info(
                    "🚨 Alert triggered: Rule '%s' matched '%s' in message from employee %s",
                    rule.name, ', '.join(matches), emp_session.employee_id.name,
                )

                # Flag the log entry
                log_entry.write({
                    'is_flagged': True,
                    'flag_reason': f"{rule.name}: {', '.join(matches)}",
                })
