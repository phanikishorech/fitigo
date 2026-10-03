from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Response
from sqlalchemy.orm import Session

from app.core.dependencies import require_role
from app.core.roles import ROLE_ADMIN, ROLE_CUSTOMER, ROLE_SUPER_ADMIN
from app.database.session import get_db
from app.models.auth import User
from app.schemas.platform_membership import PlatformCatalogResponse, PlatformOfferUpdate, PlatformOrderCreate, PlatformOrderResponse, PlatformPlanCreate, PlatformPlanResponse, PlatformPlanUpdate
from app.services.platform_membership_service import PlatformMembershipService, fail
from app.schemas.platform_membership import AdminPlanDetail
from app.schemas.platform_membership import WalletOrderPayment, PartnerUpdate
from app.models.gym import Gym
from sqlalchemy import select


router = APIRouter()
customer_access = require_role({ROLE_CUSTOMER})
admin_access = require_role({ROLE_ADMIN, ROLE_SUPER_ADMIN})


def no_store(response: Response):
    # Prices, offer state and customer orders must not be reused by shared caches.
    response.headers["Cache-Control"] = "no-store"


@router.get("/memberships/plans", response_model=PlatformCatalogResponse, dependencies=[Depends(no_store)])
def catalog(
    membership_type: Literal["MULTI_GYM"] = Query(default="MULTI_GYM"),
    db: Session = Depends(get_db),
):
    return PlatformMembershipService(db).catalog()


@router.get("/memberships/plans/{plan_id}", response_model=PlatformPlanResponse, dependencies=[Depends(no_store)])
def plan_detail(plan_id: int, db: Session = Depends(get_db)):
    return PlatformMembershipService(db).detail(plan_id)


@router.post("/memberships/orders", response_model=PlatformOrderResponse, dependencies=[Depends(no_store)])
def create_order(
    payload: PlatformOrderCreate,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")],
    db: Session = Depends(get_db),
    user: User = Depends(customer_access),
):
    return PlatformMembershipService(db).create_order(user_id=user.id, plan_id=payload.plan_id, idempotency_key=idempotency_key)


@router.get("/memberships/orders/{order_id}", response_model=PlatformOrderResponse, dependencies=[Depends(no_store)])
def get_order(order_id: UUID, db: Session = Depends(get_db), user: User = Depends(customer_access)):
    return PlatformMembershipService(db).get_order(str(order_id), user_id=user.id)


@router.post("/memberships/orders/{order_id}/payment-session", dependencies=[Depends(no_store)])
def payment_disabled(order_id: UUID, db: Session = Depends(get_db), user: User = Depends(customer_access)):
    # Deliberately no configurable bypass, wallet charge, dummy success or activation.
    PlatformMembershipService(db).get_order(str(order_id), user_id=user.id)
    fail("PAYMENT_NOT_CONFIGURED", 409)


@router.post("/memberships/orders/{order_id}/pay-wallet", response_model=PlatformOrderResponse, dependencies=[Depends(no_store)])
def pay_wallet(order_id: UUID, payload: WalletOrderPayment, db: Session = Depends(get_db), user: User = Depends(customer_access)):
    return PlatformMembershipService(db).pay_wallet(str(order_id), user_id=user.id, accepted_quote=payload.accepted_quote)


@router.get("/admin/gyms/{gym_id}/multi-gym-participation", dependencies=[Depends(no_store)])
def partner_status(gym_id: int, db: Session = Depends(get_db), user: User = Depends(admin_access)):
    gym = db.get(Gym, gym_id)
    if not gym:
        fail("GYM_NOT_FOUND", 404)
    return {"gym_id": gym.id, "enabled": gym.multi_gym_enabled}


@router.put("/admin/gyms/{gym_id}/multi-gym-participation")
def partner_update(gym_id: int, payload: PartnerUpdate, db: Session = Depends(get_db), user: User = Depends(admin_access)):
    gym = db.scalars(select(Gym).where(Gym.id == gym_id).with_for_update()).first()
    if not gym:
        fail("GYM_NOT_FOUND", 404)
    if payload.enabled and (gym.status != "APPROVED" or not gym.is_active):
        fail("GYM_NOT_ELIGIBLE")
    gym.multi_gym_enabled = payload.enabled
    db.commit()
    return {"gym_id": gym.id, "enabled": gym.multi_gym_enabled}


@router.get("/admin/membership-plans", response_model=PlatformCatalogResponse, dependencies=[Depends(no_store)])
def admin_catalog(db: Session = Depends(get_db), user: User = Depends(admin_access)):
    return PlatformMembershipService(db).catalog(include_inactive=True)


@router.post("/admin/membership-plans", response_model=PlatformPlanResponse, status_code=201)
def create_plan(payload: PlatformPlanCreate, db: Session = Depends(get_db), user: User = Depends(admin_access)):
    return PlatformMembershipService(db).save_plan(payload, actor_id=user.id)


@router.get("/admin/membership-plans/{plan_id}", response_model=AdminPlanDetail, dependencies=[Depends(no_store)])
def admin_plan_detail(plan_id: int, db: Session = Depends(get_db), user: User = Depends(admin_access)):
    return PlatformMembershipService(db).admin_detail(plan_id)


@router.put("/admin/membership-plans/{plan_id}", response_model=PlatformPlanResponse)
def update_plan(plan_id: int, payload: PlatformPlanUpdate, db: Session = Depends(get_db), user: User = Depends(admin_access)):
    return PlatformMembershipService(db).save_plan(payload, actor_id=user.id, plan_id=plan_id)


@router.put("/admin/membership-plans/{plan_id}/offer", response_model=PlatformPlanResponse)
def update_offer(plan_id: int, payload: PlatformOfferUpdate, db: Session = Depends(get_db), user: User = Depends(admin_access)):
    return PlatformMembershipService(db).save_offer(plan_id, payload, actor_id=user.id)