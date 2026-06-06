# import logging
# from odoo import models, fields, api

# _logger = logging.getLogger(__name__)


# class Conversation(models.Model):
#     """
#     Groups messages between an employee and a specific contact.
#     Think of it as a 'chat thread' view.
#     """
#     _name = 'wa.conversation'
#     _description = 'WhatsApp Conversation Thread'
#     _order = 'last_message_date desc'
#     _rec_name = 'display_name_custom'

#     employee_session_id = fields.Many2one(
#         'wa.employee.session', string='Employee Session',
#         required=True, ondelete='cascade', index=True,
#     )
#     employee_id = fields.Many2one(
#         related='employee_session_id.employee_id',
#         store=True, string='Employee', index=True,
#     )
#     department_id = fields.Many2one(
#         related='employee_session_id.department_id',
#         store=True, string='Department',
#     )
#     phone = fields.Char('Contact Phone', required=True, index=True)
#     partner_id = fields.Many2one(
#         'res.partner', string='Contact',
#     )
#     contact_name = fields.Char(
#         compute='_compute_contact_name', string='Contact Name',
#         store=True,
#     )

#     # ---- Stats ----
#     total_messages = fields.Integer('Total Messages')
#     sent_count = fields.Integer('Sent')
#     received_count = fields.Integer('Received')
#     first_message_date = fields.Datetime('First Message')
#     last_message_date = fields.Datetime('Last Message')
#     avg_response_minutes = fields.Float('Avg Response Time (min)')
#     is_active_today = fields.Boolean(
#         compute='_compute_active_today', string='Active Today',
#     )

#     # ---- Log entries ----
#     log_ids = fields.One2many(
#         'wa.communication.log', 'conversation_id',
#         string='Messages',
#     )

#     last_message_preview = fields.Char(
#         compute='_compute_last_message_preview', string='Last Message',
#     )

#     display_name_custom = fields.Char(
#         compute='_compute_display_name_custom',
#     )

#     _unique_conversation = models.Constraint(
#         'UNIQUE (employee_session_id, phone)',
#         'A conversation already exists for this employee-contact pair.',
#     )

#     @api.depends('partner_id', 'partner_id.name', 'phone')
#     def _compute_contact_name(self):
#         import re
#         for rec in self:
#             if rec.partner_id and rec.partner_id.name:
#                 rec.contact_name = rec.partner_id.name
#                 continue

#             # Try to get push_name from latest incoming message
#             try:
#                 latest_msg = self.env['wa.communication.log'].search([
#                     ('conversation_id', '=', rec.id),
#                     ('direction', '=', 'incoming'),
#                 ], order='message_date desc', limit=1)
#                 if latest_msg and latest_msg.message_id:
#                     push_name = getattr(latest_msg.message_id, 'push_name', '') or ''
#                     if push_name:
#                         rec.contact_name = push_name
#                         continue
#             except Exception:
#                 pass

#             # Clean phone and format nicely
#             phone = rec.phone or ''
#             user_match = re.search(r'User:\s*"(\d+)"', phone)
#             if user_match:
#                 clean_phone = user_match.group(1)
#             elif phone:
#                 digits = re.sub(r'[^\d]', '', phone)
#                 clean_phone = digits if len(digits) >= 6 else phone
#             else:
#                 clean_phone = 'Unknown'

#             # Try to find partner by phone (robust approach)
#             if clean_phone and clean_phone != 'Unknown':
#                 try:
#                     last_5 = clean_phone[-5:] if len(clean_phone) >= 5 else clean_phone
#                     partners = self.env['res.partner'].sudo().search([
#                         '|',
#                         ('phone', 'ilike', last_5),
#                         ('mobile', 'ilike', last_5),
#                     ])
#                     partner = False
#                     for p in partners:
#                         p_phone = ''.join(filter(str.isdigit, p.phone or ''))
#                         p_mobile = ''.join(filter(str.isdigit, p.mobile or ''))
#                         if (p_phone and p_phone == clean_phone) or \
#                            (p_mobile and p_mobile == clean_phone) or \
#                            (len(p_phone) >= 10 and p_phone[-10:] == clean_phone[-10:]) or \
#                            (len(p_mobile) >= 10 and p_mobile[-10:] == clean_phone[-10:]):
#                             partner = p
#                             break
#                 except Exception:
#                     partner = False
#                 if partner:
#                     rec.contact_name = partner.name
#                     if not rec.partner_id:
#                         rec.partner_id = partner.id
#                 else:
#                     if len(clean_phone) > 10:
#                         rec.contact_name = f"+{clean_phone}"
#                     else:
#                         rec.contact_name = clean_phone
#             else:
#                 rec.contact_name = clean_phone

