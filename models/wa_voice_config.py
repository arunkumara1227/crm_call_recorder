import json
import logging
import os

from odoo import models, fields, api

_logger = logging.getLogger(__name__)

_CONFIG_FILE = r'D:\odoo-packages\wa_config.json'


class WaVoiceConfig(models.Model):
    _name = 'wa.voice.config'
    _description = 'Voice Transcription Settings'
    _rec_name = 'transcription_provider'

    transcription_provider = fields.Selection([
        ('gemini', 'Google Gemini'),
        ('groq', 'Groq (Free - 2hr/day)'),
        ('openai', 'OpenAI Whisper'),
    ], string='Transcription Provider', default='gemini', required=True)

    translate_to_english = fields.Boolean(
        'Translate to English',
        default=True,
        help='If enabled, voice notes spoken in any language are auto-translated '
             'to English text. The detected source language is still saved on '
             'the message record for audit. Turn OFF to keep the original-language transcript.',
    )

    # Gemini settings
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
        help='Used when "Custom" is selected above. Enter exact model name e.g. gemini-2.5-flash',
    )

    # Groq settings
    groq_api_key = fields.Char('Groq API Key')
    groq_model = fields.Char(
        'Groq Model',
        default='whisper-large-v3',
        help='whisper-large-v3 (most accurate) or whisper-large-v3-turbo (faster)',
    )

    # OpenAI settings
    openai_api_key = fields.Char('OpenAI API Key')
    openai_model = fields.Selection([
        ('whisper-1', 'Whisper-1 (stable)'),
        ('gpt-4o-transcribe', 'GPT-4o Transcribe (best accuracy)'),
        ('gpt-4o-mini-transcribe', 'GPT-4o Mini Transcribe (fast)'),
    ], string='OpenAI Model', default='whisper-1')

    status_message = fields.Char('Status', readonly=True)

    @api.model
    def get_config(self):
        """Get or create the single config record."""
        config = self.search([], limit=1)
        if not config:
            # Load existing keys from wa_config.json if present
            gemini_key = ''
            try:
                with open(_CONFIG_FILE, 'r') as f:
                    data = json.load(f)
                gemini_key = data.get('gemini_api_key', '')
            except Exception:
                pass
            groq_key = data.get('groq_api_key', '') if 'data' in dir() else ''
            try:
                with open(_CONFIG_FILE, 'r') as f:
                    data2 = json.load(f)
                groq_key = data2.get('groq_api_key', '')
                provider = data2.get('transcription_provider', 'gemini')
                gemini_model = data2.get('gemini_model', 'gemini-2.5-flash')
            except Exception:
                provider = 'gemini'
                gemini_model = 'gemini-2.5-flash'
            openai_key = data2.get('openai_api_key', '') if 'data2' in dir() else ''
            openai_model = data2.get('openai_model', 'whisper-1') if 'data2' in dir() else 'whisper-1'
            translate_to_english = data2.get('translate_to_english', True) if 'data2' in dir() else True
            config = self.create({
                'transcription_provider': provider,
                'gemini_api_key': gemini_key,
                'gemini_model': gemini_model,
                'groq_api_key': groq_key,
                'openai_api_key': openai_key,
                'openai_model': openai_model,
                'translate_to_english': translate_to_english,
            })
        return config

    def action_save_config(self):
        """Save settings to wa_config.json so the worker subprocess can read them."""
        self.ensure_one()
        data = {
            'transcription_provider': self.transcription_provider or 'gemini',
            'gemini_api_key': self.gemini_api_key or '',
            'gemini_model': self.gemini_custom_model if self.gemini_model == 'custom' else (self.gemini_model or 'gemini-2.5-flash'),
            'groq_api_key': self.groq_api_key or '',
            'groq_model': self.groq_model or 'whisper-large-v3',
            'openai_api_key': self.openai_api_key or '',
            'openai_model': self.openai_model or 'whisper-1',
            'translate_to_english': bool(self.translate_to_english),
        }
        try:
            os.makedirs(os.path.dirname(_CONFIG_FILE), exist_ok=True)
            with open(_CONFIG_FILE, 'w') as f:
                json.dump(data, f, indent=4)
            self.status_message = f'Saved! Provider: {self.transcription_provider}'
            _logger.info("Voice config saved: provider=%s", self.transcription_provider)
        except Exception as e:
            self.status_message = f'Save failed: {e}'
            _logger.error("Failed to save voice config: %s", e)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Voice Config Saved',
                'message': self.status_message,
                'type': 'success' if 'Saved' in (self.status_message or '') else 'danger',
            },
        }

    def action_test_connection(self):
        """Test the configured provider quickly."""
        self.ensure_one()
        import subprocess, sys
        _PYTHON = r'C:\Program Files\Odoo 19.0.20251017\python\python.exe'

        test_script = r'D:\odoo-packages\test_transcription_provider.py'
        try:
            result = subprocess.run(
                [_PYTHON, test_script],
                capture_output=True, timeout=30,
            )
            out = result.stdout.decode(errors='replace').strip()
            err = result.stderr.decode(errors='replace').strip()
            msg = out or err or 'No output'
        except Exception as e:
            msg = str(e)

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Connection Test',
                'message': msg[:300],
                'type': 'success' if 'OK' in msg else 'warning',
                'sticky': True,
            },
        }
