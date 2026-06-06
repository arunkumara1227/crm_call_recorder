"""Bridge `hr.employee` ↔ `crm.call.recording` so the employee form can show
unified call + WhatsApp activity (when whatsapp_employee_tracker is installed).
"""

from odoo import api, fields, models


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    call_api_key_ids = fields.One2many(
        'crm.call.api.key', 'employee_id',
        string='Call Recorder API Keys',
        help='Per-device keys generated for this employee. Each key tracks '
             'one Android device.',
    )
    call_recording_count = fields.Integer(
        compute='_compute_call_recording_count',
        string='Call Recordings',
    )

    @api.depends('call_api_key_ids')
    def _compute_call_recording_count(self):
        Recording = self.env['crm.call.recording'].sudo()
        for rec in self:
            if rec.call_api_key_ids:
                rec.call_recording_count = Recording.search_count([
                    ('created_by_api_key_id', 'in', rec.call_api_key_ids.ids),
                ])
            else:
                rec.call_recording_count = 0

    def action_view_call_recordings(self):
        """Stat-button action — open the Recordings list filtered to this
        employee's devices."""
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id(
            'crm_call_recorder.action_crm_call_recording'
        )
        action['domain'] = [
            ('created_by_api_key_id', 'in', self.call_api_key_ids.ids),
        ]
        action['context'] = {
            'search_default_group_state': 1,
        }
        return action
