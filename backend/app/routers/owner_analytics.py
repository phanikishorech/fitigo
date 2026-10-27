from datetime import date
from typing import Literal
from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session
from app.core.dependencies import require_role
from app.core.roles import ROLE_GYM_OWNER
from app.database.session import get_db
from app.models.auth import User
from app.services.owner_analytics_service import OwnerAnalyticsService


def no_store(response: Response):
    response.headers['Cache-Control'] = 'no-store'


router = APIRouter(prefix='/analytics', dependencies=[Depends(no_store)])
owner = require_role({ROLE_GYM_OWNER})


def filters(gym_id: int | None = Query(None, gt=0), date_from: date | None = None, date_to: date | None = None):
    return dict(gym_id=gym_id, date_from=date_from, date_to=date_to)


def pagination(limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0)):
    return dict(limit=limit, offset=offset)


@router.get('')
def overview(scope: dict = Depends(filters), db: Session = Depends(get_db), user: User = Depends(owner)):
    return OwnerAnalyticsService(db).overview(user.id, **scope)


@router.get('/bookings')
def bookings(category: Literal['upcoming', 'attended', 'cancelled', 'no_show', 'pending_payment', 'expired', 'unresolved'] | None = None,
             scope: dict = Depends(filters), page: dict = Depends(pagination), db: Session = Depends(get_db), user: User = Depends(owner)):
    return OwnerAnalyticsService(db).bookings(user.id, **scope, **page, category=category)


@router.get('/transactions')
def transactions(category: Literal['single_gym_membership', 'individual_booking'] | None = None,
                 payment_status: Literal['PAID', 'INITIATED', 'PENDING', 'FAILED', 'REFUNDED', 'PARTIALLY_REFUNDED', 'REVIEW_REQUIRED'] | None = None,
                 scope: dict = Depends(filters), page: dict = Depends(pagination), db: Session = Depends(get_db), user: User = Depends(owner)):
    return OwnerAnalyticsService(db).transactions(user.id, **scope, **page, category=category, payment_status=payment_status)


@router.get('/attendance')
def attendance(scope: dict = Depends(filters), page: dict = Depends(pagination), db: Session = Depends(get_db), user: User = Depends(owner)):
    return OwnerAnalyticsService(db).attendance_page(user.id, **scope, **page)