from odoo import models, fields


class HrEmployeeInherit(models.Model):
    _inherit = 'hr.employee'

    wa_session_id = fields.Many2one(
        'wa.employee.session', string='WhatsApp Session',
        compute='_compute_wa_session',
    )
    wa_monitoring = fields.Boolean(
        related='wa_session_id.monitoring_enabled',
        string='WA Monitoring Active',
    )
    wa_total_messages = fields.Integer(
        related='wa_session_id.total_messages',
        string='WA Total Messages',
    )
    wa_quality_score = fields.Float(
        related='wa_session_id.quality_score',
        string='WA Quality Score',
    )

    def _compute_wa_session(self):
        for rec in self:
            session = self.env['wa.employee.session'].search([
                ('employee_id', '=', rec.id),
            ], limit=1)
            rec.wa_session_id = session.id if session else False

    def action_view_wa_tracker(self):
        """Open WhatsApp tracker for this employee."""
        self.ensure_one()
        session = self.env['wa.employee.session'].search([
            ('employee_id', '=', self.id),
        ], limit=1)
        if session:
            return {
                'type': 'ir.actions.act_window',
                'res_model': 'wa.employee.session',
                'res_id': session.id,
                'view_mode': 'form',
            }
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'wa.employee.session',
            'view_mode': 'form',
            'context': {'default_employee_id': self.id},
        }
