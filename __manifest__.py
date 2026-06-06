{
    'name': 'CRM Call Recorder',
    'version': '19.0.9.2.0',
    'category': 'Sales/CRM',
    'summary': 'Phone call recording capture + WhatsApp employee tracking',
    'description': """
        CRM Call Recorder + CRM WhatsApp
        ================================

        Two complementary employee-communication surfaces in one module:

        1. **Call Recorder** — receives phone call audio recordings uploaded
           from an Android companion app, auto-matches phone numbers to
           res.partner / crm.lead, transcribes, scores tone.
        2. **CRM WhatsApp** (ported from whatsapp_employee_tracker) — monitors
           employee WhatsApp via neonize, logs every message, runs keyword
           alerts, computes daily quality scores, analyses tone, exposes a
           chat-style live view. Auto-reply bot is intentionally NOT included.

        Together: a unified employee-communication dashboard linking calls and
        WhatsApp activity per device / employee.
    """,
    'author': 'Alphalize Technologies',
    'website': 'https://www.alphalize.com',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'mail',
        'contacts',
        'crm',
        'hr',
        'product',
        'whatsapp_neonize',
    ],
    'data': [
        'security/security.xml',
        'security/wa_tracker_security.xml',
        'security/ir.model.access.csv',
        'data/ir_config_parameter.xml',
        'data/ir_cron.xml',
        'data/tone_keywords.xml',
        'data/wa_alert_keywords_data.xml',
        'data/wa_ir_cron.xml',
        'views/call_recording_views.xml',
        'views/phone_summary_views.xml',
        'views/api_key_views.xml',
        'views/voice_config_views.xml',
        'views/hr_employee_views.xml',
        'views/tone_keyword_views.xml',
        'views/call_tone_views.xml',
        'views/tone_report_views.xml',
        'views/web_templates.xml',
        # Bundled CRM WhatsApp (formerly whatsapp_employee_tracker)
        'views/wa/employee_session_views.xml',
        'views/wa/communication_log_views.xml',
        'views/wa/keyword_alert_views.xml',
        'views/wa/conversation_views.xml',
        'views/wa/chat_views.xml',
        'views/wa/quality_score_views.xml',
        'views/wa/message_tone_views.xml',
        'views/wa/dashboard_views.xml',
        'views/wa/voice_test_views.xml',
        'views/wa/voice_config_views.xml',
        'views/wa/response_time_views.xml',
        'views/wa/tone_report_views.xml',
        'views/wa/product_template_views.xml',
        'views/wa/menu.xml',
        # Cross-module inherit views (depend on bundled WA views being loaded)
        'views/wa_employee_session_kanban_inherit.xml',
        'views/wa_employee_session_form_inherit.xml',
        'views/menu.xml',
    ],
    'assets': {
        'web.assets_backend': [
            # Bundled CRM WhatsApp chat split-view BASE — must load first
            # so the patch below finds the registered action + template.
            'crm_call_recorder/static/src/wa/css/wa_chat_style.css',
            'crm_call_recorder/static/src/wa/xml/chat_view.xml',
            'crm_call_recorder/static/src/wa/js/chat_view.js',
            # crm_call_recorder PATCH that injects the call-recordings panel
            # into the chat view above.
            'crm_call_recorder/static/src/css/wa_chat_recording_panel.css',
            'crm_call_recorder/static/src/xml/wa_chat_recording_panel.xml',
            'crm_call_recorder/static/src/js/wa_chat_recording_panel.js',
        ],
    },
    'installable': True,
    'application': True,
    'auto_install': False,
}