#     def _compute_last_message_preview(self):
#         for rec in self:
#             last_log = self.env['wa.communication.log'].search([
#                 ('conversation_id', '=', rec.id),
#             ], order='message_date desc', limit=1)
#             if last_log and last_log.message_text:
#                 prefix = '↗ ' if last_log.direction == 'outgoing' else ''
#                 text = last_log.message_text[:50]
#                 rec.last_message_preview = f"{prefix}{text}"
#             else:
#                 rec.last_message_preview = ''

#     def _compute_display_name_custom(self):
#         for rec in self:
#             emp = rec.employee_id.name or '?'
#             contact = rec.contact_name or rec.phone or '?'
#             rec.display_name_custom = f"{emp} ↔ {contact}"

#     def _compute_active_today(self):
#         today_start = fields.Datetime.now().replace(
#             hour=0, minute=0, second=0, microsecond=0
#         )
#         for rec in self:
#             rec.is_active_today = (
#                 rec.last_message_date and rec.last_message_date >= today_start
#             )

#     # ----------------------------------------------------------
#     # Get or Create conversation
#     # ----------------------------------------------------------
#     @api.model
#     def _get_or_create(self, emp_session, phone, partner=None):
#         """Get existing or create new conversation thread."""
#         import re
#         if not phone:
#             return False

#         # Clean phone number from JID protobuf format
#         clean_phone = phone
#         user_match = re.search(r'User:\s*"(\d+)"', phone)
#         if user_match:
#             clean_phone = user_match.group(1)
#         else:
#             digits = re.sub(r'[^\d]', '', phone)
#             if digits and len(digits) >= 6:
#                 clean_phone = digits

#         # Skip status/broadcast messages
#         if clean_phone in ('status', 'unknown', 'broadcast', ''):
#             return False

#         # Search by clean phone or original phone
#         conversation = self.search([
#             ('employee_session_id', '=', emp_session.id),
#             '|',
#             ('phone', '=', clean_phone),
#             ('phone', '=', phone),
#         ], limit=1)

#         if not conversation:
#             conversation = self.create({
#                 'employee_session_id': emp_session.id,
#                 'phone': clean_phone,
#                 'partner_id': partner.id if partner else False,
#             })
#         elif conversation.phone != clean_phone:
#             # Update dirty phone to clean version
#             conversation.phone = clean_phone

#         # Update partner if newly detected
#         if partner and not conversation.partner_id:
#             conversation.partner_id = partner.id

#         return conversation

#     # ----------------------------------------------------------
#     # Update conversation stats
#     # ----------------------------------------------------------
#     def _update_stats(self):
#         """Recompute stats from log entries."""
#         for rec in self:
#             logs = self.env['wa.communication.log'].search([
#                 ('conversation_id', '=', rec.id),
#             ], order='message_date asc')

#             if not logs:
#                 continue

#             sent = logs.filtered(lambda l: l.direction == 'outgoing')
#             received = logs.filtered(lambda l: l.direction == 'incoming')

#             vals = {
#                 'total_messages': len(logs),
#                 'sent_count': len(sent),
#                 'received_count': len(received),
#                 'first_message_date': logs[0].message_date,
#                 'last_message_date': logs[-1].message_date,
#             }

#             # Calculate average response time
#             # For each incoming msg, find the next outgoing msg = response time
#             response_times = []
#             for i, log in enumerate(logs):
#                 if log.direction == 'incoming':
#                     # Find next outgoing
#                     for j in range(i + 1, len(logs)):
#                         if logs[j].direction == 'outgoing':
#                             if log.message_date and logs[j].message_date:
#                                 delta = (
#                                     logs[j].message_date - log.message_date
#                                 )
#                                 minutes = delta.total_seconds() / 60
#                                 # Only count if < 24 hours (ignore old threads)
#                                 if 0 < minutes < 1440:
#                                     response_times.append(minutes)
#                             break

