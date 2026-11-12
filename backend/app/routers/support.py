from fastapi import APIRouter
from pydantic import TypeAdapter, EmailStr, ValidationError
from app.core.config import settings

router=APIRouter()


@router.get('/support')
def support():
    address=None
    if settings.support_email:
        try:address=str(TypeAdapter(EmailStr).validate_python(settings.support_email))
        except ValidationError:pass
    return {'email':address,'configured':bool(address),'ticketing_available':settings.support_workflows_enabled and settings.operational_workflows_enabled,
            'message':'Contact the configured support address.' if address else 'No support address is configured. Use your existing administrator contact.'}