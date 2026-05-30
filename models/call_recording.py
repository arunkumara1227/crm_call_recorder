import re
import logging
from markupsafe import Markup

from odoo import api, fields, models, _

_logger = logging.getLogger(__name__)


class CallRecording(models.Model):
    """One row per uploaded phone-call recording.

    After create, `_match_and_link()` resolves the phone number to a
    Contact and/or Lead, posts a chatter note with an inline audio player
    on the matched record, and sets `state` accordingly.
    """
    _name = 'crm.call.recording'
    _description = 'CRM Call Recording'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'call_date desc, id desc'
    _rec_name = 'display_label'

    display_label = fields.Char(compute='_compute_display_label', store=True)

    phone = fields.Char(required=True, index=True, tracking=True,
                        help='As uploaded by the client. _phone_digits stores the normalized form.')
    phone_digits = fields.Char(compute='_compute_phone_digits', store=True, index=True)

    direction = fields.Selection([
        ('incoming', 'Incoming'),
        ('outgoing', 'Outgoing'),
        ('unknown', 'Unknown'),
    ], default='unknown', required=True, tracking=True)

    duration_seconds = fields.Integer('Duration (s)', default=0)
    duration_display = fields.Char(compute='_compute_duration_display')

    call_date = fields.Datetime(default=fields.Datetime.now, tracking=True,
                                help='UTC timestamp of when the call happened.')

    recording_attachment_id = fields.Many2one(
        'ir.attachment', string='Recording', ondelete='set null', copy=False,
    )
    recording_url = fields.Char(compute='_compute_recording_url')
    has_recording = fields.Boolean(compute='_compute_recording_url',
                                   search='_search_has_recording')
    recording_size_kb = fields.Integer(compute='_compute_recording_url')

    state = fields.Selection([
        ('pending', 'Pending'),
        ('matched', 'Matched'),
        ('unmatched', 'Unmatched'),
        ('failed', 'Failed'),
    ], default='pending', required=True, tracking=True)

    matched_partner_id = fields.Many2one(
        'res.partner', string='Matched Contact', tracking=True,
    )
    matched_lead_id = fields.Many2one(
        'crm.lead', string='Matched Lead', tracking=True,
    )

    note = fields.Text(help='Free-text audit notes.')

    sim_label = fields.Char(
        string='SIM',
        help='Which SIM the device was on for this call. Filled by the '
             'Android app from SubscriptionInfo (e.g. "SIM 1 — Jio"). '
             'Empty for uploads from clients that don\'t send this field.',
    )

    created_by_api_key_id = fields.Many2one(
        'crm.call.api.key', string='Uploaded via', readonly=True,
        ondelete='set null',
        help='Per-device API key that authenticated this upload. Empty for '
             'uploads authenticated via the legacy shared sysparam key.',
    )

    company_id = fields.Many2one(
        'res.company', default=lambda self: self.env.company, index=True,
    )

    # ──────────────────────────────────────────────────────────────────
    # Computed fields
    # ──────────────────────────────────────────────────────────────────

    @api.depends('phone', 'matched_partner_id.name', 'matched_lead_id.name', 'call_date')
    def _compute_display_label(self):
        for rec in self:
            who = (
                (rec.matched_partner_id.name if rec.matched_partner_id else None)
                or (rec.matched_lead_id.name if rec.matched_lead_id else None)
                or rec.phone or '?'
            )
            when = fields.Datetime.to_string(rec.call_date) if rec.call_date else ''
            rec.display_label = f"{who} — {when}" if when else who

    @api.depends('phone')
    def _compute_phone_digits(self):
        for rec in self:
            rec.phone_digits = self._normalize_phone(rec.phone)

    @api.depends('duration_seconds')
    def _compute_duration_display(self):
        for rec in self:
            total = rec.duration_seconds or 0
            m, s = divmod(total, 60)
            rec.duration_display = f"{m}m {s:02d}s" if total else '—'

    @api.depends('recording_attachment_id')
    def _compute_recording_url(self):
        for rec in self:
            att = rec.recording_attachment_id
            if att:
                rec.recording_url = f'/web/content/{att.id}?download=true'
                rec.has_recording = True
                rec.recording_size_kb = (att.file_size or 0) // 1024
            else:
                rec.recording_url = False
                rec.has_recording = False
                rec.recording_size_kb = 0

    def _search_has_recording(self, operator, value):
        if operator not in ('=', '!='):
            return []
        true_match = (operator == '=' and value) or (operator == '!=' and not value)
        op = '!=' if true_match else '='
        return [('recording_attachment_id', op, False)]

    # ──────────────────────────────────────────────────────────────────
    # Phone normalization + matching
    # ──────────────────────────────────────────────────────────────────

    @api.model
    def _normalize_phone(self, raw):
        """Strip everything but digits, keep last 15.
        E.g. '+91 98765 43210' → '919876543210'."""
        if not raw:
            return ''
        digits = re.sub(r'[^\d]', '', raw)
        return digits[-15:] if len(digits) > 15 else digits

    @api.model
    def _match_partner_by_phone(self, phone_digits):
        """Find a res.partner whose phone ends in the same last-10 digits.
        Odoo 19 dropped res.partner.mobile, so we probe for it defensively."""
        Partner = self.env['res.partner']
        if not phone_digits:
            return Partner
        last10 = phone_digits[-10:] if len(phone_digits) >= 10 else phone_digits
        if len(last10) < 7:
            return Partner
        domain = [('phone', 'ilike', last10)]
        has_mobile = 'mobile' in Partner._fields
        if has_mobile:
            domain = ['|', ('phone', 'ilike', last10), ('mobile', 'ilike', last10)]
        for p in Partner.sudo().search(domain, limit=5):
            for field_name in (('phone', 'mobile') if has_mobile else ('phone',)):
                val = getattr(p, field_name, None)
                if val and self._normalize_phone(val).endswith(last10):
                    return p
        return Partner

    @api.model
    def _match_lead_by_phone(self, phone_digits):
        """Find an open crm.lead matching the same last-10 digits.
        Odoo 19 dropped crm.lead.mobile; we probe defensively. Uses
        phone_sanitized when present — it's the canonical normalized form."""
        Lead = self.env['crm.lead']
        if not phone_digits:
            return Lead
        last10 = phone_digits[-10:] if len(phone_digits) >= 10 else phone_digits
        if len(last10) < 7:
            return Lead
        probe_fields = [f for f in ('phone', 'mobile', 'phone_sanitized')
                        if f in Lead._fields]
        if not probe_fields:
            return Lead
        domain = [('active', '=', True)]
        or_clauses = []
        for f in probe_fields:
            or_clauses.append((f, 'ilike', last10))
        if len(or_clauses) > 1:
            domain += ['|'] * (len(or_clauses) - 1)
        domain += or_clauses
        for lead in Lead.sudo().search(domain, limit=5):
            for f in probe_fields:
                val = getattr(lead, f, None)
                if val and self._normalize_phone(val).endswith(last10):
                    return lead
        return Lead

    # ──────────────────────────────────────────────────────────────────
    # Post-create matching + chatter note
    # ──────────────────────────────────────────────────────────────────

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for rec in records:
            try:
                rec._match_and_link()
            except Exception as e:
                _logger.exception("CRM Call Recorder: match failed for %s: %s", rec.id, e)
                rec.state = 'failed'
                rec.note = (rec.note or '') + f"\nMatch error: {e}"
        return records

    def _match_and_link(self):
        """Resolve phone → partner / lead, set state, post chatter note."""
        self.ensure_one()
        partner = self._match_partner_by_phone(self.phone_digits)
        lead = self._match_lead_by_phone(self.phone_digits)

        self.matched_partner_id = partner.id if partner else False
        self.matched_lead_id = lead.id if lead else False

        if partner or lead:
            self.state = 'matched'
            self._post_chatter_note(partner, lead)
        else:
            self.state = 'unmatched'

    def _post_chatter_note(self, partner, lead):
        """Post an HTML5 audio-player note on the matched record(s)."""
        self.ensure_one()
        if not self.recording_attachment_id:
            return

        url = self.recording_url
        dir_label = dict(self._fields['direction'].selection).get(self.direction, 'Call')
        when = fields.Datetime.to_string(self.call_date) if self.call_date else ''
        duration = self.duration_display
        body = Markup(
            '<p><strong>📞 %s call</strong> %s · %s</p>'
            '<audio controls preload="metadata" style="width:100%%;">'
            '  <source src="%s"/>Your browser doesn\'t support inline audio.'
            '</audio>'
            '<p style="font-size:11px;color:#888;margin-top:4px;">'
            'Recorded by CRM Call Recorder. Phone: %s'
            '</p>'
        ) % (dir_label, when, duration, url, self.phone)

        # Attach the audio so the note carries the file inline as well.
        att_ids = [self.recording_attachment_id.id] if self.recording_attachment_id else []
        for target in (partner, lead):
            if target:
                target.sudo().message_post(
                    body=body,
                    attachment_ids=att_ids,
                    subject=_('Call recording: %s') % (when or self.phone),
                )

    # ──────────────────────────────────────────────────────────────────
    # Manual relink action — for unmatched recordings
    # ──────────────────────────────────────────────────────────────────

    def action_relink(self):
        """Manager picks a partner / lead via the form fields, hits this
        button to re-run matching and re-post the chatter note."""
        for rec in self:
            if rec.matched_partner_id or rec.matched_lead_id:
                rec.state = 'matched'
                rec._post_chatter_note(rec.matched_partner_id, rec.matched_lead_id)
            else:
                rec.state = 'unmatched'
        return True
