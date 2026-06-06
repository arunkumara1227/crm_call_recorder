import logging
import threading
from odoo import models, fields, api, SUPERUSER_ID
from odoo.modules.registry import Registry

_logger = logging.getLogger(__name__)


class WhatsAppMessageInherit(models.Model):
    _inherit = 'whatsapp.message'

    employee_session_id = fields.Many2one(
        'wa.employee.session', string='Employee Session',
        compute='_compute_employee_session', store=True, index=True,
    )
    employee_id = fields.Many2one(
        related='employee_session_id.employee_id',
        store=True, string='Employee',
    )
    push_name = fields.Char('WhatsApp Name', help='Contact push name from WhatsApp')
    is_voice_message = fields.Boolean('Voice Message', default=False)
    voice_transcription = fields.Text('Voice Transcription')
    voice_language = fields.Char('Detected Language', help='ISO language code detected by Whisper e.g. en, ar, ml, hi')
    voice_translation = fields.Text('English Translation')

    def _compute_employee_session(self):
        """Link message to employee session if mapped."""
        for rec in self:
            if rec.session_id:
                emp_session = self.env['wa.employee.session'].search([
                    ('session_id', '=', rec.session_id.id),
                ], limit=1)
                rec.employee_session_id = emp_session.id if emp_session else False
            else:
                rec.employee_session_id = False

    @api.model_create_multi
    def create(self, vals_list):
        """Override create to instantly sync messages to WA Tracker.

        Both side-effects (tracker sync + bus push) run inside a SAVEPOINT.
        Reason: failures inside `_instant_sync_to_tracker` previously
        poisoned the DB transaction owned by the neonize background-thread
        handler. The Python try/except caught the inner exception, but
        `pool.cursor()` exit still tried to commit and hit
        `InFailedSqlTransaction`, which crashed the neonize thread and
        triggered a reconnect-thrashing loop (Phase BB). The savepoint
        keeps any tracker failure isolated — Postgres rolls back JUST the
        tracker writes; the parent transaction (whatsapp.message row)
        commits cleanly.
        """
        records = super().create(vals_list)
        try:
            with self.env.cr.savepoint():
                self._instant_sync_to_tracker(records)
        except Exception as e:
            _logger.warning(
                "WA Tracker: Real-time sync rolled back (cron will catch up): %s",
                e, exc_info=True,
            )
        # Push to browser via Odoo's bus so the chat split-view auto-refreshes
        # without manual reload. Wrapped in its own savepoint for the same
        # defensive reason.
        try:
            with self.env.cr.savepoint():
                self._send_bus_notification(records)
        except Exception as e:
            _logger.warning("WA Tracker: bus notification skipped: %s", e)
        return records

    def _send_bus_notification(self, records):
        """Broadcast one notification per saved message on a global channel
        the chat-view OWL component subscribes to. Payload is minimal — the
        client decides whether to re-fetch based on which conversation it's
        currently showing."""
        Bus = self.env['bus.bus']
        for rec in records:
            if not rec.session_id:
                continue
            payload = {
                'session_id': rec.session_id.id,
                'phone': rec.phone or '',
                'direction': rec.direction or '',
                'message_id': rec.id,
                'is_voice': bool(rec.is_voice_message),
            }
            # Channel is a literal string. Odoo's bus is automatically
            # DB-scoped, so no cross-tenant leak. One global channel keeps
            # the v1 wiring simple; switch to per-employee channels later
            # if privacy or load demands it.
            Bus._sendone('wa.tracker.update', 'wa.message.created', payload)

    def write(self, vals):
        """Override write to update tracker when message status changes.
        Tracker update wrapped in a savepoint — same reason as create()."""
        res = super().write(vals)
        if 'status' in vals or 'message' in vals:
            try:
                with self.env.cr.savepoint():
                    self._instant_update_tracker(vals)
            except Exception as e:
                _logger.warning(
                    "WA Tracker: Real-time update rolled back: %s", e
                )
        return res

    def _instant_sync_to_tracker(self, messages):
        """Instantly process new messages into the tracker system."""
        CommLog = self.env['wa.communication.log']
        Conversation = self.env['wa.conversation']
        AlertLog = self.env['wa.keyword.alert.log']
        touched_emp_sessions = self.env['wa.employee.session']

        for msg in messages:
            if not msg.session_id:
                continue

            # Find the employee session for this WhatsApp session
            emp_session = self.env['wa.employee.session'].search([
                ('session_id', '=', msg.session_id.id),
                ('monitoring_enabled', '=', True),
            ], limit=1)

            if not emp_session:
                continue

            # Check if already in log (avoid duplicates)
            existing = CommLog.search([
                ('message_id', '=', msg.id),
            ], limit=1)
            if existing:
                continue

            # Get or create conversation thread
            conversation = Conversation._get_or_create(
                emp_session, msg.phone, msg.partner_id,
            )

            # Create communication log entry
            word_count = len((msg.message or '').split())

            # Clean phone from JID format
            import re
            clean_phone = msg.phone or ''
            user_match = re.search(r'User:\s*"(\d+)"', clean_phone)
            if user_match:
                clean_phone = user_match.group(1)
            else:
                digits = re.sub(r'[^\d]', '', clean_phone)
                if digits and len(digits) >= 6:
                    clean_phone = digits

            log_entry = CommLog.create({
                'employee_session_id': emp_session.id,
                'message_id': msg.id,
                'phone': clean_phone,
                'partner_id': msg.partner_id.id if msg.partner_id else False,
                'message_text': msg.message,
                'direction': msg.direction,
                'message_date': msg.create_date,
                'status': msg.status,
                'word_count': word_count,
                'has_attachment': bool(msg.attachment_ids) if hasattr(msg, 'attachment_ids') else False,
                'is_group_message': msg.is_group if hasattr(msg, 'is_group') else False,
                'conversation_id': conversation.id if conversation else False,
                'is_voice_message': getattr(msg, 'is_voice_message', False),
                'voice_transcription': getattr(msg, 'voice_transcription', '') or '',
                'voice_language': getattr(msg, 'voice_language', '') or '',
                'voice_translation': getattr(msg, 'voice_translation', '') or '',
            })

            # Update conversation stats
            if conversation:
                conversation._update_stats()

            # Check keyword alerts instantly
            AlertLog._check_message(log_entry, emp_session)

            # Analyze tone for outgoing employee messages
            self.env['wa.message.tone'].create_or_update_for_message(log_entry.id)

            # Auto-promote WhatsApp contact into res.partner on first sighting.
            # Incoming only (push_name is the sender's name, useful for new contacts).
            # Group messages skipped — we don't want a partner per group JID.
            if (msg.direction == 'incoming'
                    and getattr(msg, 'push_name', '')
                    and not getattr(msg, 'is_group', False)
                    and not msg.partner_id):
                partner = self._ensure_partner_from_push_name(
                    msg.push_name, clean_phone, is_group=False,
                )
                if partner:
                    log_entry.partner_id = partner.id
                    if conversation and not conversation.partner_id:
                        conversation.partner_id = partner.id

            _logger.info(
                "WA Tracker: Instant sync - %s %s message for %s",
                msg.direction, msg.phone, emp_session.employee_id.name or 'Unknown',
            )

            touched_emp_sessions |= emp_session

        if touched_emp_sessions:
            touched_emp_sessions._compute_stats()
            touched_emp_sessions._compute_today_stats()
            touched_emp_sessions._compute_last_activity()

    def _instant_update_tracker(self, vals):
        """Update tracker log when message status changes."""
        CommLog = self.env['wa.communication.log']
        for msg in self:
            log = CommLog.search([('message_id', '=', msg.id)], limit=1)
            if log:
                update_vals = {}
                if 'status' in vals:
                    update_vals['status'] = vals['status']
                if 'message' in vals:
                    update_vals['message_text'] = vals['message']
                    update_vals['word_count'] = len((vals['message'] or '').split())
                if update_vals:
                    log.write(update_vals)

    @api.model
    def _ensure_partner_from_push_name(self, push_name, phone, is_group=False):
        """Find or create a res.partner for a WhatsApp contact.

        Used both by the message-sync hook (above) and by wa.conversation
        _get_or_create() so that any WA contact with a known display name
        gets promoted into the central Contacts table — which then lets
        call recordings auto-match the same contact by phone.

        Idempotent: if a partner with the same last-10-digit phone already
        exists, returns it. Group messages are skipped (one partner per
        phone, never per group JID).

        Returns the res.partner record or False.
        """
        import re as _re
        if is_group or not push_name or not phone:
            return False
        clean_name = (push_name or '').strip()
        if not clean_name:
            return False
        digits = _re.sub(r'\D', '', phone or '')[-10:]
        if not digits or len(digits) < 7:
            return False
        Partner = self.env['res.partner'].sudo()
        existing = Partner.search(
            ['|', ('phone', 'ilike', digits), ('mobile', 'ilike', digits)],
            limit=1,
        )
        if existing:
            return existing
        try:
            return Partner.create({
                'name': clean_name,
                'phone': phone,
                'is_company': False,
            })
        except Exception as e:
            _logger.warning(
                "Failed to auto-create partner for WA contact %s (%s): %s",
                clean_name, phone, e,
            )
            return False
