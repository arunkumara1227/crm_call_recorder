import logging
from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class WaChatController(http.Controller):

    @http.route('/wa_tracker/employee_sessions', type='jsonrpc', auth='user')
    def get_employee_sessions(self):
        """Get list of employee sessions for filter dropdown."""
        sessions = request.env['wa.employee.session'].sudo().search([])
        result = []
        for s in sessions:
            result.append({
                'id': s.id,
                'name': s.employee_id.name or s.session_id.name or ('Session %s' % s.id),
                'phone': s.phone_number or '',
            })
        return result

    @http.route('/wa_tracker/conversations', type='jsonrpc', auth='user')
    def get_conversations(self, employee_session_id=None):
        """Get conversations list for the chat panel."""
        domain = []
        if employee_session_id:
            domain.append(('employee_session_id', '=', int(employee_session_id)))

        convs = request.env['wa.conversation'].sudo().search(
            domain, order='last_message_date desc'
        )
        # Pre-fetch push_names for all phones in one query
        phones = [c.phone for c in convs if c.phone]
        push_name_map = {}
        if phones:
            msgs = request.env['whatsapp.message'].sudo().search([
                ('phone', 'in', phones),
                ('push_name', '!=', False),
                ('push_name', '!=', ''),
            ], order='create_date desc')
            for m in msgs:
                if m.phone not in push_name_map:
                    push_name_map[m.phone] = m.push_name

        result = []
        for c in convs:
            # Use push_name > contact_name > phone as display name
            raw_phone = c.phone or ''
            push_name = push_name_map.get(raw_phone, '')
            # Strip non-digit chars to detect if contact_name is just a phone fallback
            digits_only = ''.join(filter(str.isdigit, c.contact_name or ''))
            contact_name = push_name or (c.contact_name if digits_only != (c.contact_name or '').strip('+') else '') or c.contact_name or 'Unknown'
            # Format phone: extract digits and add + prefix
            phone_digits = ''.join(filter(str.isdigit, raw_phone))
            formatted_phone = ('+' + phone_digits) if phone_digits else raw_phone
            result.append({
                'id': c.id,
                'contact_name': contact_name,
                'phone': formatted_phone,
                'total_messages': c.total_messages,
                'sent_count': c.sent_count,
                'received_count': c.received_count,
                'avg_response_minutes': c.avg_response_minutes,
                'last_message_date': str(c.last_message_date) if c.last_message_date else '',
                'is_active_today': c.is_active_today,
                'last_message_preview': c.last_message_preview or '',
                'employee_name': c.employee_id.name or '',
                'employee_session_id': c.employee_session_id.id if c.employee_session_id else None,
            })
        return result

    @http.route('/wa_tracker/messages', type='jsonrpc', auth='user')
    def get_messages(self, conversation_id):
        """Get messages for a conversation."""
        logs = request.env['wa.communication.log'].sudo().search([
            ('conversation_id', '=', int(conversation_id)),
        ], order='message_date asc')

        result = []
        for log in logs:
            result.append({
                'id': log.id,
                'message_text': log.message_text or '',
                'direction': log.direction,
                'message_date': str(log.message_date) if log.message_date else '',
                'status': log.status or '',
                'is_flagged': log.is_flagged,
            })
        return result
