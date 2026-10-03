from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Header, Response
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
from app.services.membership_wallet_service import single_terms, quote_key, wallet_enabled, buy_single
from app.models.wallet import WalletAccount
from sqlalchemy import select


router = APIRouter(prefix="/memberships")


@router.get("/gyms/{gym_id}/plans/{plan_id}/wallet-quote")
def wallet_quote(gym_id: int, plan_id: int, response: Response, db: Session = Depends(get_db), current_user: User = Depends(require_role({ROLE_CUSTOMER}))):
    response.headers["Cache-Control"] = "no-store"
    terms = single_terms(db, gym_id, plan_id)
    wallet = db.scalars(select(WalletAccount).where(WalletAccount.user_id == current_user.id)).first()
    return {"plan": terms, "quote_token": quote_key(terms), "payment_available": wallet_enabled(),
            "wallet_balance": str(wallet.balance) if wallet else "0.00", "wallet_currency": wallet.currency if wallet else terms["currency"],
            "payment_mode": "WALLET_TEST_CREDIT" if wallet_enabled() else "DISABLED"}


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
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=8, max_length=64, pattern=r"^[A-Za-z0-9_-]+$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role({ROLE_CUSTOMER})),
):
    svc = MembershipService(db)
    m = buy_single(db, user_id=current_user.id, gym_id=gym_id, plan_id=payload.plan_id, accepted_quote=payload.accepted_quote, key=idempotency_key)
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
        membership_type=m.membership_type, platform_plan_id=m.platform_plan_id, terms_snapshot=m.terms_snapshot, wallet_transaction_id=m.wallet_transaction_id,
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
            membership_type=m.membership_type, platform_plan_id=m.platform_plan_id, terms_snapshot=m.terms_snapshot, wallet_transaction_id=m.wallet_transaction_id,
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
        membership_type=m.membership_type, platform_plan_id=m.platform_plan_id, terms_snapshot=m.terms_snapshot, wallet_transaction_id=m.wallet_transaction_id,
        payment_status=m.payment_status,
        external_ref=m.external_ref,
        created_at=m.created_at,
        updated_at=m.updated_at,
    )
