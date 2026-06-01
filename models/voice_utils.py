"""Voice transcription utility for CRM Call Recorder.

Pure-Python module (NOT an Odoo model). Exposes `transcribe_audio(audio_bytes)`
which honors the `transcription_provider` selection on `crm.call.voice.config`
and uses the configured per-provider API key + model.

Verbatim port of `whatsapp_neonize/models/voice_utils.py` with one change:
config model name (`crm.call.voice.config` instead of `wa.voice.config`).

Return shape:
    {'text': str, 'language': str, 'duration': float, 'error': str | None}
"""

import base64
import logging
import os
import re
import subprocess
import tempfile

_logger = logging.getLogger(__name__)

# Minimum audio size — below this is too short to be real speech.
# Phone-call recordings encode to ~3-4KB/second at 16kbps; <2KB ≈ silent click.
MIN_AUDIO_BYTES = 2000

# Maximum acceptable mean no_speech_prob from Whisper segments. Above this
# the audio is mostly silence — the transcription is a hallucination.
MAX_NO_SPEECH_PROB = 0.55

# Below this avg_logprob (Whisper's per-segment confidence) the transcription
# is too unsure to trust.
MIN_AVG_LOGPROB = -1.0

# Known Whisper hallucination phrases across languages. Matched
# case-insensitively as substrings. Add new ones as they appear in the wild.
HALLUCINATION_PATTERNS = [
    # English
    r'thanks?\s+for\s+watching',
    r'subscribe\s+to\s+my\s+channel',
    r'don.?t\s+forget\s+to\s+subscribe',
    r'see\s+you\s+next\s+time',
    r'please\s+like\s+and\s+subscribe',
    # Hindi / Punjabi / Urdu — "Thanks for watching" variants
    r'देखने\s*के\s*लिए\s*धन्यवाद',
    r'ਦੇਖਣ\s*ਲਈ\s*ਧੰਨਵਾਦ',
    # Malayalam
    r'കാണുന്നതിന്\s*നന്ദി',
    # Arabic
    r'شكرا\s*للمشاهدة',
    # Japanese / Chinese — common YouTube training noise
    r'ご視聴ありがとうございました',
    r'感谢观看',
]
_HALLUCINATION_RE = re.compile('|'.join(HALLUCINATION_PATTERNS), re.IGNORECASE)


def _looks_hallucinated(text):
    """True if `text` matches any known Whisper hallucination phrase."""
    if not text:
        return False
    return bool(_HALLUCINATION_RE.search(text))


# --------------------------- Public API ---------------------------


def transcribe_audio(audio_bytes, env=None):
    """Transcribe audio bytes (typically AAC/MP4 from Infinix's recorder) to text.

    Honors `crm.call.voice.config.transcription_provider` — uses ONLY the
    selected provider. If that provider's key is empty, returns an
    error explaining which key to set.

    Falls back to env vars (GROQ_API_KEY / OPENAI_API_KEY / GEMINI_API_KEY)
    if no `crm.call.voice.config` record exists.
    """
    result = {'text': '', 'language': 'unknown', 'duration': 0.0, 'error': None}

    if not audio_bytes:
        result['error'] = 'No audio bytes received'
        return result

    if len(audio_bytes) < MIN_AUDIO_BYTES:
        _logger.info(
            "Audio too short (%d bytes < %d) — skipping transcription",
            len(audio_bytes), MIN_AUDIO_BYTES,
        )
        result['error'] = '[Voice — too short to transcribe]'
        return result

    settings = _read_config(env)
    provider = settings['provider']

    handler = {
        'groq': _try_groq,
        'openai': _try_openai,
        'gemini': _try_gemini,
    }.get(provider)

    if not handler:
        result['error'] = f"Unknown transcription_provider '{provider}'"
        return result

    api_key = settings.get(f'{provider}_api_key', '')
    if not api_key:
        result['error'] = (
            f"{provider.capitalize()} API key not set. Open Call Recorder → "
            f"Configuration → Voice Transcription, paste the key, save."
        )
        return result

    model = settings.get(f'{provider}_model', '')
    translate = bool(settings.get('translate_to_english', True))
    ffmpeg_path = settings.get('ffmpeg_path') or 'ffmpeg'

    try:
        r = handler(
            audio_bytes, api_key, model,
            translate=translate, ffmpeg_path=ffmpeg_path,
        )
        if r and r.get('text'):
            text = r['text']
            if _looks_hallucinated(text):
                _logger.info("Voice transcription dropped — hallucination: %r", text[:80])
                result['error'] = '[Voice — silent / hallucinated]'
                return result
            if r.get('no_speech_prob', 0.0) > MAX_NO_SPEECH_PROB:
                _logger.info(
                    "Voice transcription dropped — no_speech_prob %.2f > %.2f: %r",
                    r['no_speech_prob'], MAX_NO_SPEECH_PROB, text[:80],
                )
                result['error'] = '[Voice — mostly silence]'
                return result
            if r.get('avg_logprob', 0.0) < MIN_AVG_LOGPROB:
                _logger.info(
                    "Voice transcription dropped — avg_logprob %.2f < %.2f: %r",
                    r['avg_logprob'], MIN_AVG_LOGPROB, text[:80],
                )
                result['error'] = '[Voice — low-confidence transcription]'
                return result
            _logger.info(
                "Voice transcribed via %s (%s): %r",
                provider, model or 'default', text[:60],
            )
            r['provider'] = provider
            return r
        result['error'] = f"{provider.capitalize()} returned an empty transcription."
        return result
    except Exception as e:
        _logger.warning("Voice transcribe via %s failed: %s", provider, e)
        result['error'] = f"{provider.capitalize()} error: {e}"
        return result


