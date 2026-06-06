"""Tone keyword rules — admin-editable lists of soft / hard / profanity words.

Mirrors `crm_call_recorder.wa.keyword.alert.rule` but slimmer: we don't
need severity, alert log, or partner linkage — tone analysis just needs the
match set per category. Three default rules are seeded via data/tone_keywords.xml
on install; admin can add more or edit the seeds via Configuration.
"""

import logging
import re

from odoo import api, fields, models
from odoo.exceptions import ValidationError

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

    @api.constrains('match_type', 'keywords')
    def _check_regex_keywords(self):
        """Reject save when match_type='regex' and any line fails re.compile().
        Prevents a silent neutral-tone bug: a broken regex skips ALL matches in
        that rule, making real soft/hard signals invisible to analysts."""
        for rule in self:
            if rule.match_type != 'regex' or not rule.keywords:
                continue
            bad = []
            for line in rule.keywords.strip().split('\n'):
                pattern = line.strip()
                if not pattern:
                    continue
                try:
                    re.compile(pattern)
                except re.error as exc:
                    bad.append(f'{pattern!r} ({exc})')
            if bad:
                raise ValidationError(
                    "Invalid regex pattern(s) in rule '%s':\n  - %s"
                    % (rule.name, '\n  - '.join(bad))
                )

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
