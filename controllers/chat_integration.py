"""JSON-RPC endpoint feeding the Call Recordings right-panel that the
crm_call_recorder JS patch injects into whatsapp_employee_tracker's
wa_chat_split_view.

Returns recordings whose last-10 phone digits match the currently-selected
chat contact, optionally scoped to the API keys belonging to the
employee whose chat the user is viewing.
"""

import logging
import re

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class CrmCallRecorderChatIntegration(http.Controller):

    @http.route(
        '/crm_call_recorder/chat_recordings_for_phone',
        type='json', auth='user', methods=['POST'], csrf=False,
    )
    def recordings_for_phone(self, phone=None, employee_session_id=None, limit=50):
        if not phone:
            return {'recordings': []}

        # Normalize the incoming phone to last-10 digits — same convention
        # crm.call.recording._normalize_phone produces in phone_digits.
        # ASCII-only on purpose: c.isdigit() admits Arabic/Devanagari digits
        # that wouldn't match the all-ASCII phone_digits stored on recordings.
        digits = re.sub(r'\D', '', str(phone))[-10:]
        if len(digits) < 7:
            return {'recordings': []}

        domain = [('phone_digits', 'ilike', digits)]

        # Scope to that employee's devices when employee_session_id is given.
        # Prevents Arun seeing Bob's recordings just because Bob also called
        # the same contact.
        if employee_session_id:
            try:
                session = request.env['wa.employee.session'].sudo().browse(
                    int(employee_session_id),
                )
                if session.exists() and session.employee_id:
                    api_key_ids = request.env['crm.call.api.key'].sudo().search([
                        ('employee_id', '=', session.employee_id.id),
                    ]).ids
                    if api_key_ids:
                        domain.append(('created_by_api_key_id', 'in', api_key_ids))
                    else:
                        # Employee has no keys yet — nothing to show.
                        return {'recordings': []}
            except (ValueError, TypeError):
                pass  # Malformed id — fall through to unscoped search.

        recs = request.env['crm.call.recording'].sudo().search(
            domain, order='call_date desc', limit=limit,
        )

        out = []
        for r in recs:
            tone = r.tone_ids[:1] if r.tone_ids else None
            out.append({
                'id': r.id,
                'phone': r.phone or '',
                'call_date': r.call_date.strftime('%b %d, %H:%M') if r.call_date else '',
                'direction': r.direction or 'unknown',
                'duration_seconds': r.duration_seconds or 0,
                'duration_display': r.duration_display or '0s',
                'audio_url': r.recording_url or '',
                'transcript': r.transcription_text or '',
                'transcription_status': r.transcription_status or 'skipped',
                'transcription_language': r.transcription_language or '',
                'tone_label': tone.tone_label if tone else '',
                'tone_score': tone.tone_score if tone else 0,
                'has_audio': bool(r.recording_attachment_id),
            })
        return {'recordings': out}