# --------------------------- Config / key resolution ---------------------------


def _read_config(env):
    """Return dict pulled from crm.call.voice.config (record search) with
    env-var fallback when the model isn't in the registry yet (during install)
    or when no record exists.
    """
    settings = {
        'provider': 'groq',
        'translate_to_english': True,
        'gemini_api_key': os.environ.get('GEMINI_API_KEY', '') or '',
        'gemini_model': 'gemini-2.5-flash',
        'groq_api_key': os.environ.get('GROQ_API_KEY', '') or '',
        'groq_model': 'whisper-large-v3',
        'openai_api_key': os.environ.get('OPENAI_API_KEY', '') or '',
        'openai_model': 'whisper-1',
        'ffmpeg_path': '',
    }

    if env is None:
        return settings

    try:
        Config = env['crm.call.voice.config']
    except KeyError:
        _logger.warning("crm.call.voice.config model not found in registry")
        return settings

    cfg = Config.sudo().search([], limit=1)
    if not cfg:
        _logger.info("No crm.call.voice.config record yet — using env-var fallback")
        return settings

    settings['provider'] = cfg.transcription_provider or settings['provider']
    settings['translate_to_english'] = bool(getattr(cfg, 'translate_to_english', True))

    settings['gemini_api_key'] = cfg.gemini_api_key or settings['gemini_api_key']
    if cfg.gemini_model == 'custom' and cfg.gemini_custom_model:
        settings['gemini_model'] = cfg.gemini_custom_model
    elif cfg.gemini_model:
        settings['gemini_model'] = cfg.gemini_model

    settings['groq_api_key'] = cfg.groq_api_key or settings['groq_api_key']
    settings['groq_model'] = cfg.groq_model or settings['groq_model']

    settings['openai_api_key'] = cfg.openai_api_key or settings['openai_api_key']
    settings['openai_model'] = cfg.openai_model or settings['openai_model']

    settings['ffmpeg_path'] = getattr(cfg, 'ffmpeg_path', '') or ''

    return settings


# --------------------------- Whisper-API format gate ---------------------------


def _needs_transcode_for_whisper_api(audio_bytes):
    """True when these bytes WON'T be accepted by Groq/OpenAI Whisper APIs
    without first being transcoded into a recognised container (typically MP3).

    Both APIs reject raw ADTS AAC even when labeled .m4a — they sniff for the
    actual container box structure and fail. AMR isn't accepted at all.
    Anything else with a recognised magic-byte header (MP3, OGG, WAV, FLAC,
    MP4/M4A container) passes through fine.
    """
    if not audio_bytes or len(audio_bytes) < 12:
        return False
    b = audio_bytes
    # MP3
    if b[:3] == b'ID3':
        return False
    if b[0] == 0xFF and (b[1] & 0xE0) == 0xE0 and (b[1] & 0x06) != 0x00:
        return False
    # OGG
    if b[:4] == b'OggS':
        return False
    # WAV
    if b[:4] == b'RIFF' and b[8:12] == b'WAVE':
        return False
    # FLAC
    if b[:4] == b'fLaC':
        return False
    # MP4 / M4A container ("ftyp" box near the start)
    if b'ftyp' in b[:16]:
        return False
    # AMR — Whisper APIs don't take this
    if b[:6] == b'#!AMR\n':
        return True
    # ADTS AAC sync (12-bit all-ones)
    if b[0] == 0xFF and (b[1] & 0xF0) == 0xF0:
        return True
    # Anything else — be conservative, transcode
    return True


