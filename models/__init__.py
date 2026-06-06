# Bundled WhatsApp tracker BASE models — must load first so any existing
# crm_call_recorder code that inherits them (e.g. employee_session_extension)
# finds them in the registry.
from . import wa_voice_config
from . import wa_employee_session
from . import wa_communication_log
from . import wa_conversation
from . import wa_keyword_alert
from . import wa_message_tone
from . import wa_quality_score
from . import wa_response_time
from . import wa_tone_report
from . import wa_whatsapp_message_inherit
from . import wa_hr_employee_inherit
from . import wa_product_template_inherit

# Existing crm_call_recorder native models
from . import api_key
from . import voice_config
from . import tone_keyword
from . import call_tone
from . import tone_report
from . import call_recording
from . import hr_employee
from . import employee_session_extension
from . import phone_summary
