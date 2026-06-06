"""HTTP API for the Android companion app.

The Android app POSTs each new call recording to /crm_call_recorder/upload
with a shared X-API-KEY header. The key is stored in the Odoo System
Parameter `crm_call_recorder.api_key` — change it on every install.
"""

import base64
import hmac
import json
import logging

from odoo import http, fields
from odoo.http import request

_logger = logging.getLogger(__name__)

# Max upload size — 50 MB covers any plausible call length at typical
# 16 kbps codec. Defensive: avoids accidentally accepting a gigabyte.
MAX_UPLOAD_BYTES = 50 * 1024 * 1024

# System Parameter that holds the shared API key
API_KEY_PARAM = 'crm_call_recorder.api_key'


def _json_response(payload, status=200):
    return request.make_response(
        json.dumps(payload),
        status=status,
        headers=[('Content-Type', 'application/json')],
    )


def _err(message, status=400, **extra):
    body = {'ok': False, 'error': message}
    body.update(extra)
    return _json_response(body, status=status)


def _ok(**data):
    body = {'ok': True}
    body.update(data)
    return _json_response(body)


def _read_api_key():
    """Pull X-API-KEY header (or form/query fallback for curl convenience)."""
    return (
        request.httprequest.headers.get('X-API-KEY')
        or request.httprequest.form.get('api_key')
        or request.httprequest.args.get('api_key')
        or ''
    ).strip()


def _check_api_key():
    """Returns (key_record_or_None, error_response_or_None).

    key_record is the matched `crm.call.api.key` record when auth went through
    the per-device model. It is None when auth fell back to the legacy shared
    sysparam (uploads in that case have an empty `created_by_api_key_id`).
    """
    presented = _read_api_key()
    if not presented:
        return (None, _err('Missing X-API-KEY header', status=401))

    key_rec = request.env['crm.call.api.key'].sudo()._validate_key(
        presented, remote_ip=request.httprequest.remote_addr,
    )
    if key_rec:
        return (key_rec, None)

    expected = (
        request.env['ir.config_parameter'].sudo().get_param(API_KEY_PARAM) or ''
    ).strip()
    if expected and hmac.compare_digest(presented, expected):
        _logger.info(
            'CRM Call Recorder: auth via legacy sysparam '
            '(consider migrating to crm.call.api.key per-device keys)'
        )
        return (None, None)

    return (None, _err('Invalid X-API-KEY header', status=401))


class CrmCallRecorderController(http.Controller):

    @http.route(
        '/crm_call_recorder/ping', type='http', auth='public', methods=['GET'],
        csrf=False,
    )
    def ping(self, **_):
        _key_rec, err = _check_api_key()
        if err:
            return err
        return _ok(server_time=fields.Datetime.to_string(fields.Datetime.now()))

    @http.route(
        '/crm_call_recorder/upload', type='http', auth='public', methods=['POST'],
        csrf=False,
    )
    def upload(self, **post):
        """Upload one recording.

        Form fields (per PDF Section 5):
            X-API-KEY    header — required
            phone        form   — required
            direction    form   — 'incoming' | 'outgoing' | 'unknown'
            duration     form   — integer seconds
            call_date    form   — 'YYYY-MM-DD HH:MM:SS' (UTC)
            file         file   — the audio file (.m4a / .mp3 / .opus / etc.)

        Returns on success:
            {"ok": true, "id": <int>, "state": "matched"|"unmatched",
             "matched_partner_id": <int|null>, "matched_lead_id": <int|null>}
        """
        key_rec, err = _check_api_key()
        if err:
            return err

        # ---- required fields -----------------------------------------
        phone = (post.get('phone') or '').strip()
        if not phone:
            return _err("Missing 'phone' form field")

        direction = (post.get('direction') or 'unknown').strip().lower()
        if direction not in ('incoming', 'outgoing', 'unknown'):
            direction = 'unknown'

        try:
            duration = int(post.get('duration') or 0)
        except (ValueError, TypeError):
            duration = 0

        call_date = (post.get('call_date') or '').strip() or fields.Datetime.now()
        sim_label = (post.get('sim') or '').strip()

        upload = request.httprequest.files.get('file')
        if not upload:
            return _err("Missing 'file' (audio) part")

        data = upload.read()
        if not data:
            return _err("Uploaded 'file' is empty")
        if len(data) > MAX_UPLOAD_BYTES:
            return _err(
                f"Upload exceeds {MAX_UPLOAD_BYTES // (1024 * 1024)} MB",
                status=413,
            )

        # ---- create + auto-match -------------------------------------
        Recording = request.env['crm.call.recording'].sudo()
        try:
            rec = Recording.create({
                'phone': phone,
                'direction': direction,
                'duration_seconds': duration,
                'call_date': call_date,
                'sim_label': sim_label,
                'created_by_api_key_id': key_rec.id if key_rec else False,
            })
        except Exception as e:
            _logger.exception('CRM Call Recorder: create failed: %s', e)
            return _err(f'Failed to create recording row: {e}', status=500)

        att = request.env['ir.attachment'].sudo().create({
            'name': upload.filename or f'call_{rec.id}.audio',
            'datas': base64.b64encode(data),
            'res_model': 'crm.call.recording',
            'res_id': rec.id,
            'mimetype': upload.mimetype or 'audio/mpeg',
        })
        rec.recording_attachment_id = att.id

        # Mark for transcription IF the master toggle is on; cron will pick it up.
        # Otherwise keep status 'skipped' so the field is meaningful in the UI.
        voice_cfg = request.env['crm.call.voice.config'].sudo().get_config()
        if voice_cfg.transcription_enabled:
            rec.sudo().write({'transcription_status': 'pending'})

        # _match_and_link was already called inside create(); now that the
        # attachment exists, re-post the chatter note so it carries the audio.
        if rec.state == 'matched':
            rec._post_chatter_note(rec.matched_partner_id, rec.matched_lead_id)

        return _ok(
            id=rec.id,
            state=rec.state,
            matched_partner_id=(rec.matched_partner_id.id or None) if rec.matched_partner_id else None,
            matched_lead_id=(rec.matched_lead_id.id or None) if rec.matched_lead_id else None,
        )