def _transcode_to_mp3(audio_bytes, ffmpeg_cmd='ffmpeg'):
    """Pipe `audio_bytes` through ffmpeg and return MP3 bytes.

    Returns None on any failure (ffmpeg missing, exit non-zero, timeout) and
    logs the reason. Caller is expected to raise a friendly RuntimeError if a
    None return blocks the transcription.
    """
    cmd = [
        ffmpeg_cmd or 'ffmpeg',
        '-hide_banner', '-loglevel', 'error',
        '-i', 'pipe:0',
        '-vn',                         # ignore any video tracks
        '-codec:a', 'libmp3lame',
        '-b:a', '32k',                 # 32 kbps mono — fine for voice
        '-ar', '16000',                # Whisper-friendly sample rate
        '-ac', '1',
        '-f', 'mp3',
        'pipe:1',
    ]
    try:
        proc = subprocess.run(
            cmd, input=audio_bytes, capture_output=True, timeout=60,
        )
    except FileNotFoundError:
        _logger.warning(
            "ffmpeg not found (cmd=%r). Install ffmpeg or set ffmpeg_path "
            "in Configuration → Voice Transcription.", ffmpeg_cmd,
        )
        return None
    except subprocess.TimeoutExpired:
        _logger.warning("ffmpeg transcode timed out after 60s")
        return None
    except Exception as e:
        _logger.exception("ffmpeg transcode raised %s", e)
        return None

    if proc.returncode != 0 or not proc.stdout:
        _logger.warning(
            "ffmpeg transcode failed (rc=%d): %s",
            proc.returncode,
            proc.stderr[:300].decode('utf-8', 'replace') if proc.stderr else '(no stderr)',
        )
        return None

    _logger.info(
        "ffmpeg transcoded %d input bytes → %d MP3 bytes",
        len(audio_bytes), len(proc.stdout),
    )
    return proc.stdout


# --------------------------- Format detection ---------------------------


def _detect_audio_format(audio_bytes):
    """Sniff magic bytes → return (filename, mime).

    Critical for raw AAC ADTS (no container) which phone-call recorders
    produce: it must be labeled as .m4a/audio/mp4 because Groq/OpenAI Whisper
    don't accept .aac directly, but their ffmpeg-backed decoders parse ADTS
    AAC bytes happily when the extension says .m4a.
    """
    if not audio_bytes or len(audio_bytes) < 12:
        return ('audio.m4a', 'audio/mp4')
    b = audio_bytes
    if b[:3] == b'ID3' or (b[0] == 0xFF and (b[1] & 0xE0) == 0xE0 and (b[1] & 0x06) != 0x00):
        return ('audio.mp3', 'audio/mpeg')
    if b[:4] == b'OggS':
        return ('audio.ogg', 'audio/ogg')
    if b[:4] == b'RIFF' and b[8:12] == b'WAVE':
        return ('audio.wav', 'audio/wav')
    if b[:4] == b'fLaC':
        return ('audio.flac', 'audio/flac')
    # MP4 / M4A "ftyp" box in the first 16 bytes
    if b'ftyp' in b[:16]:
        return ('audio.m4a', 'audio/mp4')
    # AMR
    if b[:6] == b'#!AMR\n':
        return ('audio.amr', 'audio/amr')
    # AAC ADTS sync (0xFFF...) — fallback we hit most often on Infinix etc.
    if b[0] == 0xFF and (b[1] & 0xF0) == 0xF0:
        return ('audio.m4a', 'audio/mp4')
    # Unknown — gamble on .m4a since the audio APIs accept it and most
    # AAC-family bytes decode regardless of label.
    return ('audio.m4a', 'audio/mp4')


# --------------------------- Backend: Groq ---------------------------


def _try_groq(audio_bytes, api_key, model, translate=False, ffmpeg_path='ffmpeg'):
    import requests
    model = model or 'whisper-large-v3'
    # Groq's Whisper API rejects raw ADTS AAC / AMR / unknown formats — transcode first.
    if _needs_transcode_for_whisper_api(audio_bytes):
        mp3 = _transcode_to_mp3(audio_bytes, ffmpeg_cmd=ffmpeg_path)
        if not mp3:
            raise RuntimeError(
                "ffmpeg not found or failed — required to transcode raw AAC for "
                "Groq. Install ffmpeg on the server (or set ffmpeg path in "
                "Configuration), restart Odoo, or switch provider to Gemini "
                "(which handles AAC natively)."
            )
        audio_bytes = mp3
    # /translations forces English output. /transcriptions keeps source language.
    endpoint = 'translations' if translate else 'transcriptions'
    filename, mime = _detect_audio_format(audio_bytes)
    path = _write_temp_audio(audio_bytes, suffix='.' + filename.rsplit('.', 1)[1])
    try:
        with open(path, 'rb') as af:
            resp = requests.post(
                f'https://api.groq.com/openai/v1/audio/{endpoint}',
                headers={'Authorization': f'Bearer {api_key}'},
                files={'file': (filename, af, mime)},
                data={'model': model, 'response_format': 'verbose_json'},
                timeout=120,
            )
        if resp.status_code != 200:
            raise RuntimeError(f'HTTP {resp.status_code}: {resp.text[:200]}')
        data = resp.json()
        segs = data.get('segments') or []
        return {
            'text': (data.get('text') or '').strip(),
            'language': data.get('language') or 'unknown',
            'duration': float(data.get('duration') or 0.0),
            'no_speech_prob': _avg(s.get('no_speech_prob') for s in segs),
            'avg_logprob': _avg(s.get('avg_logprob') for s in segs),
            'error': None,
        }
    finally:
        _unlink(path)


