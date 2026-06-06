import logging
from odoo import models, fields

_logger = logging.getLogger(__name__)

class ProductTemplate(models.Model):
    _inherit = 'product.template'

    wa_retail_price = fields.Float(
        string='Retail Price (WhatsApp)',
        help='Price used for WhatsApp auto-replies when the sender is not a recognized contact.'
    )
