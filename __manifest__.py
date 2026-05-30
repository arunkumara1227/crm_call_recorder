{
    'name': 'CRM Call Recorder',
    'version': '19.0.1.0.0',
    'category': 'Sales/CRM',
    'summary': 'Auto-link Android phone recordings to Odoo Contacts and Leads',
    'description': """
        CRM Call Recorder
        =================

        Receives phone call audio recordings uploaded from an Android
        companion app (the Android side watches the phone's built-in call
        recorder folder and uploads new files). On each upload:

        * Normalize the phone number
        * Match against res.partner (Contacts) and crm.lead (Leads)
        * Save the audio as an ir.attachment
        * Post a chatter note with an inline HTML5 audio player on the
          matched record
        * Unmatched recordings are kept in the Recordings list for manual
          linking

        Auth: single shared X-API-KEY header (set via System Parameter
        `crm_call_recorder.api_key`). Per-device keys are intentionally not
        used to keep the integration trivial.
    """,
    'author': 'Alphalize Technologies',
    'website': 'https://www.alphalize.com',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'mail',
        'contacts',
        'crm',
    ],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/ir_config_parameter.xml',
        'views/call_recording_views.xml',
        'views/api_key_views.xml',
        'views/menu.xml',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
}