# --------------------------- Backend: OpenAI ---------------------------


def _try_openai(audio_bytes, api_key, model, translate=False, ffmpeg_path='ffmpeg'):
    import requests
    model = model or 'whisper-1'
    # OpenAI's Whisper API has the same container restrictions as Groq.
    if _needs_transcode_for_whisper_api(audio_bytes):
        mp3 = _transcode_to_mp3(audio_bytes, ffmpeg_cmd=ffmpeg_path)
        if not mp3:
            raise RuntimeError(
                "ffmpeg not found or failed — required to transcode raw AAC for "
                "OpenAI. Install ffmpeg on the server (or set ffmpeg path in "
                "Configuration), restart Odoo, or switch provider to Gemini "
                "(which handles AAC natively)."
            )
        audio_bytes = mp3
    use_translate = translate and model == 'whisper-1'
    endpoint = 'translations' if use_translate else 'transcriptions'
    filename, mime = _detect_audio_format(audio_bytes)
    path = _write_temp_audio(audio_bytes, suffix='.' + filename.rsplit('.', 1)[1])
    try:
        with open(path, 'rb') as af:
            data_form = {'model': model}
            if model == 'whisper-1':
                data_form['response_format'] = 'verbose_json'
            resp = requests.post(
                f'https://api.openai.com/v1/audio/{endpoint}',
                headers={'Authorization': f'Bearer {api_key}'},
                files={'file': (filename, af, mime)},
                data=data_form,
                timeout=120,
            )
        if resp.status_code != 200:
            raise RuntimeError(f'HTTP {resp.status_code}: {resp.text[:200]}')
        data = resp.json()
        segs = data.get('segments') or []
        return {
            'text': (data.get('text') or '').strip(),
            'language': data.get('language') or 'unknown',
            'duration': float(data.get('duration') or 0.0),
            'no_speech_prob': _avg(s.get('no_speech_prob') for s in segs),
            'avg_logprob': _avg(s.get('avg_logprob') for s in segs),
            'error': None,
        }
    finally:
        _unlink(path)


# --------------------------- Backend: Gemini ---------------------------


def _try_gemini(audio_bytes, api_key, model, translate=False, ffmpeg_path='ffmpeg'):
    import requests
    # ffmpeg_path is accepted for signature parity with the other backends but
    # not used — Gemini is multimodal and decodes AAC bytes natively.
    _ = ffmpeg_path
    model = model or 'gemini-2.5-flash'
    b64 = base64.b64encode(audio_bytes).decode('ascii')
    if translate:
        prompt_text = (
            'Transcribe the following audio and translate it to English. '
            'Respond with the English text only — no commentary, no quotes, '
            'no labels like "Translation:". If the audio is silent or '
            'unintelligible, respond with an empty string.'
        )
    else:
        prompt_text = (
            'Transcribe the following audio verbatim. '
            'Respond with the transcription only, no commentary.'
        )
    _, mime = _detect_audio_format(audio_bytes)
    payload = {
        'contents': [{
            'parts': [
                {'text': prompt_text},
                {'inline_data': {'mime_type': mime, 'data': b64}},
            ]
        }]
    }
    url = (
        f'https://generativelanguage.googleapis.com/v1beta/models/'
        f'{model}:generateContent?key={api_key}'
    )
    resp = requests.post(url, json=payload, timeout=120)
    if resp.status_code != 200:
        raise RuntimeError(f'HTTP {resp.status_code}: {resp.text[:200]}')
    data = resp.json()
    text = ''
    try:
        text = data['candidates'][0]['content']['parts'][0]['text'].strip()
    except (KeyError, IndexError, TypeError):
        pass
    return {
        'text': text,
        'language': 'auto',
        'duration': 0.0,
        'error': None,
    }


# --------------------------- Helpers ---------------------------


def _avg(values):
    nums = [v for v in values if v is not None]
    if not nums:
        return 0.0
    return sum(nums) / len(nums)


def _write_temp_audio(audio_bytes, suffix='.ogg'):
    f = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    try:
        f.write(audio_bytes)
    finally:
        f.close()
    return f.name


def _unlink(path):
    try:
        os.unlink(path)
    except OSError:
        pass
