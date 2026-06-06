import logging
import secrets

from werkzeug.security import generate_password_hash, check_password_hash

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class CrmCallApiKey(models.Model):
    """Per-device API key for the Android companion app.

    Modelled after `offline.sync.api.key` so admins recognise the workflow.
    Keys are hashed at rest (werkzeug); plaintext is shown to the admin only
    once via the wizard popup. The 8-char `key_prefix` is indexed so lookups
    stay O(1) over the table size.
    """
    _name = 'crm.call.api.key'
    _description = 'CRM Call Recorder API Key'
    _order = 'create_date desc'

    name = fields.Char(
        string='Description', required=True,
        help='Human label (e.g. "Arun\'s Infinix", "Sales agent 3").',
    )
    key_prefix = fields.Char(
        string='Key Prefix', readonly=True, index=True,
        help='First 8 characters of the key, shown to admins for identification.',
    )
    key_hash = fields.Char(string='Key Hash', readonly=True)
    user_id = fields.Many2one(
        'res.users', string='User', required=True,
        default=lambda self: self.env.uid,
        help='Odoo user this device acts as for audit / future per-user rules.',
    )
    employee_id = fields.Many2one(
        'hr.employee', string='Employee',
        help='HR employee record this device belongs to. Bridges to '
             'whatsapp_employee_tracker so the employee form can show '
             'unified call + WhatsApp activity.',
    )
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        'res.company', string='Company',
        default=lambda self: self.env.company,
    )
    last_used = fields.Datetime(string='Last Used', readonly=True)
    last_used_ip = fields.Char(string='Last Used IP', readonly=True)
    expires_at = fields.Datetime(
        string='Expires At',
        help='Leave empty for no expiration.',
    )
    recording_count = fields.Integer(
        string='Recordings', compute='_compute_recording_count',
    )

    @api.depends('name')
    def _compute_recording_count(self):
        Recording = self.env['crm.call.recording'].sudo()
        for rec in self:
            rec.recording_count = Recording.search_count(
                [('created_by_api_key_id', '=', rec.id)]
            ) if rec.id else 0

    # ─── Auto-bridge to wa.employee.session ────────────────────────────
    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for rec in records:
            rec._ensure_wa_employee_session()
        return records

    def write(self, vals):
        res = super().write(vals)
        if 'employee_id' in vals:
            for rec in self:
                rec._ensure_wa_employee_session()
        return res

    def _ensure_wa_employee_session(self):
        """If employee_id is set and no wa.employee.session exists for that
        employee, auto-create a placeholder whatsapp.session + wa.employee.session
        so the employee appears on the unified Communications Dashboard.

        Idempotent. Skips silently if the WhatsApp models aren't available
        (e.g. whatsapp_employee_tracker temporarily uninstalled) — checked via
        registry presence, not try/except.
        """
        self.ensure_one()
        if not self.employee_id:
            return
        if 'wa.employee.session' not in self.env or 'whatsapp.session' not in self.env:
            return
        WaSession = self.env['wa.employee.session'].sudo()
        try:
            with self.env.cr.savepoint():
                # Row-lock the employee so concurrent api_key writes serialise here.
                self.env.cr.execute(
                    'SELECT id FROM hr_employee WHERE id = %s FOR UPDATE',
                    (self.employee_id.id,),
                )
                existing = WaSession.search(
                    [('employee_id', '=', self.employee_id.id)], limit=1,
                )
                if existing:
                    return
                WhatsApp = self.env['whatsapp.session'].sudo()
                placeholder = WhatsApp.create({
                    'name': f'Call-only: {self.employee_id.name}',
                    'status': 'disconnected',
                    'company_id': self.company_id.id,
                })
                digits = (self.employee_id.work_phone or '').replace(' ', '').replace('+', '').replace('-', '')
                WaSession.create({
                    'employee_id': self.employee_id.id,
                    'session_id': placeholder.id,
                    'phone_number': digits or '0',
                    'monitoring_enabled': False,
                })
        except Exception:
            _logger.exception(
                'Failed to bridge api_key %s -> wa.employee.session; '
                'continuing without auto-session.', self.id,
            )

    def action_generate_key(self):
        """Generate a new API key. Plaintext shown ONCE via the wizard."""
        self.ensure_one()
        raw_key = secrets.token_hex(20)  # 40-char hex
        self.write({
            'key_hash': generate_password_hash(raw_key),
            'key_prefix': raw_key[:8],
        })
        return {
            'type': 'ir.actions.act_window',
            'name': 'Your API Key',
            'res_model': 'crm.call.api.key.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_api_key': raw_key},
        }

    @api.model
    def _validate_key(self, key_string, remote_ip=None):
        """Look up a presented key. Returns the matched record (or False).

        On a successful match, updates `last_used` + `last_used_ip` and returns
        the recordset so the caller can use it for audit (set
        `crm.call.recording.created_by_api_key_id`).
        """
        if not key_string or len(key_string) < 8:
            return False
        prefix = key_string[:8]
        candidates = self.sudo().search([
            ('key_prefix', '=', prefix),
            ('active', '=', True),
        ])
        now = fields.Datetime.now()
        for candidate in candidates:
            if candidate.expires_at and candidate.expires_at < now:
                continue
            if not candidate.key_hash:
                continue
            if check_password_hash(candidate.key_hash, key_string):
                candidate.sudo().write({
                    'last_used': now,
                    'last_used_ip': (remote_ip or '')[:64],
                })
                return candidate
        return False


class CrmCallApiKeyWizard(models.TransientModel):
    _name = 'crm.call.api.key.wizard'
    _description = 'CRM Call Recorder API Key Display Wizard'

    api_key = fields.Char(
        string='API Key', readonly=True,
        help='Copy this key now. It will NOT be shown again.',
    )
