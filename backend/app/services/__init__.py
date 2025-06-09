"""
Services package for ClassRent

Contiene tutti i servizi business logic dell'applicazione.
"""

from .auth_service import verify_password, get_password_hash, create_access_token, verify_token
from .booking_service import booking_service

# ✅ EMAIL: Solo il servizio ClassRent corretto
from .classrent_email_service import classrent_email_service as email_service

# ✅ CALENDARIO: Solo MongoDB (rimosso Google Calendar)
from .database_calendar_service import database_calendar_service as calendar_service

# ✅ AI: Solo il servizio OpenAI Agent (rimosso ai_service legacy)
from .openai_agent_service import ai_agent_service

__all__ = [
    # Auth service
    "verify_password",
    "get_password_hash", 
    "create_access_token",
    "verify_token",
    
    # Service instances
    "booking_service",
    "email_service",         # ✅ ClassRent email
    "calendar_service",      # ✅ MongoDB calendar
    "ai_agent_service",      # ✅ Solo AI Agent (no legacy)
]