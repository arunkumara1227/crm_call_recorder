# CRM Call Recorder

**Auto-link Android phone-call recordings to Odoo Contacts and Leads.**

Built per the CRM Call Recorder PDF plan, adapted for **Odoo 19** Community
(plan originally targets Odoo 17 — see "Odoo 19 deltas" below for what changed).

| Component | Status |
|---|---|
| Odoo module (server side) | ✅ Built and ready |
| Android companion app | ❌ Phase 2 — uses any phone with built-in call recorder + a folder watcher |

---

## Goal

Build a free, self-hosted system where calls on an Android phone are
**automatically recorded** by the phone's built-in recorder, then
**automatically uploaded** to Odoo and **linked to the matching Contact or
Lead** by phone number. Each call appears in Odoo with an inline audio
player and a chatter note.

## Architecture (per PDF)

| Step | Where | What happens |
|---|---|---|
| 1 | Phone | A call happens; the phone's built-in recorder saves an audio file |
| 2 | Phone (companion app) | App detects the new file + reads the call's number / direction / duration / time from the Call Log |
| 3 | Phone → Odoo | App POSTs audio + metadata to `/crm_call_recorder/upload` with the shared `X-API-KEY` header |
| 4 | Odoo (this module) | Normalizes phone, matches to a Contact and/or Lead, stores audio as `ir.attachment`, posts a chatter note with inline `<audio>` player |
| 5 | Odoo | Sales user opens the matched record and plays the call inline |

### Critical design constraint

**Android 10+ blocks third-party apps from recording calls.** The companion
app therefore does NOT record audio itself — it relies on the phone's
built-in call recorder (Settings → Phone → Call Recording → Auto-record all
calls) and only reads the saved files. This is the only approach that's
robust across Android versions.

## Install

```powershell
# Adjust paths to match your Odoo install
Stop-Service odoo-server-19.0

& "C:\Program Files\Odoo 19.0.20260107\python\python.exe" `
  "C:\Program Files\Odoo 19.0.20260107\server\odoo-bin" `
  -c "C:\Program Files\Odoo 19.0.20260107\server\odoo.conf" `
  --addons-path="C:\Program Files\Odoo 19.0.20260107\server\odoo\addons,c:\odoo19\custom_addons" `
  -d test9 -i crm_call_recorder --stop-after-init

Start-Service odoo-server-19.0
```

Or via Apps UI: search "CRM Call Recorder" → Install.

## Configuration

1. **Change the API key.** Settings → Technical → System Parameters →
   find `crm_call_recorder.api_key` → edit. Default is `my-secret-key-2026`.
   **Change this before any non-local use.**

2. (Optional) Add a Sales Manager to the **Manager** group of the
   "CRM Call Recorder" privilege so they can delete recordings.

## Test it locally (no phone needed)

The included `tools/test_upload.py` simulates the Android app.

```powershell
cd c:\odoo19\custom_addons\crm_call_recorder

# Install requests if you don't have it
python -m pip install requests

# Health check — should print HTTP 200 + server_time
python tools\test_upload.py --ping --key "my-secret-key-2026" --server "http://localhost:8069" --db test9

# Upload a fake call for a number that exists in Contacts (or just any number)
python tools\test_upload.py `
    --server "http://localhost:8069" `
    --db test9 `
    --key "my-secret-key-2026" `
    --phone "+91 98765 43210" `
    --direction incoming `
    --duration 187 `
    --file C:\Windows\Media\Alarm01.wav
