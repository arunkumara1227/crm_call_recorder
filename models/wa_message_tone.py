import logging
from odoo import models, fields, api

_logger = logging.getLogger(__name__)

try:
    from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
    _vader = SentimentIntensityAnalyzer()
    HAS_VADER = True
except ImportError:
    _vader = None
    HAS_VADER = False
    _logger.warning("vaderSentiment not installed. Run: pip install vaderSentiment")


class MessageTone(models.Model):
    """
    Tone/sentiment analysis for OUTGOING employee messages.
    Determines if an employee is being Soft (polite) or Hard (harsh) with clients.

    Scoring pipeline:
        sentiment_score + keywords  →  tone_score (0-100, weighted)
        tone_score                  →  tone_category
        tone_category               →  tone_label / is_harsh / is_polite

    Weights:
        Keywords = 70% (primary signal — controllable, language-agnostic)
        VADER    = 30% (secondary signal — fills gap when no keywords match)
    """
    _name = 'wa.message.tone'
    _description = 'Message Tone Analysis'
    _order = 'message_date desc'

    # ---- Relations ----
    communication_log_id = fields.Many2one(
        'wa.communication.log', string='Communication Log',
        required=True, ondelete='cascade', index=True,
    )
    employee_session_id = fields.Many2one(
        related='communication_log_id.employee_session_id',
        store=True, string='Employee Session', index=True,
    )
    employee_id = fields.Many2one(
        related='communication_log_id.employee_id',
        store=True, string='Employee', index=True,
    )
    message_date = fields.Datetime(
        related='communication_log_id.message_date',
        store=True, string='Message Date', index=True,
    )
    message_text = fields.Text(
        related='communication_log_id.message_text',
        string='Message',
    )

    # ---- Raw Signals ----
    sentiment_score = fields.Float(
        'VADER Score (-1 to 1)', digits=(3, 2),
        aggregator='avg',
        help='-1 = Very Negative, 0 = Neutral, 1 = Very Positive',
    )
    soft_keywords_found = fields.Text(
        'Soft Keywords Found',
        help='Polite/friendly words detected in the message',
    )
    hard_keywords_found = fields.Text(
        'Hard Keywords Found',
        help='Harsh/aggressive words detected in the message',
    )

    # ---- Computed Score & Category ----
    tone_score = fields.Integer(
        'Tone Score (0-100)',
        compute='_compute_tone_score', store=True,
        aggregator='avg',
        help='Weighted score: 0=Harshest, 50=Neutral, 100=Most Polite',
    )
    tone_category = fields.Selection([
        ('harsh',      'Harsh / Aggressive'),
        ('curt',       'Curt / Dismissive'),
        ('neutral',    'Neutral / Professional'),
        ('polite',     'Polite / Friendly'),
        ('very_polite','Very Polite / Warm'),
    ], string='Tone Category', compute='_compute_tone_category', store=True)

    tone_label = fields.Char(
        'Tone', compute='_compute_tone_label', store=True,
        help='Soft / Neutral / Hard',
    )
    is_harsh = fields.Boolean('Is Harsh', compute='_compute_tone_flags', store=True)
    is_polite = fields.Boolean('Is Polite', compute='_compute_tone_flags', store=True)

    # ---- Sentiment Category (for display) ----
    sentiment_category = fields.Selection([
        ('very_negative', 'Very Negative'),
        ('negative',      'Negative'),
        ('neutral',       'Neutral'),
        ('positive',      'Positive'),
        ('very_positive', 'Very Positive'),
    ], string='Sentiment', compute='_compute_sentiment_category', store=True)

    # ----------------------------------------------------------
    # Compute: tone_score  (keywords=70%, VADER=30%)
    # ----------------------------------------------------------
    @api.depends('sentiment_score', 'soft_keywords_found', 'hard_keywords_found')
    def _compute_tone_score(self):
        """
        Formula (all deltas from neutral base of 50):

            soft_pts  = min(soft_count  * 12, 42)   # each soft keyword +12, max +42
            hard_pts  = min(hard_count  * 18, 54)   # each hard keyword -18, max -54
            vader_pts = sentiment_score * 30         # VADER maps -1..+1 → -30..+30

            delta = soft_pts - hard_pts + vader_pts
            score = clamp(50 + delta, 0, 100)

        Examples:
            "Thank you so much!" (1 soft kw, VADER +0.8) → 50 +12 +24 = 86  → very_polite
            "ok" (no kw, VADER 0)                        → 50 +0  +0  = 50  → neutral
            "Sorry, not possible" (1 soft, 1 hard, -0.2) → 50 +12 -18 -6 = 38 → curt
            "I already told you, figure it out" (2 hard) → 50 -36 -12 = 2   → harsh
        """
        for rec in self:
            soft_count = _count_keywords(rec.soft_keywords_found)
            hard_count = _count_keywords(rec.hard_keywords_found)

            soft_pts  = min(soft_count * 12, 42)
            hard_pts  = min(hard_count * 18, 54)
            vader_pts = (rec.sentiment_score or 0.0) * 30

            delta = soft_pts - hard_pts + vader_pts
            rec.tone_score = int(max(0, min(100, 50 + delta)))

    # ----------------------------------------------------------
    # Compute: tone_category  (from tone_score ranges)
    # ----------------------------------------------------------
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
            rec.is_harsh  = rec.tone_category in ('harsh', 'curt')
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

    # ----------------------------------------------------------
    # Core Analysis
    # ----------------------------------------------------------
    def _analyze_message(self, message_text):
        """
        Analyze a message and return raw signals.
        Single DB query: fetches all tone rules at once, splits in Python.
        Skips VADER for very short messages (< 3 words) — too unreliable.
        """
        result = {
            'sentiment_score': 0.0,
            'soft_keywords_found': '',
            'hard_keywords_found': '',
        }

        if not message_text or not message_text.strip():
            return result

        # VADER: skip for very short messages (< 3 words) — unreliable on "ok", "noted"
        word_count = len(message_text.split())
        if HAS_VADER and word_count >= 3:
            try:
                scores = _vader.polarity_scores(message_text)
                result['sentiment_score'] = round(scores['compound'], 2)
            except Exception as e:
                _logger.warning("VADER error: %s", e)

        # Single DB query for all tone keyword rules
        all_rules = self.env['wa.keyword.alert.rule'].search([
            ('category', 'in', ('soft_language', 'hard_language', 'profanity')),
            ('active', '=', True),
        ])

        soft_keywords = []
        hard_keywords = []

        for rule in all_rules:
            matches = rule._check_text(message_text)
            if not matches:
                continue
            if rule.category == 'soft_language':
                soft_keywords.extend(matches)
            else:  # hard_language or profanity
                hard_keywords.extend(matches)

        if soft_keywords:
            result['soft_keywords_found'] = ', '.join(dict.fromkeys(soft_keywords))
        if hard_keywords:
            result['hard_keywords_found'] = ', '.join(dict.fromkeys(hard_keywords))

        return result

    @api.model
    def create_or_update_for_message(self, communication_log_id):
        """
        Create or update tone analysis for a communication log entry.
        Only analyzes OUTGOING messages (employee → client).
        """
        log = self.env['wa.communication.log'].browse(communication_log_id)
        if not log.exists() or log.direction != 'outgoing':
            return False

        analysis = self._analyze_message(log.message_text)

        values = {
            'communication_log_id': log.id,
            'sentiment_score':      analysis['sentiment_score'],
            'soft_keywords_found':  analysis['soft_keywords_found'],
            'hard_keywords_found':  analysis['hard_keywords_found'],
        }

        tone = self.search([('communication_log_id', '=', log.id)], limit=1)
        if tone:
            tone.write(values)
        else:
            tone = self.create(values)

        return tone.id


# ----------------------------------------------------------
# Helper (module-level, no DB access needed)
# ----------------------------------------------------------
def _count_keywords(keyword_text):
    """Count distinct keywords from comma-separated keyword field."""
    if not keyword_text:
        return 0
    return len([k for k in keyword_text.split(',') if k.strip()])
