"""Simulate the Android companion app uploading a recording.

Per PDF Section 6 — local test commands.

Examples:

    # Health check
    python tools\\test_upload.py --ping

    # Upload a fake call (defaults to a short generated WAV if no --file)
    python tools\\test_upload.py --key "my-secret-key-2026" --phone "+91 98765 43210" --direction incoming

    # Upload with a real audio file
    python tools\\test_upload.py --key "my-secret-key-2026" --phone "+91 98765 43210" `
        --direction outgoing --duration 187 --file C:\\Windows\\Media\\Alarm01.wav

Exit status 0 on success (matched or unmatched), non-zero on auth/transport error.
"""

import argparse
import datetime
import io
import json
import os
import struct
import sys
import wave

try:
    import requests
except ImportError:
    print("ERROR: 'requests' missing.  pip install requests", file=sys.stderr)
    sys.exit(2)


def make_silent_wav(duration_seconds: int = 3) -> bytes:
    """Generate a small valid WAV file in memory so we don't need a real audio file."""
    buf = io.BytesIO()
    with wave.open(buf, 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(8000)
        silence = struct.pack('<h', 0) * (8000 * duration_seconds)
        w.writeframes(silence)
    return buf.getvalue()


def cmd_ping(server: str, key: str, database: str | None = None) -> int:
    url = server.rstrip('/') + '/crm_call_recorder/ping'
    headers = {'X-API-KEY': key} if key else {}
    if database:
        headers['X-Odoo-Database'] = database
    try:
        r = requests.get(url, headers=headers, timeout=10)
    except requests.RequestException as e:
        print(f'ERROR: {e}', file=sys.stderr)
        return 2
    print(f'HTTP {r.status_code}: {r.text}')
    return 0 if r.status_code == 200 else 1


def cmd_upload(server: str, key: str, phone: str, direction: str,
               duration: int, call_date: str, file_path: str | None,
               database: str | None) -> int:
    url = server.rstrip('/') + '/crm_call_recorder/upload'
    headers = {'X-API-KEY': key}
    if database:
        headers['X-Odoo-Database'] = database

    if file_path:
        if not os.path.isfile(file_path):
            print(f'ERROR: file not found: {file_path}', file=sys.stderr)
            return 2
        with open(file_path, 'rb') as fp:
            audio_bytes = fp.read()
        filename = os.path.basename(file_path)
        mime = 'audio/wav' if filename.lower().endswith('.wav') else 'audio/mpeg'
    else:
        audio_bytes = make_silent_wav(max(1, duration or 3))
        filename = 'silence.wav'
        mime = 'audio/wav'

    data = {
        'phone': phone,
        'direction': direction,
        'duration': str(duration),
        'call_date': call_date,
    }
    files = {'file': (filename, audio_bytes, mime)}

    try:
        r = requests.post(url, headers=headers, data=data, files=files, timeout=60)
    except requests.RequestException as e:
        print(f'ERROR: {e}', file=sys.stderr)
        return 2

    try:
        payload = r.json()
    except ValueError:
        payload = {'raw': r.text}
    print(f'HTTP {r.status_code}: {json.dumps(payload, indent=2)}')
    return 0 if (r.status_code == 200 and payload.get('ok')) else 1


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    p.add_argument('--server', default='http://localhost:8069',
                   help='Odoo base URL (default: http://localhost:8069)')
    p.add_argument('--db', default=None,
                   help='Odoo database name (sent as X-Odoo-Database header; '
                        'required if Odoo is multi-DB)')
    p.add_argument('--key', default=os.environ.get('CRM_CALL_RECORDER_API_KEY', ''),
                   help='Shared API key (or set CRM_CALL_RECORDER_API_KEY env var). '
                        'Required for everything except --ping with empty key.')
    p.add_argument('--ping', action='store_true', help='Just hit /ping and exit.')
    p.add_argument('--phone', help='Phone number (E.164 or any common format).')
    p.add_argument('--direction', default='incoming',
                   choices=['incoming', 'outgoing', 'unknown'])
    p.add_argument('--duration', type=int, default=10, help='Duration in seconds.')
    p.add_argument('--call-date', dest='call_date',
                   default=datetime.datetime.now(datetime.UTC).strftime('%Y-%m-%d %H:%M:%S'),
                   help='UTC call timestamp (default: now)')
    p.add_argument('--file', default=None,
                   help='Audio file to upload. If omitted, a silent WAV is generated.')
    args = p.parse_args()

    if args.ping:
        return cmd_ping(args.server, args.key, args.db)

    if not args.phone:
        p.error('--phone is required for upload')
    if not args.key:
        p.error('--key is required (or set CRM_CALL_RECORDER_API_KEY)')

    return cmd_upload(
        server=args.server,
        key=args.key,
        phone=args.phone,
        direction=args.direction,
        duration=args.duration,
        call_date=args.call_date,
        file_path=args.file,
        database=args.db,
    )


if __name__ == '__main__':
    sys.exit(main())
