from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.auth import User
from app.models.platform_membership import PlatformMembershipAudit, PlatformMembershipOffer, PlatformMembershipOrder, PlatformMembershipPlan
from app.schemas.platform_membership import ActiveOffer, PlatformCatalogResponse, PlatformOfferUpdate, PlatformOrderResponse, PlatformPlanCreate, PlatformPlanResponse, PlatformPlanUpdate
from app.schemas.platform_membership import AdminOfferConfiguration, AdminPlanDetail
from app.models.membership import UserMembership
from app.models.wallet import WalletAccount
from app.services.membership_wallet_service import activate, lock_customer, quote_key, wallet_enabled


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def aware(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def fail(code: str, status: int = 409):
    raise HTTPException(status_code=status, detail={"code": code})


def price_plan(plan: PlatformMembershipPlan, offer: PlatformMembershipOffer | None, now: datetime) -> PlatformPlanResponse:
    base = Decimal(plan.base_price).quantize(Decimal("0.01"))
    discount = Decimal("0.00")
    percentage = None
    promotion = None
    if offer and offer.is_active and aware(offer.starts_at) <= aware(now) < aware(offer.ends_at):
        amount = base * Decimal(offer.value) / Decimal(100) if offer.kind == "PERCENTAGE" else Decimal(offer.value)
        discount = min(base, amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
        if discount > 0:
            percentage = Decimal(offer.value) if offer.kind == "PERCENTAGE" else None
            promotion = ActiveOffer(id=offer.id, kind=offer.kind, title=offer.title, valid_until=aware(offer.ends_at))
    return PlatformPlanResponse(
        id=plan.id, code=plan.code, name=plan.name, description=plan.description,
        duration_value=plan.duration_value, duration_unit=plan.duration_unit,
        base_price=base, final_price=base - discount, discount_amount=discount,
        discount_percentage=percentage, currency=plan.currency, offer=promotion,
        benefits=plan.benefits, badge=plan.badge, display_order=plan.display_order,
        is_active=plan.is_active, version=plan.version, purchase_available=wallet_enabled() and plan.is_active,
        pause_rule={"allowed": bool(plan.pause_allowed), "max_pause_days": plan.max_pause_days or 0},
    )


class PlatformMembershipService:
    def __init__(self, db: Session):
        self.db = db

    def catalog(self, *, include_inactive: bool = False) -> PlatformCatalogResponse:
        query = select(PlatformMembershipPlan, PlatformMembershipOffer).outerjoin(
            PlatformMembershipOffer, PlatformMembershipOffer.plan_id == PlatformMembershipPlan.id
        ).order_by(PlatformMembershipPlan.display_order, PlatformMembershipPlan.id)
        if not include_inactive:
            query = query.where(PlatformMembershipPlan.is_active.is_(True))
        now = utcnow()
        return PlatformCatalogResponse(items=[price_plan(p, o, now) for p, o in self.db.execute(query)], server_time=now,
            checkout_available=wallet_enabled(), checkout_unavailable_reason=None if wallet_enabled() else "WALLET_MVP_DISABLED",
            payment_mode="WALLET_TEST_CREDIT" if wallet_enabled() else "DISABLED")

    def _plan(self, plan_id: int, *, lock: bool = False) -> PlatformMembershipPlan:
        query = select(PlatformMembershipPlan).where(PlatformMembershipPlan.id == plan_id)
        if lock:
            query = query.with_for_update().execution_options(populate_existing=True)
        plan = self.db.scalars(query).first()
        if not plan:
            fail("PLAN_UNAVAILABLE", 404)
        return plan

    def detail(self, plan_id: int, *, require_active: bool = True, lock: bool = False) -> PlatformPlanResponse:
        plan = self._plan(plan_id, lock=lock)
        if require_active and not plan.is_active:
            fail("PLAN_UNAVAILABLE", 404)
        offer_query = select(PlatformMembershipOffer).where(PlatformMembershipOffer.plan_id == plan_id)
        if lock:
            # Use a current read for both rows under MySQL REPEATABLE READ.
            offer_query = offer_query.with_for_update().execution_options(populate_existing=True)
        offer = self.db.scalars(offer_query).first()
        return price_plan(plan, offer, utcnow())

    def _audit(self, actor_id: int, plan_id: int, action: str, details: dict):
        self.db.add(PlatformMembershipAudit(actor_id=actor_id, plan_id=plan_id, action=action, details=details))

    def admin_detail(self, plan_id: int) -> AdminPlanDetail:
        plan = self._plan(plan_id)
        offer = self.db.scalars(select(PlatformMembershipOffer).where(PlatformMembershipOffer.plan_id == plan_id)).first()
        now = utcnow()
        configuration = None
        if offer:
            state = "DISABLED" if not offer.is_active else "EXPIRED" if aware(offer.ends_at) <= now else "SCHEDULED" if aware(offer.starts_at) > now else "ACTIVE"
            configuration = AdminOfferConfiguration(
                id=offer.id, kind=offer.kind, value=offer.value, title=offer.title,
                starts_at=aware(offer.starts_at), ends_at=aware(offer.ends_at), is_active=offer.is_active, state=state,
            )
        return AdminPlanDetail(plan=price_plan(plan, offer, now), offer_configuration=configuration, server_time=now)

    def save_plan(self, data: PlatformPlanCreate | PlatformPlanUpdate, *, actor_id: int, plan_id: int | None = None) -> PlatformPlanResponse:
        try:
            values = data.model_dump(exclude={"expected_version", "pause_rule"})
            # Old clients omitting policy must not wipe an existing configuration.
            if plan_id is None or "pause_rule" in data.model_fields_set:
                values.update(pause_allowed=data.pause_rule.allowed, max_pause_days=data.pause_rule.max_pause_days)
            if plan_id is None:
                plan = PlatformMembershipPlan(**values)
                self.db.add(plan)
                action = "PLAN_CREATED"
            else:
                plan = self._plan(plan_id, lock=True)
                if plan.version != data.expected_version:
                    fail("PLAN_VERSION_CHANGED")
                for key, value in values.items():
                    setattr(plan, key, value)
                plan.version += 1
                action = "PLAN_UPDATED"
            self.db.flush()
            self._audit(actor_id, plan.id, action, data.model_dump(mode="json"))
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            fail("PLAN_CODE_EXISTS")
        except Exception:
            self.db.rollback()
            raise
        return self.detail(plan.id, require_active=False)

    def save_offer(self, plan_id: int, data: PlatformOfferUpdate, *, actor_id: int) -> PlatformPlanResponse:
        try:
            plan = self._plan(plan_id, lock=True)
            if plan.version != data.expected_version:
                fail("PLAN_VERSION_CHANGED")
            offer = self.db.scalars(select(PlatformMembershipOffer).where(PlatformMembershipOffer.plan_id == plan_id)).first()
            values = data.model_dump(exclude={"expected_version"})
            for field in ("starts_at", "ends_at"):
                values[field] = aware(values[field]).replace(tzinfo=None)
            if offer is None:
                offer = PlatformMembershipOffer(plan_id=plan_id, **values)
                self.db.add(offer)
            else:
                for key, value in values.items():
                    setattr(offer, key, value)
            plan.version += 1
            self._audit(actor_id, plan_id, "OFFER_UPDATED", data.model_dump(mode="json"))
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        return self.detail(plan_id, require_active=False)

    def get_order(self, order_id: str, *, user_id: int) -> PlatformOrderResponse:
        order = self.db.scalars(select(PlatformMembershipOrder).where(
            PlatformMembershipOrder.id == order_id, PlatformMembershipOrder.user_id == user_id
        )).first()
        if not order:
            fail("ORDER_NOT_FOUND", 404)
        current = self.detail(order.plan_id, require_active=False)
        if not current.is_active:
            current = None
        snapshot = PlatformPlanResponse.model_validate(order.snapshot)
        membership = self.db.get(UserMembership, order.membership_id) if order.membership_id else None
        # A completed order is a receipt. Later catalog changes cannot rewrite it.
        if membership:
            current = snapshot
        account = self.db.scalars(select(WalletAccount).where(WalletAccount.user_id == user_id)).first()
        return PlatformOrderResponse(
            id=order.id, plan=snapshot, created_at=aware(order.created_at), current_plan=current,
            requires_review=not membership and (current is None or current.model_dump(mode="json") != snapshot.model_dump(mode="json")),
            status="PAID" if membership else "AWAITING_WALLET" if wallet_enabled() else "PAYMENT_DISABLED",
            payment_status="PAID" if membership else "NOT_STARTED", eligibility_status="VALIDATED" if membership else "NOT_EVALUATED",
            payment_available=wallet_enabled() and current is not None and membership is None,
            membership_id=membership.id if membership else None,
            quote_token=quote_key(current.model_dump(mode="json")) if current else None,
            payment_mode="WALLET_TEST_CREDIT" if wallet_enabled() else "DISABLED",
            wallet_balance=str(account.balance) if account else "0.00", wallet_currency=account.currency if account else (current.currency if current else snapshot.currency),
            wallet_transaction_id=membership.wallet_transaction_id if membership else None,
        )

    def pay_wallet(self, order_id: str, *, user_id: int, accepted_quote: str) -> PlatformOrderResponse:
        try:
            lock_customer(self.db, user_id)
            order = self.db.scalars(select(PlatformMembershipOrder).where(
                PlatformMembershipOrder.id == order_id, PlatformMembershipOrder.user_id == user_id
            ).with_for_update().execution_options(populate_existing=True)).first()
            if not order:
                fail("ORDER_NOT_FOUND", 404)
            if not order.membership_id:
                current = self.detail(order.plan_id, lock=True).model_dump(mode="json")
                if quote_key(current) != accepted_quote:
                    fail("MEMBERSHIP_PRICE_CHANGED")
                membership = activate(self.db, user_id=user_id, terms=current, checkout_key=f"multi:{order.id}")
                order.membership_id = membership.id
                order.snapshot = current
                order.status = "PAID"
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        return self.get_order(order_id, user_id=user_id)

    def create_order(self, *, user_id: int, plan_id: int, idempotency_key: str) -> PlatformOrderResponse:
        try:
            # Serialize this customer's order creation, including idempotent retries.
            user = self.db.scalars(select(User).where(User.id == user_id).with_for_update().execution_options(populate_existing=True)).first()
            if not user or user.status != "ACTIVE":
                fail("ACCOUNT_UNAVAILABLE", 403)
            previous = self.db.scalars(select(PlatformMembershipOrder).where(
                PlatformMembershipOrder.user_id == user_id, PlatformMembershipOrder.idempotency_key == idempotency_key
            )).first()
            if previous:
                if previous.plan_id != plan_id:
                    fail("IDEMPOTENCY_CONFLICT")
                order_id = previous.id
            else:
                plan = self.detail(plan_id, lock=True)
                order_id = str(uuid4())
                self.db.add(PlatformMembershipOrder(
                    id=order_id, user_id=user_id, plan_id=plan_id, idempotency_key=idempotency_key,
                    snapshot=plan.model_dump(mode="json"), status="PAYMENT_DISABLED",
                ))
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            previous = self.db.scalars(select(PlatformMembershipOrder).where(
                PlatformMembershipOrder.user_id == user_id, PlatformMembershipOrder.idempotency_key == idempotency_key
            )).first()
            if not previous or previous.plan_id != plan_id:
                fail("IDEMPOTENCY_CONFLICT")
            order_id = previous.id
        except Exception:
            self.db.rollback()
            raise
        return self.get_order(order_id, user_id=user_id)