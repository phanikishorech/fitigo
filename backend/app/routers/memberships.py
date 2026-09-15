from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.dependencies import require_role
from app.core.roles import ROLE_CUSTOMER, ROLE_GYM_OWNER
from app.database.session import get_db
from app.models.auth import User
from app.schemas.membership import (
    MembershipPlanCreateRequest,
    MembershipPlanResponse,
    PurchaseMembershipRequest,
    UserMembershipResponse,
)
from app.services.membership_service import MembershipService


router = APIRouter(prefix="/memberships")


@router.post("/gyms/{gym_id}/plans", response_model=MembershipPlanResponse)
def create_plan(
    gym_id: int,
    payload: MembershipPlanCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role({ROLE_GYM_OWNER})),
):
    svc = MembershipService(db)
    plan = svc.create_plan(owner_user_id=current_user.id, gym_id=gym_id, data=payload.model_dump())
    return MembershipPlanResponse(
        id=plan.id,
        gym_id=plan.gym_id,
        name=plan.name,
        description=plan.description,
        duration_days=plan.duration_days,
        price=str(plan.price),
        currency=plan.currency,
        is_active=plan.is_active,
        created_at=plan.created_at,
        updated_at=plan.updated_at,
    )


@router.get("/gyms/{gym_id}/plans", response_model=list[MembershipPlanResponse])
def list_public_plans(
    gym_id: int,
    db: Session = Depends(get_db),
):
    svc = MembershipService(db)
    plans = svc.list_public_plans(gym_id=gym_id)
    return [
        MembershipPlanResponse(
            id=p.id,
            gym_id=p.gym_id,
            name=p.name,
            description=p.description,
            duration_days=p.duration_days,
            price=str(p.price),
            currency=p.currency,
            is_active=p.is_active,
            created_at=p.created_at,
            updated_at=p.updated_at,
        )
        for p in plans
    ]


@router.post("/gyms/{gym_id}/purchase", response_model=UserMembershipResponse)
def purchase_membership(
    gym_id: int,
    payload: PurchaseMembershipRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role({ROLE_CUSTOMER})),
):
    svc = MembershipService(db)
    m = svc.purchase_membership(user_id=current_user.id, gym_id=gym_id, plan_id=payload.plan_id)
    return UserMembershipResponse(
        id=m.id,
        user_id=m.user_id,
        gym_id=m.gym_id,
        plan_id=m.plan_id,
        status=m.status,
        start_at=m.start_at,
        end_at=m.end_at,
        cancelled_at=m.cancelled_at,
        paid_amount=str(m.paid_amount),
        currency=m.currency,
        payment_provider=m.payment_provider,
        payment_status=m.payment_status,
        external_ref=m.external_ref,
        created_at=m.created_at,
        updated_at=m.updated_at,
    )


@router.get("/me", response_model=list[UserMembershipResponse])
def list_my_memberships(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role({ROLE_CUSTOMER})),
):
    svc = MembershipService(db)
    items = svc.list_my_memberships(user_id=current_user.id)
    return [
        UserMembershipResponse(
            id=m.id,
            user_id=m.user_id,
            gym_id=m.gym_id,
            plan_id=m.plan_id,
            status=m.status,
            start_at=m.start_at,
            end_at=m.end_at,
            cancelled_at=m.cancelled_at,
            paid_amount=str(m.paid_amount),
            currency=m.currency,
            payment_provider=m.payment_provider,
            payment_status=m.payment_status,
            external_ref=m.external_ref,
            created_at=m.created_at,
            updated_at=m.updated_at,
        )
        for m in items
    ]


@router.post("/me/{membership_id}/cancel", response_model=UserMembershipResponse)
def cancel_membership(
    membership_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role({ROLE_CUSTOMER})),
):
    svc = MembershipService(db)
    m = svc.cancel_membership(user_id=current_user.id, membership_id=membership_id)
    return UserMembershipResponse(
        id=m.id,
        user_id=m.user_id,
        gym_id=m.gym_id,
        plan_id=m.plan_id,
        status=m.status,
        start_at=m.start_at,
        end_at=m.end_at,
        cancelled_at=m.cancelled_at,
        paid_amount=str(m.paid_amount),
        currency=m.currency,
        payment_provider=m.payment_provider,
        payment_status=m.payment_status,
        external_ref=m.external_ref,
        created_at=m.created_at,
        updated_at=m.updated_at,
    )
