"""Tone analysis for transcribed call recordings.

Ported from `crm_call_recorder.wa.message.tone`. Same VADER + keyword
formula (keywords 70%, VADER 30%); same 5-tier category + 3-tier label.

Adapted to operate on `crm.call.recording.transcription_text` instead of
`wa.communication.log.message_text`, and to surface the recording's per-device
api_key for downstream filtering by "Arun Infinx" etc.
"""

import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)

try:
    from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
    _vader = SentimentIntensityAnalyzer()
    HAS_VADER = True
except ImportError:
    _vader = None
    HAS_VADER = False
    _logger.warning(
        "vaderSentiment not installed. Run: pip install vaderSentiment "
        "(crm_call_recorder external_dependencies should normally block install — "
        "if you see this warning, the dep was bypassed)."
    )


class CrmCallTone(models.Model):
    _name = 'crm.call.tone'
    _description = 'CRM Call Tone Analysis'
    _order = 'call_date desc'
    _rec_name = 'recording_id'

    # ── Relations ─────────────────────────────────────────────────────
    recording_id = fields.Many2one(
        'crm.call.recording', string='Recording',
        required=True, ondelete='cascade', index=True,
    )
    # Filterable proxies (stored related) — these are what the dashboard groups by.
    call_date = fields.Datetime(
        related='recording_id.call_date', store=True,
        string='Call Date', index=True,
    )
    api_key_id = fields.Many2one(
        related='recording_id.created_by_api_key_id', store=True,
        string='Uploaded via', index=True,
    )
    user_id = fields.Many2one(
        related='api_key_id.user_id', store=True,
        string='Agent', index=True,
    )
    phone = fields.Char(
        related='recording_id.phone', store=True, index=True,
    )
    phone_digits = fields.Char(
        related='recording_id.phone_digits', store=True, index=True,
    )
    matched_partner_id = fields.Many2one(
        related='recording_id.matched_partner_id', store=True,
        string='Contact',
    )
    transcript_text = fields.Text(
        related='recording_id.transcription_text',
        string='Transcript',
    )

    # ── Raw signals ───────────────────────────────────────────────────
    sentiment_score = fields.Float(
        'VADER Score (-1 to 1)', digits=(3, 2), aggregator='avg',
        help='-1 = Very Negative, 0 = Neutral, 1 = Very Positive',
    )
    soft_keywords_found = fields.Text('Soft Keywords Found')
    hard_keywords_found = fields.Text('Hard Keywords Found')

    # ── Computed score + category ─────────────────────────────────────
    tone_score = fields.Integer(
        'Tone Score (0-100)', compute='_compute_tone_score',
        store=True, aggregator='avg',
        help='Weighted score: 0=Harshest, 50=Neutral, 100=Most Polite',
    )
    tone_category = fields.Selection([
        ('harsh',       'Harsh / Aggressive'),
        ('curt',        'Curt / Dismissive'),
        ('neutral',     'Neutral / Professional'),
        ('polite',      'Polite / Friendly'),
        ('very_polite', 'Very Polite / Warm'),
    ], string='Tone Category', compute='_compute_tone_category', store=True)

    tone_label = fields.Char(
        'Tone', compute='_compute_tone_label', store=True, index=True,
        help='Soft / Neutral / Hard',
    )
    is_harsh = fields.Boolean(compute='_compute_tone_flags', store=True)
    is_polite = fields.Boolean(compute='_compute_tone_flags', store=True)

    sentiment_category = fields.Selection([
        ('very_negative', 'Very Negative'),
        ('negative',      'Negative'),
        ('neutral',       'Neutral'),
        ('positive',      'Positive'),
        ('very_positive', 'Very Positive'),
    ], string='Sentiment', compute='_compute_sentiment_category', store=True)

    # ──────────────────────────────────────────────────────────────────
    # Compute: tone_score (keywords=70%, VADER=30%)
    # ──────────────────────────────────────────────────────────────────
    @api.depends('sentiment_score', 'soft_keywords_found', 'hard_keywords_found')
    def _compute_tone_score(self):
        """Formula (deltas from neutral base of 50):

            soft_pts  = min(soft_count  * 12, 42)    # max +42
            hard_pts  = min(hard_count  * 18, 54)    # max -54
            vader_pts = sentiment_score * 30         # ±30
            score = clamp(50 + soft_pts - hard_pts + vader_pts, 0, 100)
        """
        for rec in self:
            soft_count = _count_keywords(rec.soft_keywords_found)
            hard_count = _count_keywords(rec.hard_keywords_found)

            soft_pts = min(soft_count * 12, 42)
            hard_pts = min(hard_count * 18, 54)
            vader_pts = (rec.sentiment_score or 0.0) * 30

            delta = soft_pts - hard_pts + vader_pts
            rec.tone_score = int(max(0, min(100, 50 + delta)))

    @api.depends('tone_score')
    def _compute_tone_category(self):
        for rec in self:
            s = rec.tone_score
            if s <= 20:
                rec.tone_category = 'harsh'
            elif s <= 40:
                rec.tone_category = 'curt'
            elif s <= 60:
                rec.tone_category = 'neutral'
            elif s <= 80:
                rec.tone_category = 'polite'
            else:
                rec.tone_category = 'very_polite'

    @api.depends('tone_category')
    def _compute_tone_label(self):
        for rec in self:
            if rec.tone_category in ('harsh', 'curt'):
                rec.tone_label = 'Hard'
            elif rec.tone_category in ('polite', 'very_polite'):
                rec.tone_label = 'Soft'
            else:
                rec.tone_label = 'Neutral'

    @api.depends('tone_category')
    def _compute_tone_flags(self):
        for rec in self:
            rec.is_harsh = rec.tone_category in ('harsh', 'curt')
            rec.is_polite = rec.tone_category in ('polite', 'very_polite')

    @api.depends('sentiment_score')
    def _compute_sentiment_category(self):
        for rec in self:
            s = rec.sentiment_score or 0.0
            if s >= 0.6:
                rec.sentiment_category = 'very_positive'
            elif s >= 0.2:
                rec.sentiment_category = 'positive'
            elif s > -0.2:
                rec.sentiment_category = 'neutral'
            elif s > -0.6:
                rec.sentiment_category = 'negative'
            else:
                rec.sentiment_category = 'very_negative'

    # ──────────────────────────────────────────────────────────────────
    # Core analysis
    # ──────────────────────────────────────────────────────────────────
    @api.model
    def _analyze_text(self, text):
        """Run VADER + keyword rules on `text`. Returns raw signals dict.

        Skips VADER for < 3 words (matches WA tracker — too noisy for short clips).
        """
        result = {
            'sentiment_score': 0.0,
            'soft_keywords_found': '',
            'hard_keywords_found': '',
        }

        if not text or not text.strip():
            return result

        word_count = len(text.split())
        if HAS_VADER and word_count >= 3:
            try:
                scores = _vader.polarity_scores(text)
                result['sentiment_score'] = round(scores['compound'], 2)
            except Exception as e:
                _logger.warning("VADER error on tone analysis: %s", e)

        # Single DB query for all active keyword rules.
        rules = self.env['crm.call.tone.keyword'].search([('active', '=', True)])

        soft_kw, hard_kw = [], []
        for rule in rules:
            matches = rule._check_text(text)
            if not matches:
                continue
            if rule.category == 'soft':
                soft_kw.extend(matches)
            else:  # hard or profanity
                hard_kw.extend(matches)

        if soft_kw:
            result['soft_keywords_found'] = ', '.join(dict.fromkeys(soft_kw))
        if hard_kw:
            result['hard_keywords_found'] = ', '.join(dict.fromkeys(hard_kw))

        return result

    @api.model
    def create_or_update_for_recording(self, recording_id):
        """Idempotent: create the tone row, or update the existing one. Returns
        the tone row id, or False if the recording isn't ready to analyse."""
        Recording = self.env['crm.call.recording']
        rec = Recording.browse(recording_id)
        if not rec.exists():
            return False
        if rec.transcription_status != 'done' or not (rec.transcription_text or '').strip():
            # Nothing to analyse yet. Caller may retry once transcription completes.
            return False
        # Word-count guard mirrors WA tracker: < 3 words = no analysis row created.
        if len((rec.transcription_text or '').split()) < 3:
            return False

        signals = self._analyze_text(rec.transcription_text)
        values = {
            'recording_id': rec.id,
            'sentiment_score': signals['sentiment_score'],
            'soft_keywords_found': signals['soft_keywords_found'],
            'hard_keywords_found': signals['hard_keywords_found'],
        }

        tone = self.search([('recording_id', '=', rec.id)], limit=1)
        if tone:
            tone.write(values)
        else:
            tone = self.create(values)

        # Push a bus notification on Hard tone so the /calls bell can react in
        # real time. Wrapped in try/except — failure must not block the tone.
        try:
            if tone.tone_label == 'Hard':
                Bus = self.env['bus.bus']
                Bus._sendone(
                    'crm_call_recorder.alert', 'harsh_tone',
                    {
                        'recording_id': rec.id,
                        'phone': rec.phone or '',
                        'tone_score': float(tone.tone_score or 0),
                        'call_date': fields.Datetime.to_string(rec.call_date) if rec.call_date else '',
                        'device_name': rec.created_by_api_key_id.name or '' if rec.created_by_api_key_id else '',
                    },
                )
        except Exception as e:
            _logger.warning("Bus push for harsh tone failed: %s", e)

        return tone.id


# ──────────────────────────────────────────────────────────────────────
# Helper (module-level, no DB access needed)
# ──────────────────────────────────────────────────────────────────────


def _count_keywords(keyword_text):
    """Count distinct keywords from comma-separated text. 0 on empty."""
    if not keyword_text:
        return 0
    return len([k for k in keyword_text.split(',') if k.strip()])
