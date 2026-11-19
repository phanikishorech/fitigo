from typing import Literal
from fastapi import APIRouter, Depends, Header, Query, Response
from sqlalchemy.orm import Session
from app.core.dependencies import require_role
from app.database.session import get_db
from app.models.auth import User
from app.schemas.gym_financial_settings import SettingsCreate
from app.services import gym_financial_settings as service

router = APIRouter(prefix='/financial-settings')
admin = require_role({'ADMIN', 'SUPER_ADMIN'})


@router.get('/gyms')
def gyms(response: Response, q: str = Query('', max_length=100), limit: int = Query(20, ge=1, le=100),
         offset: int = Query(0, ge=0), db: Session = Depends(get_db), user: User = Depends(admin)):
    response.headers['Cache-Control'] = 'no-store'
    return service.search_gyms(db, q, limit, offset)


@router.get('')
def read(response: Response, mode: Literal['test', 'live'], gym_id: int = Query(..., gt=0),
         limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0),
         db: Session = Depends(get_db), user: User = Depends(admin)):
    response.headers['Cache-Control'] = 'no-store'
    return service.configuration(db, mode, gym_id, limit, offset)


@router.post('')
def schedule(response: Response, payload: SettingsCreate,
             idempotency_key: str = Header(..., alias='Idempotency-Key', min_length=8, max_length=64, pattern=r'^[A-Za-z0-9_-]+$'),
             db: Session = Depends(get_db), user: User = Depends(admin)):
    response.headers['Cache-Control'] = 'no-store'
    return service.create(db, user.id, payload, idempotency_key)