#             if response_times:
#                 vals['avg_response_minutes'] = round(
#                     sum(response_times) / len(response_times), 1
#                 )

#             rec.write(vals)

#     def action_refresh_stats(self):
#         """Public wrapper for _update_stats, callable from button."""
#         self._update_stats()

#     # ----------------------------------------------------------
#     # Actions
#     # ----------------------------------------------------------
#     def action_view_messages(self):
#         """View all messages in this conversation."""
#         self.ensure_one()
#         return {
#             'type': 'ir.actions.act_window',
#             'name': f'Chat: {self.contact_name or self.phone}',
#             'res_model': 'wa.communication.log',
#             'view_mode': 'list,form',
#             'domain': [('conversation_id', '=', self.id)],
#             'context': {'default_conversation_id': self.id},
#         }
import logging
import re
from odoo import models, fields, api

_logger = logging.getLogger(__name__)


class Conversation(models.Model):
    """
    Groups messages between an employee and a specific contact.
    Think of it as a 'chat thread' view.
    """
    _name = 'wa.conversation'
    _description = 'WhatsApp Conversation Thread'
    _order = 'last_message_date desc'
    _rec_name = 'display_name_custom'

    employee_session_id = fields.Many2one(
        'wa.employee.session', string='Employee Session',
        required=True, ondelete='cascade', index=True,
    )
    employee_id = fields.Many2one(
        related='employee_session_id.employee_id',
        store=True, string='Employee', index=True,
    )
    department_id = fields.Many2one(
        related='employee_session_id.department_id',
        store=True, string='Department',
    )
    phone = fields.Char('Contact Phone', required=True, index=True)
    partner_id = fields.Many2one(
        'res.partner', string='Contact',
    )
    contact_name = fields.Char(
        compute='_compute_contact_name', string='Contact Name',
        store=True,
    )

    # ---- Stats ----
    total_messages = fields.Integer('Total Messages')
    sent_count = fields.Integer('Sent')
    received_count = fields.Integer('Received')
    first_message_date = fields.Datetime('First Message')
    last_message_date = fields.Datetime('Last Message')
    avg_response_minutes = fields.Float('Avg Response Time (min)')
    is_active_today = fields.Boolean(
        compute='_compute_active_today', string='Active Today',
    )

    # ---- Tone / Sentiment ----
    avg_tone_score = fields.Float(
        'Avg Tone Score (0-100)',
        help='Average tone score of outgoing messages. 0=Harsh, 50=Neutral, 100=Polite.',
    )
    tone_label = fields.Char(
        'Employee Tone',
        help='Soft (polite), Neutral, or Hard (harsh) based on avg tone score.',
    )

    # ---- Log entries ----
    log_ids = fields.One2many(
        'wa.communication.log', 'conversation_id',
        string='Messages',
    )

    last_message_preview = fields.Char(
        compute='_compute_last_message_preview', string='Last Message',
    )

    display_name_custom = fields.Char(
        compute='_compute_display_name_custom',
    )

    _unique_conversation = models.Constraint(
        'UNIQUE (employee_session_id, phone)',
        'A conversation already exists for this employee-contact pair.',
    )

    @api.model
    def _is_ghost_partner(self, partner):
        """Returns True if partner was auto-created by WhatsApp module."""
        if not partner:
            return False
        comment = (partner.comment or '').lower()
        return 'auto-created from whatsapp' in comment

    @api.model
    def _find_real_partner_by_phone(self, phone):
        """Search res.partner by phone or phone_sanitized, skipping ghost contacts."""
        if not phone:
            return False
        clean_phone = ''.join(filter(str.isdigit, phone))
        if not clean_phone or len(clean_phone) < 5 or len(clean_phone) > 17:
            return False
        last_5 = clean_phone[-5:]
        partners = self.env['res.partner'].sudo().search([
            ('phone', 'ilike', last_5), ('active', '=', True),
        ])
        partners |= self.env['res.partner'].sudo().search([
            ('phone_sanitized', 'ilike', last_5), ('active', '=', True),
        ])
        for p in partners:
            if self._is_ghost_partner(p):
                continue
            p_phone = ''.join(filter(str.isdigit, p.phone or ''))
            p_san = ''.join(filter(str.isdigit, p.phone_sanitized or ''))
            matched = (
                (p_phone and p_phone == clean_phone) or
                (p_san and p_san == clean_phone) or
                (len(p_phone) >= 7 and len(clean_phone) >= 7 and p_phone[-10:] == clean_phone[-10:]) or
                (len(p_san) >= 7 and len(clean_phone) >= 7 and p_san[-10:] == clean_phone[-10:])
            )
            if matched:
                return p
        return False

    @api.depends('partner_id', 'partner_id.name', 'phone')
    def _compute_contact_name(self):
        # whatsapp.group is provided by whatsapp_neonize — guard if missing
        group_model = self.env['whatsapp.group'] if 'whatsapp.group' in self.env else None
        for rec in self:
            # Group JID? Resolve to friendly group name via whatsapp.group cache.
            phone_raw = (rec.phone or '').strip()
            phone_digits = ''.join(filter(str.isdigit, phone_raw))
            looks_like_group = (
                phone_digits.isdigit()
                and len(phone_digits) >= 15
                and phone_digits.startswith('120')
            )
            if looks_like_group and group_model is not None:
                try:
                    grp = group_model.sudo().search(
                        [('jid', '=', phone_digits)], limit=1,
                    )
                    if grp and grp.name:
                        rec.contact_name = grp.name
                        continue
                except Exception:
                    pass

            # Use partner name only if it's a real (non-ghost) partner
            if rec.partner_id and rec.partner_id.name and not self._is_ghost_partner(rec.partner_id):
                rec.contact_name = rec.partner_id.name
                continue

            # Try to find real partner by phone
            real_partner = self._find_real_partner_by_phone(rec.phone)
            if real_partner:
                rec.contact_name = real_partner.name
                if rec.partner_id != real_partner:
                    rec.sudo().write({'partner_id': real_partner.id})
                continue

            # Try push_name from latest incoming message
            try:
                latest_msg = self.env['wa.communication.log'].search([
                    ('conversation_id', '=', rec.id),
                    ('direction', '=', 'incoming'),
                ], order='message_date desc', limit=1)
                if latest_msg and latest_msg.message_id:
                    push_name = getattr(latest_msg.message_id, 'push_name', '') or ''
                    if push_name:
                        rec.contact_name = push_name
                        continue
            except Exception:
                pass

            # Format phone number as display name
            phone = rec.phone or ''
            user_match = re.search(r'User:\s*"(\d+)"', phone)
            if user_match:
                clean_phone = user_match.group(1)
            elif phone:
                digits = re.sub(r'[^\d]', '', phone)
                clean_phone = digits if len(digits) >= 6 else phone
            else:
                clean_phone = 'Unknown'

            if clean_phone and clean_phone != 'Unknown' and len(clean_phone) > 10:
                rec.contact_name = f"+{clean_phone}"
            else:
                rec.contact_name = clean_phone or 'Unknown'

    def _compute_last_message_preview(self):
        for rec in self:
            last_log = self.env['wa.communication.log'].search([
                ('conversation_id', '=', rec.id),
            ], order='message_date desc', limit=1)
            if last_log and last_log.message_text:
                prefix = '↗ ' if last_log.direction == 'outgoing' else ''
                text = last_log.message_text[:50]
                rec.last_message_preview = f"{prefix}{text}"
            else:
                rec.last_message_preview = ''

    def _compute_display_name_custom(self):
        for rec in self:
            emp = rec.employee_id.name or '?'
            contact = rec.contact_name or rec.phone or '?'
            rec.display_name_custom = f"{emp} ↔ {contact}"

    def _compute_active_today(self):
        today_start = fields.Datetime.now().replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        for rec in self:
            rec.is_active_today = (
                rec.last_message_date and rec.last_message_date >= today_start
            )

    @api.model
    def _get_or_create(self, emp_session, phone, partner=None):
        """Get existing or create new conversation thread."""
        if not phone:
            return False

        clean_phone = phone
        user_match = re.search(r'User:\s*"(\d+)"', phone)
        if user_match:
            clean_phone = user_match.group(1)
        else:
            digits = re.sub(r'[^\d]', '', phone)
            if digits and len(digits) >= 6:
                clean_phone = digits

        if clean_phone in ('status', 'unknown', 'broadcast', ''):
            return False

        # Resolve real partner — never link ghost contacts
        if not partner:
            partner = self._find_real_partner_by_phone(clean_phone)
        elif self._is_ghost_partner(partner):
            real = self._find_real_partner_by_phone(clean_phone)
            partner = real if real else False

        conversation = self.search([
            ('employee_session_id', '=', emp_session.id),
            '|',
            ('phone', '=', clean_phone),
            ('phone', '=', phone),
        ], limit=1)

        if not conversation:
            conversation = self.create({
                'employee_session_id': emp_session.id,
                'phone': clean_phone,
                'partner_id': partner.id if partner else False,
            })
            _logger.info("Created conversation phone=%s partner=%s",
                         clean_phone, partner.name if partner else 'None')
        else:
            if conversation.phone != clean_phone:
                conversation.phone = clean_phone
            # Upgrade ghost link to real partner
            if partner and (not conversation.partner_id or self._is_ghost_partner(conversation.partner_id)):
                conversation.partner_id = partner.id
                _logger.info("Relinked conv %s to real partner %s", conversation.id, partner.name)

        return conversation

    @api.model
    def _cron_fix_ghost_partner_links(self):
        """Cron: relink all conversations that point to ghost partners."""
        fixed = 0
        conversations = self.sudo().search([('partner_id', '!=', False)])
        for conv in conversations:
            if not self._is_ghost_partner(conv.partner_id):
                continue
            real_partner = self._find_real_partner_by_phone(conv.phone)
            if real_partner:
                conv.sudo().write({'partner_id': real_partner.id})
                _logger.info("[GHOST FIX] Conv %s relinked to %s (ID %s)",
                             conv.id, real_partner.name, real_partner.id)
                fixed += 1
            else:
                conv.sudo().write({'partner_id': False})
                _logger.info("[GHOST FIX] Conv %s ghost link cleared", conv.id)
        _logger.info("[GHOST FIX] Done. Fixed %d conversations.", fixed)

    def _update_stats(self):
        """Recompute stats from log entries."""
        for rec in self:
            logs = self.env['wa.communication.log'].search([
                ('conversation_id', '=', rec.id),
            ], order='message_date asc')
            if not logs:
                continue
            sent = logs.filtered(lambda l: l.direction == 'outgoing')
            received = logs.filtered(lambda l: l.direction == 'incoming')
            vals = {
                'total_messages': len(logs),
                'sent_count': len(sent),
                'received_count': len(received),
                'first_message_date': logs[0].message_date,
                'last_message_date': logs[-1].message_date,
            }
            response_times = []
            for i, log in enumerate(logs):
                if log.direction == 'incoming':
                    for j in range(i + 1, len(logs)):
                        if logs[j].direction == 'outgoing':
                            if log.message_date and logs[j].message_date:
                                delta = logs[j].message_date - log.message_date
                                minutes = delta.total_seconds() / 60
                                if 0 < minutes < 1440:
                                    response_times.append(minutes)
                            break
            if response_times:
                vals['avg_response_minutes'] = round(
                    sum(response_times) / len(response_times), 1
                )

            # Compute avg tone score from outgoing message tone analyses
            outgoing_log_ids = sent.ids
            if outgoing_log_ids:
                tones = self.env['wa.message.tone'].search([
                    ('communication_log_id', 'in', outgoing_log_ids),
                ])
                if tones:
                    avg_score = sum(t.tone_score for t in tones) / len(tones)
                    vals['avg_tone_score'] = round(avg_score, 1)
                    if avg_score >= 65:
                        vals['tone_label'] = 'Soft'
                    elif avg_score <= 35:
                        vals['tone_label'] = 'Hard'
                    else:
                        vals['tone_label'] = 'Neutral'

            rec.write(vals)

    def action_refresh_stats(self):
        self._update_stats()

    def action_view_messages(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': f'Chat: {self.contact_name or self.phone}',
            'res_model': 'wa.communication.log',
            'view_mode': 'list,form',
            'domain': [('conversation_id', '=', self.id)],
            'context': {'default_conversation_id': self.id},
        }
