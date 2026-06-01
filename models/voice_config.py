"""Voice transcription config — singleton model.

Mirrors `wa.voice.config` from whatsapp_employee_tracker but drops the
subprocess/JSON-file dance (we read straight from the DB inside the cron
worker). Adds a master `transcription_enabled` toggle on top.
"""

import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class CrmCallVoiceConfig(models.Model):
    _name = 'crm.call.voice.config'
    _description = 'CRM Call Recorder — Voice Transcription Settings'
    _rec_name = 'transcription_provider'

    transcription_enabled = fields.Boolean(
        'Transcription Enabled', default=False,
        help='Master toggle. When OFF, new uploads are saved with '
             'status="skipped" and the cron does nothing. Turn ON after '
             'pasting at least one provider\'s API key.',
    )

    transcription_provider = fields.Selection([
        ('gemini', 'Google Gemini'),
        ('groq', 'Groq (Free — 2hr/day)'),
        ('openai', 'OpenAI Whisper'),
    ], string='Transcription Provider', default='groq', required=True)

    translate_to_english = fields.Boolean(
        'Translate to English', default=True,
        help='ON: calls in any language are transcribed AS English. '
             'The detected source language is still recorded for audit. '
             'OFF: keep the original-language transcript only.',
    )

    # Gemini
    gemini_api_key = fields.Char('Gemini API Key')
    gemini_model = fields.Selection([
        ('gemini-2.5-flash', 'Gemini 2.5 Flash (recommended)'),
        ('gemini-2.5-flash-lite', 'Gemini 2.5 Flash Lite'),
        ('gemini-2.5-pro', 'Gemini 2.5 Pro'),
        ('gemini-2.0-flash', 'Gemini 2.0 Flash'),
        ('gemini-2.0-flash-lite', 'Gemini 2.0 Flash Lite'),
        ('gemini-1.5-flash', 'Gemini 1.5 Flash'),
        ('gemini-1.5-flash-8b', 'Gemini 1.5 Flash 8B (fastest)'),
        ('gemini-1.5-pro', 'Gemini 1.5 Pro'),
        ('custom', 'Custom (enter below)'),
    ], string='Gemini Model', default='gemini-2.5-flash')
    gemini_custom_model = fields.Char(
        'Custom Model Name',
        help='Used when "Custom" is selected. Exact model id, e.g. gemini-3-flash-preview.',
    )

    # Groq
    groq_api_key = fields.Char('Groq API Key')
    groq_model = fields.Char(
        'Groq Model', default='whisper-large-v3',
        help='whisper-large-v3 (most accurate) or whisper-large-v3-turbo (faster).',
    )

    # OpenAI
    openai_api_key = fields.Char('OpenAI API Key')
    openai_model = fields.Selection([
        ('whisper-1', 'Whisper-1 (stable)'),
        ('gpt-4o-transcribe', 'GPT-4o Transcribe (best accuracy)'),
        ('gpt-4o-mini-transcribe', 'GPT-4o Mini Transcribe (fast)'),
    ], string='OpenAI Model', default='whisper-1')

    ffmpeg_path = fields.Char(
        'ffmpeg path (optional)',
        help='Leave empty to look up `ffmpeg` on the system PATH. Set an '
             'absolute path (e.g. C:\\ffmpeg\\bin\\ffmpeg.exe) when ffmpeg is '
             'installed but Odoo can\'t find it on PATH. Only used to '
             'transcode raw AAC for the Groq + OpenAI Whisper backends; '
             'Gemini handles AAC natively without ffmpeg.',
    )

    status_message = fields.Char('Status', readonly=True)

    @api.model
    def get_config(self):
        """Get or create the single config record (singleton pattern)."""
        config = self.sudo().search([], limit=1)
        if not config:
            config = self.sudo().create({})
        return config

    def action_save_config(self):
        """No-op save trigger — Odoo persists field changes when the user clicks
        Save in the normal way. This button only exists so the form footer has
        a primary action that shows a clear "Saved" notification.
        """
        self.ensure_one()
        self.status_message = (
            f'Saved. Provider: {self.transcription_provider}. '
            f'Enabled: {self.transcription_enabled}.'
        )
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Voice config saved',
                'message': self.status_message,
                'type': 'success',
                'sticky': False,
            },
        }

    def action_test_connection(self):
        """Send a 1-second silent WAV through the configured provider to verify
        the API key + reachability. Updates `status_message` with the outcome.
        """
        self.ensure_one()
        from . import voice_utils
        # Tiny silent WAV header + 1s of zeros at 8kHz/mono/16-bit.
        # 8000 samples * 2 bytes = 16000 bytes of PCM = comfortably above
        # voice_utils.MIN_AUDIO_BYTES (2000) so it actually reaches the API.
        import io
        import wave
        buf = io.BytesIO()
        with wave.open(buf, 'wb') as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(8000)
            w.writeframes(b'\x00\x00' * 8000)
        sample = buf.getvalue()

        result = voice_utils.transcribe_audio(sample, env=self.env)
        ok = not result.get('error') or result.get('text')
        if result.get('error'):
            # Silence test is EXPECTED to be flagged as "too short" or
            # "silent / hallucinated" — that means the API responded.
            err = result['error']
            if any(s in err for s in ('too short', 'silent', 'mostly silence', 'low-confidence')):
                ok = True
                msg = (
                    f'✓ Provider {self.transcription_provider} reachable '
                    f'(silence test correctly flagged).'
                )
            else:
                ok = False
                msg = f'✗ {err}'
        else:
            msg = (
                f'✓ Provider {self.transcription_provider} reachable. '
                f'(Sample returned: {result.get("text", "")[:60]})'
            )

        self.status_message = msg
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Connection test',
                'message': msg[:300],
                'type': 'success' if ok else 'danger',
                'sticky': True,
            },
        }