```

Expected success response:

```json
{
  "ok": true,
  "id": 1,
  "state": "matched",
  "matched_partner_id": 14,
  "matched_lead_id": null
}
```

State will be `"matched"` if any Contact/Lead has that phone, `"unmatched"`
otherwise (recording is still saved, just not auto-linked).

**Then in the UI:**
- Sales → **Call Recorder → Recordings** → see the new row
- If matched: open the contact/lead → chatter shows the new note with an
  inline audio player

## Upload contract (Android → Odoo)

The companion app must send a multipart POST exactly like this:

| Field | Type | Notes |
|---|---|---|
| `X-API-KEY` | header | Must match the Odoo System Parameter `crm_call_recorder.api_key` |
| `X-Odoo-Database` | header | Required if Odoo is multi-DB. Omit on single-DB installs. |
| `phone` | form field | Required. Any common format — auto-normalized to digits. |
| `direction` | form field | `incoming` / `outgoing` / `unknown` |
| `duration` | form field | Integer seconds |
| `call_date` | form field | `YYYY-MM-DD HH:MM:SS` (UTC) |
| `file` | file part | The audio file — any common mimetype |

Endpoint: `POST {server}/crm_call_recorder/upload`

Success: HTTP 200 + JSON with `ok=true, id, state, matched_partner_id, matched_lead_id`.

Errors: HTTP 401 for auth, 400 for bad input, 413 if file > 50 MB,
500 for server errors. All errors return `{"ok": false, "error": "<message>"}`.

## Odoo 19 deltas from the original PDF plan

The PDF targets Odoo 17 Community. This implementation targets Odoo 19 and
adapts where the API has changed:

| Concern | Odoo 17 (PDF) | Odoo 19 (this build) |
|---|---|---|
| `res.groups` security | `category_id` field on group | `res.groups.privilege` intermediate model (Odoo 19 removed `category_id`) |
| `res.partner.mobile` field | Always present | Removed in Odoo 19 — code uses `getattr(...)` to probe |
| View list element | `<tree>` | `<list>` |
| Auth | `X-API-KEY` (unchanged) | `X-API-KEY` (unchanged) |

## Security & legal

- **Change the API key.** Default is for local testing only.
- **Use HTTPS** (Caddy / Nginx reverse proxy) when the phone connects over
  the internet. Plain HTTP leaks the API key + recordings.
- **Recordings are sensitive PII** — restrict access via the Manager group
  + record rules already configured.
- **Call-recording laws vary by country** (one-party vs two-party consent).
  Confirm legality in each jurisdiction; add a recorded-call disclaimer
  if required.

## Project files

| Path | Purpose |
|---|---|
| `__manifest__.py` | Module declaration |
| `models/call_recording.py` | `crm.call.recording` model + auto-match logic |
| `controllers/main.py` | `/crm_call_recorder/upload` endpoint |
| `views/call_recording_views.xml` | List, form, search, pivot |
| `views/menu.xml` | Sales → Call Recorder → Recordings |
| `security/security.xml` | Groups + record rules |
| `security/ir.model.access.csv` | Model access |
| `data/ir_config_parameter.xml` | Default API key |
| `tools/test_upload.py` | Local test simulator |

## Next: Phase 2 — Android companion app

A Kotlin Android app that:
- Watches the phone's call-recording folder via `FileObserver`
- Reads call metadata from the `CallLog` content provider
- Uploads new files to this Odoo endpoint with the API key
- Retries on network failure via WorkManager

This is **not in this repo yet**. When you start Phase 2, build a fresh
Android Studio project per the PDF Section 3B + Section 5 contract. The
existing `phone_call_recording/android_client/` directory has a related
skeleton (different module name, more complex auth) you can reference.

---

## Migrating from the previous `phone_call_recording` module

If you previously installed the `phone_call_recording` module from this
repo, uninstall it before relying on this one — they don't conflict at
the model level (different table names) but they both add Sales menus
that can confuse users.

```powershell
Stop-Service odoo-server-19.0

& "C:\Program Files\Odoo 19.0.20260107\python\python.exe" `
  "C:\Program Files\Odoo 19.0.20260107\server\odoo-bin" `
  -c "C:\Program Files\Odoo 19.0.20260107\server\odoo.conf" `
  --addons-path="C:\Program Files\Odoo 19.0.20260107\server\odoo\addons,c:\odoo19\custom_addons" `
  -d test9 --uninstall phone_call_recording --stop-after-init

Start-Service odoo-server-19.0
```

The `phone_call_recording/` folder remains on disk for reference.

---

*Generated 2026-05-29 per the CRM Call Recorder PDF plan.*
