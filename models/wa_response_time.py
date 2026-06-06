import logging
from odoo import models, fields, api, tools

_logger = logging.getLogger(__name__)


class WaResponseTimeStat(models.Model):
    """
    SQL view: one row per outgoing message that has a preceding
    incoming message in the same conversation.
    """
    _name = 'wa.response.time.stat'
    _description = 'Manual Response Time Statistics'
    _auto = False
    _order = 'reply_date desc'

    employee_session_id = fields.Many2one('wa.employee.session', string='Session', readonly=True)
    employee_id = fields.Many2one('hr.employee', string='Employee', readonly=True)
    department_id = fields.Many2one('hr.department', string='Department', readonly=True)
    conversation_id = fields.Many2one('wa.conversation', string='Conversation', readonly=True)
    phone = fields.Char('Customer Phone', readonly=True)
    reply_date = fields.Datetime('Reply Sent At', readonly=True)
    customer_msg_date = fields.Datetime('Customer Sent At', readonly=True)
    response_seconds = fields.Float('Response Time (sec)', readonly=True)
    response_minutes = fields.Float('Response Time (min)', readonly=True)
    reply_text = fields.Text('Reply Message', readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, 'wa_response_time_stat')
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW wa_response_time_stat AS
            SELECT
                out_log.id                          AS id,
                out_log.employee_session_id         AS employee_session_id,
                out_log.employee_id                 AS employee_id,
                out_log.department_id               AS department_id,
                out_log.conversation_id             AS conversation_id,
                out_log.phone                       AS phone,
                out_log.message_date                AS reply_date,
                in_log.message_date                 AS customer_msg_date,
                EXTRACT(EPOCH FROM (out_log.message_date - in_log.message_date))
                                                    AS response_seconds,
                EXTRACT(EPOCH FROM (out_log.message_date - in_log.message_date)) / 60.0
                                                    AS response_minutes,
                out_log.message_text                AS reply_text
            FROM wa_communication_log out_log
            JOIN LATERAL (
                SELECT il.message_date
                FROM wa_communication_log il
                WHERE il.conversation_id = out_log.conversation_id
                  AND il.direction = 'incoming'
                  AND il.message_date < out_log.message_date
                ORDER BY il.message_date DESC
                LIMIT 1
            ) in_log ON true
            WHERE out_log.direction = 'outgoing'
              -- Only reasonable response windows (> 0 sec, < 24 hours)
              AND out_log.message_date > in_log.message_date
              AND EXTRACT(EPOCH FROM (out_log.message_date - in_log.message_date)) < 86400
        """)


class WaResponseTimeSummary(models.Model):
    """
    SQL view: one row per employee session with aggregated response time stats.
    """
    _name = 'wa.response.time.summary'
    _description = 'Response Time Summary per Employee'
    _auto = False
    _order = 'avg_response_minutes asc'

    employee_session_id = fields.Many2one('wa.employee.session', string='Session', readonly=True)
    employee_id = fields.Many2one('hr.employee', string='Employee', readonly=True)
    department_id = fields.Many2one('hr.department', string='Department', readonly=True)
    total_manual_replies = fields.Integer('Manual Replies', readonly=True)
    avg_response_seconds = fields.Float('Avg Response (sec)', readonly=True)
    avg_response_minutes = fields.Float('Avg Response (min)', readonly=True)
    min_response_minutes = fields.Float('Fastest (min)', readonly=True)
    max_response_minutes = fields.Float('Slowest (min)', readonly=True)
    last_reply_date = fields.Datetime('Last Reply', readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, 'wa_response_time_summary')
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW wa_response_time_summary AS
            SELECT
                employee_session_id                         AS id,
                employee_session_id,
                employee_id,
                department_id,
                COUNT(*)                                    AS total_manual_replies,
                AVG(response_seconds)                       AS avg_response_seconds,
                AVG(response_seconds) / 60.0               AS avg_response_minutes,
                MIN(response_seconds) / 60.0               AS min_response_minutes,
                MAX(response_seconds) / 60.0               AS max_response_minutes,
                MAX(reply_date)                             AS last_reply_date
            FROM wa_response_time_stat
            GROUP BY employee_session_id, employee_id, department_id
        """)
