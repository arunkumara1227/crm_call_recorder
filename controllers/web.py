"""Web client for crm_call_recorder — vanilla JS app at /calls.

Mirrors the textile_pos pattern: server-rendered HTML shell + JSON-RPC
endpoints under /calls/api/*. Standard Odoo session auth (no API keys).
"""

import json
import logging
import re
from datetime import timedelta

import odoo
from odoo import http, fields
from odoo.http import request
from markupsafe import Markup

_logger = logging.getLogger(__name__)


def _ok(**data):
    return {'ok': True, **data}


def _err(msg, **extra):
    return {'ok': False, 'error': msg, **extra}


def _is_manager():
    return request.env.user.has_group('crm_call_recorder.group_call_recorder_manager')


def _is_user():
    return request.env.user.has_group('crm_call_recorder.group_call_recorder_user')


def _require_manager():
    if not _is_manager():
        return _err('Manager access required')
    return None


class CrmCallRecorderWeb(http.Controller):

    # ─── Login / logout / shell ────────────────────────────────────────

    @http.route('/calls/login', type='http', auth='public', website=False)
    def login_page(self, **kw):
        if request.session.uid and not kw.get('error'):
            return request.redirect('/calls')
        return request.render('crm_call_recorder.web_login', {
            'error': kw.get('error', ''),
        })

    @http.route('/calls/login/submit', type='http', auth='none',
                methods=['POST'], csrf=False)
    def login_submit(self, **kw):
        login = kw.get('login', '')
        password = kw.get('password', '')
        try:
            credential = {'type': 'password', 'login': login, 'password': password}
            auth_info = request.session.authenticate(request.env, credential)
            if auth_info.get('uid'):
                return request.redirect('/calls')
        except odoo.exceptions.AccessDenied:
            pass
        return request.redirect('/calls/login?error=Invalid+username+or+password')

    @http.route('/calls/logout', type='http', auth='user')
    def logout(self, **kw):
        request.session.logout(keep_db=True)
        return request.redirect('/calls/login')

    @http.route('/calls', type='http', auth='user', website=False)
    def main_app(self, **kw):
        if not _is_user():
            return request.render('crm_call_recorder.web_access_denied', {
                'user': request.env.user,
            })
        user_json = json.dumps({
            'id': request.env.user.id,
            'name': request.env.user.name,
            'is_manager': _is_manager(),
        })
        return request.render('crm_call_recorder.web_app', {
            'user': request.env.user,
            'is_manager': _is_manager(),
            'user_json': Markup(user_json),
        })

    # ─── Dashboard ─────────────────────────────────────────────────────

    @http.route('/calls/api/dashboard/devices', type='json',
                auth='user', csrf=False)
    def api_dashboard_devices(self):
        Devices = request.env['crm.call.device.summary'].sudo()
        records = Devices.search([], order='last_call_at desc')
        out = []
        for d in records:
            out.append({
                'id': d.id,
                'api_key_id': d.api_key_id.id,
                'device_name': d.device_name,
                'employee_id': d.employee_id.id if d.employee_id else 0,
                'employee_name': d.employee_id.name if d.employee_id else '',
                'total_calls': d.total_calls,
                'incoming_count': d.incoming_count,
                'outgoing_count': d.outgoing_count,
                'harsh_calls_count': d.harsh_calls_count,
                'avg_tone_score': round(d.avg_tone_score or 0.0, 1),
                'done_transcripts_count': d.done_transcripts_count,
                'unique_contacts_count': d.unique_contacts_count,
                'last_call_at': fields.Datetime.to_string(d.last_call_at) if d.last_call_at else '',
                'last_contact_phone': d.last_contact_phone or '',
                'last_sim_label': d.last_sim_label or '',
                'last_used': fields.Datetime.to_string(d.api_key_id.last_used) if d.api_key_id.last_used else '',
                'has_wa_session': bool(d.wa_employee_session_id),
                'wa_session_id': d.wa_employee_session_id.id if d.wa_employee_session_id else 0,
                'wa_message_count': d.wa_message_count,
                'wa_tone_count': d.wa_tone_count,
                'wa_log_count': d.wa_log_count,
            })
        return _ok(devices=out)

    # ─── Recordings ────────────────────────────────────────────────────

    @http.route('/calls/api/recordings/list', type='json',
                auth='user', csrf=False)
    def api_recordings_list(self, device_id=None, phone=None,
                            date_from=None, date_to=None,
                            transcription_status=None, tone_label=None,
                            state=None, limit=200):
        domain = []
        if device_id:
            domain.append(('created_by_api_key_id', '=', int(device_id)))
        if phone:
            digits = re.sub(r'\D', '', str(phone))
            if digits:
                domain.append(('phone_digits', 'ilike', digits))
        if date_from:
            domain.append(('call_date', '>=', date_from + ' 00:00:00'))
        if date_to:
            domain.append(('call_date', '<=', date_to + ' 23:59:59'))
        if transcription_status:
            domain.append(('transcription_status', '=', transcription_status))
        if tone_label:
            domain.append(('tone_label', '=', tone_label))
        if state:
            domain.append(('state', '=', state))

        Rec = request.env['crm.call.recording'].sudo()
        recs = Rec.search(domain, order='call_date desc', limit=int(limit or 200))
        out = []
        for r in recs:
            out.append({
                'id': r.id,
                'phone': r.phone or '',
                'call_date': fields.Datetime.to_string(r.call_date) if r.call_date else '',
                'direction': r.direction or 'unknown',
                'duration_seconds': r.duration_seconds or 0,
                'duration_display': r.duration_display or '—',
                'state': r.state or 'pending',
                'matched_partner_id': r.matched_partner_id.id if r.matched_partner_id else 0,
                'matched_partner_name': r.matched_partner_id.name if r.matched_partner_id else '',
                'matched_lead_id': r.matched_lead_id.id if r.matched_lead_id else 0,
                'matched_lead_name': r.matched_lead_id.name if r.matched_lead_id else '',
                'device_id': r.created_by_api_key_id.id if r.created_by_api_key_id else 0,
                'device_name': r.created_by_api_key_id.name if r.created_by_api_key_id else '',
                'sim_label': r.sim_label or '',
                'transcription_status': r.transcription_status or 'skipped',
                'tone_label': r.tone_label or '',
                'tone_score': r.tone_score or 0,
                'has_recording': r.has_recording,
            })
        return _ok(recordings=out)

    @http.route('/calls/api/recordings/<int:rec_id>', type='json',
                auth='user', csrf=False)
    def api_recording_detail(self, rec_id):
        rec = request.env['crm.call.recording'].sudo().browse(rec_id)
        if not rec.exists():
            return _err('Recording not found')
        return _ok(recording={
            'id': rec.id,
            'phone': rec.phone or '',
            'call_date': fields.Datetime.to_string(rec.call_date) if rec.call_date else '',
            'direction': rec.direction or 'unknown',
            'duration_seconds': rec.duration_seconds or 0,
            'duration_display': rec.duration_display or '—',
            'state': rec.state or 'pending',
            'sim_label': rec.sim_label or '',
            'note': rec.note or '',
            'matched_partner_id': rec.matched_partner_id.id if rec.matched_partner_id else 0,
            'matched_partner_name': rec.matched_partner_id.name if rec.matched_partner_id else '',
            'matched_lead_id': rec.matched_lead_id.id if rec.matched_lead_id else 0,
            'matched_lead_name': rec.matched_lead_id.name if rec.matched_lead_id else '',
            'device_id': rec.created_by_api_key_id.id if rec.created_by_api_key_id else 0,
            'device_name': rec.created_by_api_key_id.name if rec.created_by_api_key_id else '',
            'audio_url': rec.recording_url or '',
            'has_recording': rec.has_recording,
            'transcription_status': rec.transcription_status or 'skipped',
            'transcription_text': rec.transcription_text or '',
            'transcription_language': rec.transcription_language or '',
            'transcription_provider_used': rec.transcription_provider_used or '',
            'transcription_error': rec.transcription_error or '',
            'tone_label': rec.tone_label or '',
            'tone_score': rec.tone_score or 0,
            'tone_category': rec.tone_category or '',
        })

    @http.route('/calls/api/recordings/<int:rec_id>/retranscribe',
                type='json', auth='user', csrf=False)
    def api_recording_retranscribe(self, rec_id):
        rec = request.env['crm.call.recording'].sudo().browse(rec_id)
        if not rec.exists():
            return _err('Recording not found')
        try:
            rec.action_transcribe_now()
        except Exception as e:
            return _err(str(e))
        return _ok()

    @http.route('/calls/api/recordings/<int:rec_id>/reanalyze_tone',
                type='json', auth='user', csrf=False)
    def api_recording_reanalyze(self, rec_id):
        rec = request.env['crm.call.recording'].sudo().browse(rec_id)
        if not rec.exists():
            return _err('Recording not found')
        try:
            rec.action_reanalyze_tone()
        except Exception as e:
            return _err(str(e))
        return _ok()

    @http.route('/calls/api/recordings/<int:rec_id>/relink',
                type='json', auth='user', csrf=False)
    def api_recording_relink(self, rec_id):
        rec = request.env['crm.call.recording'].sudo().browse(rec_id)
        if not rec.exists():
            return _err('Recording not found')
        try:
            rec.action_relink()
        except Exception as e:
            return _err(str(e))
        return _ok()

    @http.route('/calls/api/recordings/<int:rec_id>/note',
                type='json', auth='user', csrf=False)
    def api_recording_note(self, rec_id, note=''):
        rec = request.env['crm.call.recording'].sudo().browse(rec_id)
        if not rec.exists():
            return _err('Recording not found')
        rec.note = note or ''
        return _ok()

    # ─── Tone Report ───────────────────────────────────────────────────

    @http.route('/calls/api/tone/devices', type='json',
                auth='user', csrf=False)
    def api_tone_devices(self):
        Keys = request.env['crm.call.api.key'].sudo()
        keys = Keys.search([('active', '=', True)], order='name')
        return _ok(devices=[
            {
                'id': k.id,
                'name': k.name,
                'employee_name': k.employee_id.name if k.employee_id else '',
            } for k in keys
        ])

    def _build_tone_wizard(self, channel, api_key_id, date_range,
                           date_from, date_to, phone_contains):
        Report = request.env['crm.call.tone.report'].sudo()
        return Report.create({
            'channel': channel or 'calls',
            'api_key_id': int(api_key_id),
            'date_range': date_range or 'today',
            'date_from': date_from or False,
            'date_to': date_to or False,
            'phone_contains': phone_contains or False,
        })

    @http.route('/calls/api/tone/report', type='json',
                auth='user', csrf=False)
    def api_tone_report(self, channel='calls', api_key_id=None,
                        date_range='today', date_from=None, date_to=None,
                        phone_contains=None):
        if not api_key_id:
            return _ok(report=None)
        wizard = self._build_tone_wizard(
            channel, api_key_id, date_range, date_from, date_to, phone_contains,
        )
        return _ok(report={
            'count_soft': wizard.count_soft,
            'count_neutral': wizard.count_neutral,
            'count_hard': wizard.count_hard,
            'count_total': wizard.count_total,
            'count_soft_calls': wizard.count_soft_calls,
            'count_neutral_calls': wizard.count_neutral_calls,
            'count_hard_calls': wizard.count_hard_calls,
            'count_soft_wa': wizard.count_soft_wa,
            'count_neutral_wa': wizard.count_neutral_wa,
            'count_hard_wa': wizard.count_hard_wa,
        })

    @http.route('/calls/api/tone/drill', type='json',
                auth='user', csrf=False)
    def api_tone_drill(self, kind='calls', tone_label='Soft', api_key_id=None,
                       date_range='today', date_from=None, date_to=None,
                       phone_contains=None):
        if not api_key_id:
            return _ok(items=[])
        wizard = self._build_tone_wizard(
            kind, api_key_id, date_range, date_from, date_to, phone_contains,
        )
        if kind == 'wa':
            wa_domain = wizard._get_wa_base_domain()
            if wa_domain is None:
                return _ok(items=[])
            WaTone = request.env.get('wa.message.tone')
            if WaTone is None:
                return _ok(items=[])
            tones = WaTone.sudo().search(
                wa_domain + [('tone_label', '=', tone_label)], limit=200,
            )
            return _ok(items=[
                {
                    'id': t.id,
                    'kind': 'wa',
                    'label': getattr(t, 'message_text', '') or getattr(t, 'name', '') or '',
                    'date': fields.Datetime.to_string(getattr(t, 'message_date', None))
                            if getattr(t, 'message_date', None) else '',
                    'tone_label': t.tone_label,
                    'tone_score': getattr(t, 'tone_score', 0),
                } for t in tones
            ])
        # calls
        CallTone = request.env['crm.call.tone'].sudo()
        domain = wizard._get_base_domain() + [('tone_label', '=', tone_label)]
        tones = CallTone.search(domain, limit=200)
        return _ok(items=[
            {
                'id': t.id,
                'kind': 'call',
                'recording_id': t.recording_id.id,
                'label': t.phone or '',
                'date': fields.Datetime.to_string(t.call_date) if t.call_date else '',
                'tone_label': t.tone_label,
                'tone_score': t.tone_score,
            } for t in tones
        ])

    # ─── API Keys ──────────────────────────────────────────────────────

    @http.route('/calls/api/apikeys/list', type='json',
                auth='user', csrf=False)
    def api_apikeys_list(self):
        Keys = request.env['crm.call.api.key'].sudo()
        if _is_manager():
            keys = Keys.search([])
        else:
            keys = Keys.search([('user_id', '=', request.env.user.id)])
        return _ok(keys=[
            {
                'id': k.id,
                'name': k.name,
                'key_prefix': k.key_prefix or '',
                'user_id': k.user_id.id,
                'user_name': k.user_id.name,
                'employee_id': k.employee_id.id if k.employee_id else 0,
                'employee_name': k.employee_id.name if k.employee_id else '',
                'active': k.active,
                'last_used': fields.Datetime.to_string(k.last_used) if k.last_used else '',
                'last_used_ip': k.last_used_ip or '',
                'recording_count': k.recording_count,
            } for k in keys
        ])

    @http.route('/calls/api/apikeys/employees', type='json',
                auth='user', csrf=False)
    def api_apikeys_employees(self):
        Emp = request.env['hr.employee'].sudo()
        emps = Emp.search([], order='name', limit=500)
        return _ok(employees=[{'id': e.id, 'name': e.name} for e in emps])

    @http.route('/calls/api/apikeys/generate', type='json',
                auth='user', csrf=False)
    def api_apikeys_generate(self, name=None, employee_id=None):
        if not name:
            return _err('Name is required')
        Keys = request.env['crm.call.api.key'].sudo()
        vals = {'name': name, 'user_id': request.env.user.id}
        if employee_id:
            vals['employee_id'] = int(employee_id)
        rec = Keys.create(vals)
        action = rec.action_generate_key()
        raw_key = (action or {}).get('context', {}).get('default_api_key', '')
        return _ok(id=rec.id, key=raw_key, key_prefix=rec.key_prefix)

    @http.route('/calls/api/apikeys/<int:key_id>/revoke', type='json',
                auth='user', csrf=False)
    def api_apikeys_revoke(self, key_id):
        err = _require_manager()
        if err:
            return err
        rec = request.env['crm.call.api.key'].sudo().browse(key_id)
        if not rec.exists():
            return _err('Key not found')
        rec.active = False
        return _ok()

    # ─── Voice config (manager) ────────────────────────────────────────

    @http.route('/calls/api/voice/get', type='json',
                auth='user', csrf=False)
    def api_voice_get(self):
        err = _require_manager()
        if err:
            return err
        cfg = request.env['crm.call.voice.config'].sudo().get_config()
        return _ok(config={
            'id': cfg.id,
            'transcription_enabled': cfg.transcription_enabled,
            'transcription_provider': cfg.transcription_provider,
            'translate_to_english': cfg.translate_to_english,
            'gemini_api_key': cfg.gemini_api_key or '',
            'gemini_model': cfg.gemini_model,
            'gemini_custom_model': cfg.gemini_custom_model or '',
            'groq_api_key': cfg.groq_api_key or '',
            'groq_model': cfg.groq_model or '',
            'openai_api_key': cfg.openai_api_key or '',
            'openai_model': cfg.openai_model,
            'ffmpeg_path': cfg.ffmpeg_path or '',
            'status_message': cfg.status_message or '',
        })

    @http.route('/calls/api/voice/save', type='json',
                auth='user', csrf=False)
    def api_voice_save(self, **vals):
        err = _require_manager()
        if err:
            return err
        cfg = request.env['crm.call.voice.config'].sudo().get_config()
        allowed = {
            'transcription_enabled', 'transcription_provider',
            'translate_to_english',
            'gemini_api_key', 'gemini_model', 'gemini_custom_model',
            'groq_api_key', 'groq_model',
            'openai_api_key', 'openai_model',
            'ffmpeg_path',
        }
        write_vals = {k: v for k, v in vals.items() if k in allowed}
        cfg.write(write_vals)
        return _ok()

    @http.route('/calls/api/voice/test', type='json',
                auth='user', csrf=False)
    def api_voice_test(self):
        err = _require_manager()
        if err:
            return err
        cfg = request.env['crm.call.voice.config'].sudo().get_config()
        try:
            cfg.action_test_connection()
        except Exception as e:
            return _err(str(e))
        return _ok(status_message=cfg.status_message or '')

    # ─── Tone keywords (manager) ───────────────────────────────────────

    @http.route('/calls/api/keywords/list', type='json',
                auth='user', csrf=False)
    def api_keywords_list(self):
        err = _require_manager()
        if err:
            return err
        Kw = request.env['crm.call.tone.keyword'].sudo()
        items = Kw.search([])
        return _ok(keywords=[
            {
                'id': k.id,
                'name': k.name,
                'category': k.category,
                'match_type': k.match_type,
                'keywords': k.keywords or '',
                'active': k.active,
                'sequence': k.sequence,
                'description': k.description or '',
            } for k in items
        ])

    @http.route('/calls/api/keywords/save', type='json',
                auth='user', csrf=False)
    def api_keywords_save(self, id=None, **vals):
        err = _require_manager()
        if err:
            return err
        Kw = request.env['crm.call.tone.keyword'].sudo()
        allowed = {'name', 'category', 'match_type', 'keywords',
                   'sequence', 'active', 'description'}
        write_vals = {k: v for k, v in vals.items() if k in allowed}
        try:
            if id:
                rec = Kw.browse(int(id))
                if not rec.exists():
                    return _err('Rule not found')
                rec.write(write_vals)
            else:
                if not write_vals.get('name'):
                    return _err('Name is required')
                if not write_vals.get('keywords'):
                    return _err('Keywords are required')
                write_vals.setdefault('category', 'soft')
                write_vals.setdefault('match_type', 'contains')
                rec = Kw.create(write_vals)
        except Exception as e:
            return _err(str(e))
        return _ok(id=rec.id)

    @http.route('/calls/api/keywords/<int:kw_id>/delete', type='json',
                auth='user', csrf=False)
    def api_keywords_delete(self, kw_id):
        err = _require_manager()
        if err:
            return err
        rec = request.env['crm.call.tone.keyword'].sudo().browse(kw_id)
        if not rec.exists():
            return _err('Rule not found')
        rec.active = False
        return _ok()

    # ─── Contact search (relink helper) ────────────────────────────────

    @http.route('/calls/api/contacts/search', type='json',
                auth='user', csrf=False)
    def api_contacts_search(self, q='', limit=20):
        if not q or len(q) < 2:
            return _ok(contacts=[])
        Partner = request.env['res.partner'].sudo()
        partners = Partner.search([
            '|', '|',
            ('name', 'ilike', q),
            ('phone', 'ilike', q),
            ('mobile', 'ilike', q),
        ], limit=int(limit or 20))
        return _ok(contacts=[
            {
                'id': p.id,
                'name': p.name,
                'phone': p.phone or p.mobile or '',
                'email': p.email or '',
            } for p in partners
        ])

    # ─── CRM WhatsApp — employee sessions admin ────────────────────────

    @http.route('/calls/api/wa/whatsapp_sessions', type='json',
                auth='user', csrf=False)
    def api_wa_whatsapp_sessions(self):
        """List paired neonize whatsapp.session records (one per phone/QR)."""
        WaSess = request.env.get('whatsapp.session')
        if WaSess is None:
            return _ok(sessions=[])
        recs = WaSess.sudo().search([], order='name')
        return _ok(sessions=[
            {
                'id': r.id,
                'name': r.name or '',
                'status': getattr(r, 'status', '') or '',
                'phone_number': getattr(r, 'phone_number', '') or '',
            } for r in recs
        ])

    @http.route('/calls/api/wa/sessions/list', type='json',
                auth='user', csrf=False)
    def api_wa_sessions_list(self):
        """List existing wa.employee.session rows for the WA Sessions admin tab."""
        Sess = request.env.get('wa.employee.session')
        if Sess is None:
            return _ok(sessions=[])
        recs = Sess.sudo().search([], order='employee_id')
        return _ok(sessions=[
            {
                'id': s.id,
                'employee_id': s.employee_id.id if s.employee_id else 0,
                'employee_name': s.employee_id.name if s.employee_id else '',
                'whatsapp_session_id': s.session_id.id if s.session_id else 0,
                'whatsapp_session_name': s.session_id.name if s.session_id else '',
                'phone_number': s.phone_number or '',
                'session_status': s.session_status or '',
                'monitoring_enabled': bool(s.monitoring_enabled),
                'total_messages': s.total_messages or 0,
                'last_activity': fields.Datetime.to_string(s.last_activity) if s.last_activity else '',
            } for s in recs
        ])

    @http.route('/calls/api/wa/sessions/create', type='json',
                auth='user', csrf=False)
    def api_wa_sessions_create(self, employee_id=None, whatsapp_session_id=None,
                               monitoring_enabled=True):
        """Pair an employee with an existing whatsapp.session."""
        if not employee_id or not whatsapp_session_id:
            return _err('Employee and WhatsApp session are both required')
        if 'wa.employee.session' not in request.env:
            return _err('CRM WhatsApp module not available')
        WaSess = request.env['whatsapp.session'].sudo().browse(int(whatsapp_session_id))
        if not WaSess.exists():
            return _err('WhatsApp session not found')
        existing = request.env['wa.employee.session'].sudo().search([
            '|', ('employee_id', '=', int(employee_id)),
                 ('session_id', '=', WaSess.id),
        ], limit=1)
        if existing:
            return _err('That employee or session is already paired')
        try:
            rec = request.env['wa.employee.session'].sudo().create({
                'employee_id': int(employee_id),
                'session_id': WaSess.id,
                'phone_number': getattr(WaSess, 'phone_number', '') or WaSess.name or '',
                'monitoring_enabled': bool(monitoring_enabled),
            })
        except Exception as e:
            return _err(str(e))
        return _ok(id=rec.id)

    @http.route('/calls/api/wa/sessions/<int:sess_id>/toggle_monitoring',
                type='json', auth='user', csrf=False)
    def api_wa_sessions_toggle(self, sess_id):
        Sess = request.env.get('wa.employee.session')
        if Sess is None:
            return _err('CRM WhatsApp module not available')
        rec = Sess.sudo().browse(sess_id)
        if not rec.exists():
            return _err('Session not found')
        rec.monitoring_enabled = not rec.monitoring_enabled
        return _ok(monitoring_enabled=rec.monitoring_enabled)

    @http.route('/calls/api/wa/sessions/<int:sess_id>/delete',
                type='json', auth='user', csrf=False)
    def api_wa_sessions_delete(self, sess_id):
        err = _require_manager()
        if err:
            return err
        Sess = request.env.get('wa.employee.session')
        if Sess is None:
            return _err('CRM WhatsApp module not available')
        rec = Sess.sudo().browse(sess_id)
        if not rec.exists():
            return _err('Session not found')
        rec.unlink()
        return _ok()

    # ─── CRM WhatsApp — chat monitoring (read-only) ────────────────────

    @http.route('/calls/api/wa/chat_sessions', type='json',
                auth='user', csrf=False)
    def api_wa_chat_sessions(self):
        """Mirror of /wa_tracker/employee_sessions but under our SPA's namespace."""
        Sess = request.env.get('wa.employee.session')
        if Sess is None:
            return _ok(sessions=[])
        recs = Sess.sudo().search([], order='employee_id')
        return _ok(sessions=[
            {
                'id': s.id,
                'name': s.employee_id.name or s.session_id.name or ('Session %s' % s.id),
                'employee_id': s.employee_id.id if s.employee_id else 0,
                'phone': s.phone_number or '',
                'status': s.session_status or '',
                'monitoring_enabled': bool(s.monitoring_enabled),
            } for s in recs
        ])

    @http.route('/calls/api/wa/chat_conversations', type='json',
                auth='user', csrf=False)
    def api_wa_chat_conversations(self, employee_session_id=None, search=None, limit=200):
        Conv = request.env.get('wa.conversation')
        if Conv is None:
            return _ok(conversations=[])
        domain = []
        if employee_session_id:
            domain.append(('employee_session_id', '=', int(employee_session_id)))
        convs = Conv.sudo().search(domain, order='last_message_date desc', limit=int(limit or 200))

        # Pre-fetch latest push_names for the phone numbers in this batch.
        Msg = request.env.get('whatsapp.message')
        push_name_map = {}
        if Msg is not None:
            phones = [c.phone for c in convs if c.phone]
            if phones:
                msgs = Msg.sudo().search([
                    ('phone', 'in', phones),
                    ('push_name', '!=', False),
                    ('push_name', '!=', ''),
                ], order='create_date desc')
                for m in msgs:
                    if m.phone not in push_name_map:
                        push_name_map[m.phone] = m.push_name

        out = []
        for c in convs:
            raw_phone = c.phone or ''
            push_name = push_name_map.get(raw_phone, '')
            # Prefer push_name when contact_name is just a phone fallback
            digits_only = ''.join(filter(str.isdigit, c.contact_name or ''))
            display_name = push_name or (c.contact_name if digits_only != (c.contact_name or '').strip('+') else '') or c.contact_name or 'Unknown'
            phone_digits = ''.join(filter(str.isdigit, raw_phone))
            formatted_phone = ('+' + phone_digits) if phone_digits else raw_phone

            if search:
                s = search.lower()
                if s not in (display_name or '').lower() and s not in formatted_phone.lower():
                    continue

            out.append({
                'id': c.id,
                'contact_name': display_name,
                'phone': formatted_phone,
                'total_messages': c.total_messages or 0,
                'sent_count': c.sent_count or 0,
                'received_count': c.received_count or 0,
                'last_message_date': fields.Datetime.to_string(c.last_message_date) if c.last_message_date else '',
                'is_active_today': bool(c.is_active_today),
                'last_message_preview': c.last_message_preview or '',
                'employee_name': c.employee_id.name if c.employee_id else '',
                'employee_session_id': c.employee_session_id.id if c.employee_session_id else 0,
                'is_group_message': any(l.is_group_message for l in c.log_ids[:1]) if c.log_ids else False,
            })
        return _ok(conversations=out)

    @http.route('/calls/api/wa/chat_messages', type='json',
                auth='user', csrf=False)
    def api_wa_chat_messages(self, conversation_id=None, limit=500):
        if not conversation_id:
            return _ok(messages=[])
        Log = request.env.get('wa.communication.log')
        if Log is None:
            return _ok(messages=[])
        logs = Log.sudo().search(
            [('conversation_id', '=', int(conversation_id))],
            order='message_date asc',
            limit=int(limit or 500),
        )
        return _ok(messages=[
            {
                'id': l.id,
                'text': l.message_text or '',
                'direction': l.direction or 'incoming',
                'date': fields.Datetime.to_string(l.message_date) if l.message_date else '',
                'status': l.status or '',
                'is_flagged': bool(l.is_flagged),
                'is_voice': bool(l.is_voice_message),
                'voice_transcription': l.voice_transcription or '',
                'voice_language': l.voice_language or '',
            } for l in logs
        ])

    # ─── Notifications panel ───────────────────────────────────────────

    # Diagnostic ping — if this 404s, the routes block isn't registering.
    @http.route('/calls/api/notifications/ping', type='json',
                auth='user', csrf=False)
    def api_notifications_ping(self):
        return _ok(message='pong')

    # Alternate-path alias to /calls/api/alerts/list — if this works but
    # /calls/api/notifications/list doesn't, the issue is path-cache.
    @http.route('/calls/api/alerts/list', type='json',
                auth='user', csrf=False)
    def api_alerts_list(self, limit=50):
        return self.api_notifications_list(limit=limit)

    def _notif_last_seen_key(self):
        return 'crm_call_recorder.notif_last_seen.%s' % request.env.user.id

    def _get_notif_last_seen(self):
        Param = request.env['ir.config_parameter'].sudo()
        v = Param.get_param(self._notif_last_seen_key())
        return v or '1970-01-01 00:00:00'

    @http.route('/calls/api/notifications/list', type='json',
                auth='user', csrf=False)
    def api_notifications_list(self, limit=50):
        env = request.env
        items = []

        # 1. Harsh-tone calls — last 7 days, my devices preferred but show all
        Recording = env['crm.call.recording'].sudo()
        seven_days_ago = (fields.Datetime.now() - timedelta(days=7))
        harsh = Recording.search([
            ('tone_label', '=', 'Hard'),
            ('call_date', '>=', fields.Datetime.to_string(seven_days_ago)),
        ], order='call_date desc', limit=int(limit))
        for r in harsh:
            items.append({
                'kind': 'harsh_tone',
                'id': r.id,
                'title': 'Harsh call: %s' % (r.matched_partner_id.name or r.phone or ''),
                'subtitle': '%s · %s' % (
                    r.created_by_api_key_id.name if r.created_by_api_key_id else '',
                    fields.Datetime.to_string(r.call_date) if r.call_date else '',
                ),
                'date': fields.Datetime.to_string(r.call_date) if r.call_date else '',
                'phone': r.phone or '',
                'recording_id': r.id,
                'severity': 'danger',
            })

        # 2. Unanswered WA — incoming logs in last 24h with no later outgoing
        CommLog = env.get('wa.communication.log')
        if CommLog is not None:
            one_day_ago = fields.Datetime.now() - timedelta(days=1)
            incoming = CommLog.sudo().search([
                ('direction', '=', 'incoming'),
                ('message_date', '>=', fields.Datetime.to_string(one_day_ago)),
            ], order='message_date desc', limit=int(limit))
            for ic in incoming:
                # Skip if a later outgoing exists in same conversation
                later = CommLog.sudo().search_count([
                    ('conversation_id', '=', ic.conversation_id.id),
                    ('direction', '=', 'outgoing'),
                    ('message_date', '>', ic.message_date),
                ]) if ic.conversation_id else 0
                if later:
                    continue
                items.append({
                    'kind': 'unanswered_wa',
                    'id': ic.id,
                    'title': 'Unanswered WhatsApp: %s' % (
                        ic.conversation_id.contact_name or ic.phone or 'Unknown'
                    ),
                    'subtitle': (ic.message_text or '')[:80],
                    'date': fields.Datetime.to_string(ic.message_date) if ic.message_date else '',
                    'phone': ic.phone or '',
                    'conversation_id': ic.conversation_id.id if ic.conversation_id else 0,
                    'employee_session_id': ic.employee_session_id.id if ic.employee_session_id else 0,
                    'severity': 'warning',
                })

        # 3. Overdue activities for current user
        Activity = env['mail.activity'].sudo()
        today = fields.Date.today()
        my_activities = Activity.search([
            ('user_id', '=', env.user.id),
            ('date_deadline', '<', fields.Date.to_string(today)),
        ], order='date_deadline asc', limit=int(limit))
        for a in my_activities:
            items.append({
                'kind': 'overdue_activity',
                'id': a.id,
                'title': a.summary or (a.activity_type_id.name if a.activity_type_id else 'Activity'),
                'subtitle': 'Due %s · %s' % (
                    fields.Date.to_string(a.date_deadline) if a.date_deadline else '',
                    a.res_name or '',
                ),
                'date': fields.Datetime.to_string(a.create_date) if a.create_date else '',
                'res_model': a.res_model or '',
                'res_id': a.res_id or 0,
                'severity': 'warning',
            })

        # 4. Unmatched recordings older than 1h
        one_hour_ago = fields.Datetime.now() - timedelta(hours=1)
        unmatched = Recording.search([
            ('state', '=', 'unmatched'),
            ('call_date', '<', fields.Datetime.to_string(one_hour_ago)),
        ], order='call_date desc', limit=int(limit))
        for r in unmatched:
            items.append({
                'kind': 'unmatched_rec',
                'id': r.id,
                'title': 'Unmatched recording: %s' % (r.phone or ''),
                'subtitle': fields.Datetime.to_string(r.call_date) if r.call_date else '',
                'date': fields.Datetime.to_string(r.call_date) if r.call_date else '',
                'phone': r.phone or '',
                'recording_id': r.id,
                'severity': 'secondary',
            })

        # Sort all by date desc, slice to limit
        items.sort(key=lambda x: x.get('date') or '', reverse=True)
        items = items[:int(limit)]

        last_seen = self._get_notif_last_seen()
        unread = sum(1 for it in items if (it.get('date') or '') > last_seen)

        return _ok(notifications=items, unread=unread, last_seen=last_seen)

    @http.route('/calls/api/notifications/mark_read', type='json',
                auth='user', csrf=False)
    def api_notifications_mark_read(self):
        now = fields.Datetime.to_string(fields.Datetime.now())
        request.env['ir.config_parameter'].sudo().set_param(
            self._notif_last_seen_key(), now,
        )
        return _ok(last_seen=now)

    # ─── Leads / Pipeline ──────────────────────────────────────────────

    @http.route('/calls/api/leads/stages', type='json',
                auth='user', csrf=False)
    def api_leads_stages(self):
        Stage = request.env['crm.stage'].sudo()
        stages = Stage.search([], order='sequence asc')
        return _ok(stages=[{
            'id': s.id,
            'name': s.name or '',
            'sequence': s.sequence or 0,
            'is_won': bool(getattr(s, 'is_won', False)),
            'fold': bool(getattr(s, 'fold', False)),
            'lead_count': request.env['crm.lead'].sudo().search_count(
                [('stage_id', '=', s.id), ('active', '=', True)]),
        } for s in stages])

    @http.route('/calls/api/leads/list', type='json',
                auth='user', csrf=False)
    def api_leads_list(self, stage_id=None, search=None, limit=200):
        Lead = request.env['crm.lead'].sudo()
        domain = [('active', '=', True)]
        if stage_id:
            domain.append(('stage_id', '=', int(stage_id)))
        if search and search.strip():
            q = search.strip()
            domain += ['|', '|', '|',
                       ('name', 'ilike', q),
                       ('phone', 'ilike', q),
                       ('partner_id.name', 'ilike', q),
                       ('email_from', 'ilike', q) if 'email_from' in Lead._fields else ('name', 'ilike', q)]
        leads = Lead.search(domain, order='priority desc, create_date desc', limit=int(limit))
        Recording = request.env['crm.call.recording'].sudo()

        def rec_count_for(phone):
            if not phone:
                return 0
            digits = re.sub(r'\D', '', phone)[-10:]
            return Recording.search_count(
                [('phone_digits', 'ilike', digits)]) if digits else 0

        return _ok(leads=[{
            'id': ld.id,
            'name': ld.name or '',
            'partner_id': ld.partner_id.id if ld.partner_id else 0,
            'partner_name': ld.partner_id.name if ld.partner_id else '',
            'phone': ld.phone or '',
            'email': (ld.email_from or '') if 'email_from' in Lead._fields else '',
            'stage_id': ld.stage_id.id if ld.stage_id else 0,
            'stage_name': ld.stage_id.name if ld.stage_id else '',
            'expected_revenue': float(ld.expected_revenue or 0),
            'probability': float(ld.probability or 0),
            'priority': ld.priority or '0',
            'user_id': ld.user_id.id if ld.user_id else 0,
            'user_name': ld.user_id.name if ld.user_id else '',
            'days_in_stage': (
                (fields.Datetime.now() - ld.date_last_stage_update).days
                if hasattr(ld, 'date_last_stage_update') and ld.date_last_stage_update else 0
            ),
            'create_date': fields.Datetime.to_string(ld.create_date) if ld.create_date else '',
            'recording_count': rec_count_for(ld.phone),
        } for ld in leads])

    @http.route('/calls/api/leads/<int:lead_id>', type='json',
                auth='user', csrf=False)
    def api_lead_detail(self, lead_id):
        Lead = request.env['crm.lead'].sudo()
        lead = Lead.browse(int(lead_id))
        if not lead.exists():
            return _err('Lead not found')

        digits = re.sub(r'\D', '', lead.phone or '')[-10:] if lead.phone else ''
        Recording = request.env['crm.call.recording'].sudo()
        CommLog = request.env.get('wa.communication.log')
        Activity = request.env['mail.activity'].sudo()

        recs = Recording.search(
            [('phone_digits', 'ilike', digits)], order='call_date desc', limit=50,
        ) if digits else Recording.browse()
        wa_logs = (CommLog.sudo().search(
            [('phone', 'ilike', digits)], order='message_date desc', limit=50,
        ) if (CommLog is not None and digits) else [])
        activities = Activity.search(
            [('res_model', '=', 'crm.lead'), ('res_id', '=', lead.id)],
            order='date_deadline asc',
        )

        return _ok(
            lead={
                'id': lead.id,
                'name': lead.name or '',
                'description': lead.description or '',
                'partner_id': lead.partner_id.id if lead.partner_id else 0,
                'partner_name': lead.partner_id.name if lead.partner_id else '',
                'phone': lead.phone or '',
                'email': (lead.email_from or '') if 'email_from' in Lead._fields else '',
                'stage_id': lead.stage_id.id if lead.stage_id else 0,
                'stage_name': lead.stage_id.name if lead.stage_id else '',
                'expected_revenue': float(lead.expected_revenue or 0),
                'probability': float(lead.probability or 0),
                'priority': lead.priority or '0',
                'user_id': lead.user_id.id if lead.user_id else 0,
                'user_name': lead.user_id.name if lead.user_id else '',
                'team_id': lead.team_id.id if lead.team_id else 0,
                'team_name': lead.team_id.name if lead.team_id else '',
                'create_date': fields.Datetime.to_string(lead.create_date) if lead.create_date else '',
            },
            recordings=[{
                'id': r.id,
                'phone': r.phone or '',
                'direction': r.direction or '',
                'duration_display': r.duration_display or '',
                'state': r.state or '',
                'tone_label': r.tone_label or '',
                'call_date': fields.Datetime.to_string(r.call_date) if r.call_date else '',
            } for r in recs],
            wa_logs=[{
                'id': l.id,
                'phone': l.phone or '',
                'direction': l.direction or '',
                'text': l.message_text or '',
                'date': fields.Datetime.to_string(l.message_date) if l.message_date else '',
            } for l in wa_logs],
            activities=[{
                'id': a.id,
                'summary': a.summary or '',
                'type': a.activity_type_id.name if a.activity_type_id else '',
                'date_deadline': fields.Date.to_string(a.date_deadline) if a.date_deadline else '',
                'user_name': a.user_id.name if a.user_id else '',
            } for a in activities],
        )

    @http.route('/calls/api/leads/<int:lead_id>/move_stage', type='json',
                auth='user', csrf=False)
    def api_lead_move_stage(self, lead_id, stage_id=None):
        if not stage_id:
            return _err('stage_id required')
        lead = request.env['crm.lead'].sudo().browse(int(lead_id))
        if not lead.exists():
            return _err('Lead not found')
        stage = request.env['crm.stage'].sudo().browse(int(stage_id))
        if not stage.exists():
            return _err('Stage not found')
        lead.write({'stage_id': stage.id})
        return _ok()

    @http.route('/calls/api/leads/<int:lead_id>/mark_won', type='json',
                auth='user', csrf=False)
    def api_lead_mark_won(self, lead_id):
        lead = request.env['crm.lead'].sudo().browse(int(lead_id))
        if not lead.exists():
            return _err('Lead not found')
        won_stage = request.env['crm.stage'].sudo().search(
            [('is_won', '=', True)], order='sequence desc', limit=1)
        vals = {'probability': 100.0}
        if won_stage:
            vals['stage_id'] = won_stage.id
        lead.write(vals)
        return _ok()

    @http.route('/calls/api/leads/<int:lead_id>/mark_lost', type='json',
                auth='user', csrf=False)
    def api_lead_mark_lost(self, lead_id):
        lead = request.env['crm.lead'].sudo().browse(int(lead_id))
        if not lead.exists():
            return _err('Lead not found')
        # Odoo's standard "lost" pattern: probability=0 + active=False
        if hasattr(lead, 'action_set_lost'):
            try:
                lead.action_set_lost()
                return _ok()
            except Exception:
                pass
        lead.write({'probability': 0.0, 'active': False})
        return _ok()

    @http.route('/calls/api/leads/from_recording', type='json',
                auth='user', csrf=False)
    def api_lead_from_recording(self, recording_id=None, name=None,
                                expected_revenue=0, stage_id=None):
        if not recording_id:
            return _err('recording_id required')
        rec = request.env['crm.call.recording'].sudo().browse(int(recording_id))
        if not rec.exists():
            return _err('Recording not found')

        Stage = request.env['crm.stage'].sudo()
        stage = Stage.browse(int(stage_id)) if stage_id else False
        if not stage or not stage.exists():
            stage = Stage.search([], order='sequence asc', limit=1)

        title = (name or '').strip() or (
            'Call from %s' % (rec.matched_partner_id.name if rec.matched_partner_id else (rec.phone or 'unknown')))

        description_parts = []
        if rec.transcription_text:
            description_parts.append('Transcript:\n' + rec.transcription_text)
        if rec.tone_label:
            description_parts.append('Tone: %s' % rec.tone_label)
        description_parts.append('Source recording id: %s' % rec.id)

        vals = {
            'name': title,
            'phone': rec.phone or '',
            'expected_revenue': float(expected_revenue or 0),
            'description': '\n\n'.join(description_parts),
            'type': 'lead' if 'type' in request.env['crm.lead']._fields else False,
        }
        if rec.matched_partner_id:
            vals['partner_id'] = rec.matched_partner_id.id
        if stage:
            vals['stage_id'] = stage.id
        # Remove keys with False values that aren't optional
        vals = {k: v for k, v in vals.items() if v is not False}

        lead = request.env['crm.lead'].sudo().create(vals)
        # Link recording back to the new lead if not already linked
        if rec.matched_lead_id != lead:
            try:
                rec.write({'matched_lead_id': lead.id})
            except Exception:
                pass
        return _ok(lead_id=lead.id)

    @http.route('/calls/api/leads/from_phone', type='json',
                auth='user', csrf=False)
    def api_lead_from_phone(self, phone=None, name=None,
                            expected_revenue=0, stage_id=None,
                            description=None):
        """Create a crm.lead from a phone number (e.g. a WhatsApp contact).
        Looks up matched res.partner by phone digits using the same
        last-10-digit ilike pattern used elsewhere."""
        if not phone or not str(phone).strip():
            return _err('phone required')

        Stage = request.env['crm.stage'].sudo()
        stage = Stage.browse(int(stage_id)) if stage_id else False
        if not stage or not stage.exists():
            stage = Stage.search([], order='sequence asc', limit=1)

        digits = re.sub(r'\D', '', str(phone))[-10:]
        Partner = request.env['res.partner'].sudo()
        partner = Partner.search([('phone', 'ilike', digits)], limit=1) if digits else Partner.browse()
        if not partner and digits and 'mobile' in Partner._fields:
            partner = Partner.search([('mobile', 'ilike', digits)], limit=1)

        title = (name or '').strip() or (
            'Lead from %s' % (partner.name if partner else (phone or 'unknown')))

        vals = {
            'name': title,
            'phone': phone,
            'expected_revenue': float(expected_revenue or 0),
            'type': 'lead' if 'type' in request.env['crm.lead']._fields else False,
        }
        if description and description.strip():
            vals['description'] = description.strip()
        if partner:
            vals['partner_id'] = partner.id
        if stage:
            vals['stage_id'] = stage.id
        vals = {k: v for k, v in vals.items() if v is not False}

        lead = request.env['crm.lead'].sudo().create(vals)
        return _ok(lead_id=lead.id)

    # ─── CRM WhatsApp — outbound send ──────────────────────────────────

    @http.route('/calls/api/wa/send_message', type='json',
                auth='user', csrf=False)
    def api_wa_send_message(self, whatsapp_session_id=None, phone=None, text=None):
        """Send a WhatsApp text message via neonize. Reuses
        whatsapp.session.send_message() which also creates the
        whatsapp.message record + fires the bus push."""
        if not whatsapp_session_id or not phone or not text:
            return _err('session, phone and text are all required')
        if not text.strip():
            return _err('Message text is empty')
        WaSession = request.env.get('whatsapp.session')
        if WaSession is None:
            return _err('whatsapp_neonize not installed')
        sess = WaSession.sudo().browse(int(whatsapp_session_id))
        if not sess.exists():
            return _err('WhatsApp session not found')
        try:
            sess.send_message(phone, text)
        except Exception as e:
            return _err('Send failed: %s' % str(e))
        return _ok()

    # ─── Contact 360 — unified per-contact view ────────────────────────

    def _resolve_contact_key(self, key):
        """Parse 'phone:<digits>' or 'partner:<id>' into (partner, digits10)."""
        if not key:
            return None, ''
        Partner = request.env['res.partner'].sudo()
        if key.startswith('partner:'):
            try:
                partner = Partner.browse(int(key.split(':', 1)[1]))
            except (ValueError, IndexError):
                return None, ''
            if not partner.exists():
                return None, ''
            phone_raw = partner.phone or getattr(partner, 'mobile', '') or ''
            digits = re.sub(r'\D', '', phone_raw)[-10:] if phone_raw else ''
            return partner, digits
        if key.startswith('phone:'):
            digits = re.sub(r'\D', '', key.split(':', 1)[1])[-10:]
            if not digits or len(digits) < 7:
                return None, ''
            partner = Partner.search([('phone', 'ilike', digits)], limit=1)
            if not partner and 'mobile' in Partner._fields:
                partner = Partner.search([('mobile', 'ilike', digits)], limit=1)
            return (partner or None), digits
        return None, ''

    @http.route('/calls/api/contact/lookup', type='json',
                auth='user', csrf=False)
    def api_contact_lookup(self, phone=None, partner_id=None):
        """Return canonical contact key for a phone or partner id."""
        if partner_id:
            return _ok(key='partner:%s' % int(partner_id))
        if not phone:
            return _err('phone or partner_id required')
        digits = re.sub(r'\D', '', str(phone))[-10:]
        if not digits or len(digits) < 7:
            return _err('Phone too short')
        # If a partner exists, prefer the partner key (canonical).
        Partner = request.env['res.partner'].sudo()
        partner = Partner.search([('phone', 'ilike', digits)], limit=1)
        if not partner and 'mobile' in Partner._fields:
            partner = Partner.search([('mobile', 'ilike', digits)], limit=1)
        if partner:
            return _ok(key='partner:%s' % partner.id)
        return _ok(key='phone:%s' % digits)

    @http.route('/calls/api/contact/<string:key>/profile', type='json',
                auth='user', csrf=False)
    def api_contact_profile(self, key):
        partner, digits = self._resolve_contact_key(key)
        if not digits and not partner:
            return _err('Contact not found')

        Recording = request.env['crm.call.recording'].sudo()
        CommLog = request.env.get('wa.communication.log')
        Lead = request.env['crm.lead'].sudo()

        rec_domain = [('phone_digits', 'ilike', digits)] if digits else []
        recs = Recording.search(rec_domain) if rec_domain else Recording.browse()
        wa_logs = CommLog.sudo().search([('phone', 'ilike', digits)]) if (CommLog is not None and digits) else []
        leads = Lead.search([('phone', 'ilike', digits)]) if digits else Lead.browse()

        harsh_count = sum(1 for r in recs if r.tone_label == 'Hard')
        wa_msg_count = len(wa_logs) if wa_logs else 0
        last_activity = None
        for r in recs[:1]:
            last_activity = fields.Datetime.to_string(r.call_date) if r.call_date else None
        for l in wa_logs[:1] if wa_logs else []:
            wa_dt = fields.Datetime.to_string(l.message_date) if l.message_date else None
            if wa_dt and (not last_activity or wa_dt > last_activity):
                last_activity = wa_dt

        # Pick a display name: partner name > push_name from latest WA > phone
        display_name = partner.name if partner else ''
        if not display_name and wa_logs:
            Msg = request.env.get('whatsapp.message')
            if Msg is not None and digits:
                latest = Msg.sudo().search([
                    ('phone', 'ilike', digits),
                    ('push_name', '!=', False),
                    ('push_name', '!=', ''),
                ], order='create_date desc', limit=1)
                if latest:
                    display_name = latest.push_name
        if not display_name:
            display_name = '+' + digits if digits else 'Unknown'

        return _ok(profile={
            'key': key,
            'display_name': display_name,
            'partner_id': partner.id if partner else 0,
            'partner_name': partner.name if partner else '',
            'phone': ('+' + digits) if digits else '',
            'phone_digits': digits,
            'email': (partner.email if partner else '') or '',
            'is_company': bool(partner.is_company) if partner else False,
            'image': '/web/image/res.partner/%s/avatar_128' % partner.id if partner else '',
            'kpis': {
                'calls_total': len(recs),
                'calls_harsh': harsh_count,
                'wa_messages': wa_msg_count,
                'leads_count': len(leads),
                'last_activity': last_activity or '',
            },
        })

    @http.route('/calls/api/contact/<string:key>/timeline', type='json',
                auth='user', csrf=False)
    def api_contact_timeline(self, key, filter='all', limit=200):
        """Merged timeline. filter: all | calls | wa | leads | activities."""
        partner, digits = self._resolve_contact_key(key)
        if not digits and not partner:
            return _ok(items=[])

        items = []

        # Calls
        if filter in ('all', 'calls') and digits:
            Recording = request.env['crm.call.recording'].sudo()
            recs = Recording.search(
                [('phone_digits', 'ilike', digits)],
                order='call_date desc', limit=int(limit or 200),
            )
            for r in recs:
                items.append({
                    'type': 'call',
                    'id': r.id,
                    'date': fields.Datetime.to_string(r.call_date) if r.call_date else '',
                    'title': '%s call · %s' % (
                        (r.direction or 'unknown').title(),
                        r.duration_display or '—',
                    ),
                    'preview': (r.transcription_text or '')[:200],
                    'tone_label': r.tone_label or '',
                    'state': r.state or '',
                    'audio_url': r.recording_url or '',
                    'has_recording': bool(r.has_recording),
                    'sim_label': r.sim_label or '',
                })

        # WhatsApp
        if filter in ('all', 'wa') and digits:
            CommLog = request.env.get('wa.communication.log')
            if CommLog is not None:
                wa_logs = CommLog.sudo().search(
                    [('phone', 'ilike', digits)],
                    order='message_date desc', limit=int(limit or 200),
                )
                for l in wa_logs:
                    items.append({
                        'type': 'wa',
                        'id': l.id,
                        'date': fields.Datetime.to_string(l.message_date) if l.message_date else '',
                        'title': ('You: ' if l.direction == 'outgoing' else '') + (l.message_text or '')[:80],
                        'preview': l.message_text or '',
                        'direction': l.direction or 'incoming',
                        'is_flagged': bool(l.is_flagged),
                        'is_voice': bool(l.is_voice_message),
                        'voice_transcription': l.voice_transcription or '',
                    })

        # Leads
        if filter in ('all', 'leads') and digits:
            Lead = request.env['crm.lead'].sudo()
            leads = Lead.search(
                [('phone', 'ilike', digits)],
                order='create_date desc',
            )
            for ld in leads:
                items.append({
                    'type': 'lead',
                    'id': ld.id,
                    'date': fields.Datetime.to_string(ld.create_date) if ld.create_date else '',
                    'title': ld.name or 'Lead',
                    'preview': (ld.description or '')[:200],
                    'stage': ld.stage_id.name if ld.stage_id else '',
                    'expected_revenue': ld.expected_revenue or 0.0,
                    'probability': ld.probability or 0,
                })

        # Activities (mail.activity)
        if filter in ('all', 'activities'):
            Activity = request.env['mail.activity'].sudo()
            domain_or = []
            if partner:
                domain_or.append(['&', ('res_model', '=', 'res.partner'),
                                       ('res_id', '=', partner.id)])
            if digits:
                # call recordings
                rec_ids = request.env['crm.call.recording'].sudo().search(
                    [('phone_digits', 'ilike', digits)], limit=200,
                ).ids
                if rec_ids:
                    domain_or.append(['&', ('res_model', '=', 'crm.call.recording'),
                                           ('res_id', 'in', rec_ids)])
                lead_ids = request.env['crm.lead'].sudo().search(
                    [('phone', 'ilike', digits)], limit=200,
                ).ids
                if lead_ids:
                    domain_or.append(['&', ('res_model', '=', 'crm.lead'),
                                           ('res_id', 'in', lead_ids)])
            if domain_or:
                # OR the sub-domains
                domain = []
                for i in range(len(domain_or) - 1):
                    domain.append('|')
                for sub in domain_or:
                    domain.extend(sub)
                activities = Activity.search(domain, order='date_deadline asc')
                for a in activities:
                    items.append({
                        'type': 'activity',
                        'id': a.id,
                        'date': fields.Datetime.to_string(a.create_date) if a.create_date else '',
                        'date_deadline': fields.Date.to_string(a.date_deadline) if a.date_deadline else '',
                        'title': a.summary or (a.activity_type_id.name if a.activity_type_id else 'Activity'),
                        'preview': a.note or '',
                        'user_name': a.user_id.name if a.user_id else '',
                        'res_model': a.res_model or '',
                        'res_id': a.res_id or 0,
                    })

        # Sort merged feed by date desc (treat empty as oldest)
        items.sort(key=lambda x: x.get('date') or '', reverse=True)
        return _ok(items=items[:int(limit or 200)])
