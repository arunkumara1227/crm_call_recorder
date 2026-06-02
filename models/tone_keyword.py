"""Tone keyword rules — admin-editable lists of soft / hard / profanity words.

Mirrors `whatsapp_employee_tracker.wa.keyword.alert.rule` but slimmer: we don't
need severity, alert log, or partner linkage — tone analysis just needs the
match set per category. Three default rules are seeded via data/tone_keywords.xml
on install; admin can add more or edit the seeds via Configuration.
"""

import logging
import re

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class CrmCallToneKeyword(models.Model):
    _name = 'crm.call.tone.keyword'
    _description = 'CRM Call Tone Keyword Rule'
    _order = 'category, sequence, id'

    name = fields.Char(
        'Rule Name', required=True,
        help='Free-text label, e.g. "Default soft language" or "Internal jargon".',
    )
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    keywords = fields.Text(
        'Keywords', required=True,
        help='One keyword or phrase per line. Case-insensitive matching.',
    )
    category = fields.Selection([
        ('soft', 'Soft / Polite'),
        ('hard', 'Hard / Harsh'),
        ('profanity', 'Profanity / Inappropriate'),
    ], string='Category', required=True, default='soft')
    match_type = fields.Selection([
        ('contains', 'Contains (anywhere in text)'),
        ('exact_word', 'Exact Word Match'),
        ('regex', 'Regular Expression'),
    ], string='Match Type', default='contains', required=True)
    description = fields.Text('Description')

    def _check_text(self, text):
        """Return list of keywords from this rule found in `text`."""
        if not text or not self.keywords:
            return []

        text_lower = text.lower()
        matches = []

        for line in self.keywords.strip().split('\n'):
            keyword = line.strip()
            if not keyword:
                continue

            if self.match_type == 'contains':
                if keyword.lower() in text_lower:
                    matches.append(keyword)
            elif self.match_type == 'exact_word':
                pattern = r'\b' + re.escape(keyword) + r'\b'
                if re.search(pattern, text, re.IGNORECASE):
                    matches.append(keyword)
            elif self.match_type == 'regex':
                try:
                    if re.search(keyword, text, re.IGNORECASE):
                        matches.append(keyword)
                except re.error:
                    _logger.warning(
                        "Invalid regex in tone keyword rule %s: %s",
                        self.name, keyword,
                    )
        return matches
