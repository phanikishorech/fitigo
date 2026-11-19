from typing import Literal
from fastapi import APIRouter, Depends, Header, Query, Response
from sqlalchemy.orm import Session
from app.core.dependencies import require_role
from app.database.session import get_db
from app.models.auth import User
from app.schemas.financial_agreement import AgreementCreate, AgreementTerms
from app.services import financial_agreements

router = APIRouter(prefix='/financial-agreements')
admin = require_role({'ADMIN', 'SUPER_ADMIN'})


@router.post('/policy-validation')
def validate_policy(response: Response, terms: AgreementTerms, user: User = Depends(admin)):
    """Validation only: no save, no pin, no transaction-source access."""
    from app.services.accounting_policy import policy_readiness
    response.headers['Cache-Control'] = 'no-store'
    return policy_readiness(terms.model_dump(mode='json'))


@router.get('')
def read(response: Response, mode: Literal['test', 'live'], gym_id: int | None = Query(None, gt=0),
         limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0),
         db: Session = Depends(get_db), user: User = Depends(admin)):
    response.headers['Cache-Control'] = 'no-store'
    return financial_agreements.configuration(db, mode, gym_id, limit, offset)


@router.post('')
def schedule(response: Response, payload: AgreementCreate,
             idempotency_key: str = Header(..., alias='Idempotency-Key', min_length=8, max_length=64, pattern=r'^[A-Za-z0-9_-]+$'),
             db: Session = Depends(get_db), user: User = Depends(admin)):
    response.headers['Cache-Control'] = 'no-store'
    return financial_agreements.create(db, user.id, payload, idempotency_key)