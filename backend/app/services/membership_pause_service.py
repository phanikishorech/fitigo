"""Pause rules and dates have one authority. UTC matches the access-day service."""
import hashlib
import json
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.auth import User
from app.models.membership import GymMembershipPlan, MembershipPause, UserMembership
from app.models.platform_membership import PlatformMembershipPlan
from app.schemas.membership_pause import PauseEligibility, PausePeriod, PausePolicy, PausePreview, PauseRequest


def utcnow():
    return datetime.now(timezone.utc)


def aware(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def paused_on(db: Session, membership_id: int, day):
    return db.scalar(select(MembershipPause.id).where(MembershipPause.membership_id == membership_id,
        MembershipPause.start_date <= day, MembershipPause.end_date >= day).limit(1)) is not None


def membership_status(db: Session, membership: UserMembership, now=None):
    now = aware(now or utcnow())
    if membership.status != "ACTIVE":
        return membership.status
    if aware(membership.end_at) <= now:
        return "EXPIRED"
    if membership.payment_status != "PAID" or aware(membership.start_at) > now:
        return "INACTIVE"
    return "PAUSED" if paused_on(db, membership.id, now.date()) else "ACTIVE"


def policy_for(db: Session, membership: UserMembership, lock=False):
    model = PlatformMembershipPlan if membership.membership_type == "MULTI_GYM" else GymMembershipPlan
    key = membership.platform_plan_id if model is PlatformMembershipPlan else membership.plan_id
    query = select(model).where(model.id == key)
    if model is GymMembershipPlan:
        query = query.where(model.gym_id == membership.gym_id)
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    plan = db.scalars(query).first()
    return PausePolicy(allowed=bool(plan and plan.pause_allowed), max_pause_days=plan.max_pause_days if plan and plan.pause_allowed else 0)


def fail(code, http=409):
    raise HTTPException(status_code=http, detail={"code": code})


class MembershipPauseService:
    def __init__(self, db: Session):
        self.db = db

    def membership(self, user_id, membership_id, lock=False):
        query = select(UserMembership).where(UserMembership.id == membership_id, UserMembership.user_id == user_id)
        if lock:
            query = query.with_for_update().execution_options(populate_existing=True)
        membership = self.db.scalars(query).first()
        if not membership:
            fail("MEMBERSHIP_NOT_FOUND", 404)
        return membership

    def eligibility(self, membership, now=None, lock=False):
        now = aware(now or utcnow())
        policy = policy_for(self.db, membership, lock)
        query = select(MembershipPause).where(MembershipPause.membership_id == membership.id).order_by(MembershipPause.start_date)
        if lock:
            query = query.with_for_update().execution_options(populate_existing=True)
        periods = list(self.db.scalars(query))
        history = [PausePeriod(id=p.id, start_date=p.start_date, end_date=p.end_date,
            resumes_on=p.end_date + timedelta(days=1), days=p.days,
            status="SCHEDULED" if p.start_date > now.date() else "COMPLETED" if p.end_date < now.date() else "PAUSED",
            previous_end_at=aware(p.previous_end_at), new_end_at=aware(p.new_end_at)) for p in periods]
        current = next((p for p in history if p.status == "PAUSED"), None)
        used = sum(p.days for p in periods)
        remaining = max(0, policy.max_pause_days - used)
        status = membership_status(self.db, membership, now)
        earliest = max(now.date() + timedelta(days=1), aware(membership.start_at).date())
        # Only whole UTC days within the CURRENT validity can be paused.
        last = aware(membership.end_at).date() - timedelta(days=1)
        while earliest <= last and any(p.start_date <= earliest <= p.end_date for p in periods):
            earliest = next(p.end_date + timedelta(days=1) for p in periods if p.start_date <= earliest <= p.end_date)
        reason = ("MEMBERSHIP_ALREADY_PAUSED" if status == "PAUSED" else "MEMBERSHIP_EXPIRED" if status == "EXPIRED"
                  else "MEMBERSHIP_INACTIVE" if status != "ACTIVE" else "PAUSE_NOT_ALLOWED" if not policy.allowed
                  else "PAUSE_LIMIT_EXCEEDED" if remaining == 0 else "INVALID_PAUSE_DATE" if earliest > last else None)
        return PauseEligibility(membership_id=membership.id, membership_status=status, pause_allowed=policy.allowed,
            can_pause=reason is None, max_pause_days=policy.max_pause_days, pause_days_used=used, pause_days_remaining=remaining,
            currently_paused=status == "PAUSED", eligible_from=earliest if earliest <= last else None,
            eligible_until=last if earliest <= last else None,
            original_end_at=aware(membership.original_end_at or membership.end_at), current_end_at=aware(membership.end_at),
            current_pause=current, history=history, reason_code=reason)

    def preview(self, membership, request: PauseRequest, now=None, lock=False):
        eligibility = self.eligibility(membership, now, lock)
        if not eligibility.can_pause:
            fail(eligibility.reason_code)
        if request.days > eligibility.pause_days_remaining:
            fail("PAUSE_LIMIT_EXCEEDED")
        try:
            end = request.start_date + timedelta(days=request.days - 1)
        except OverflowError:
            fail("INVALID_PAUSE_DATE")
        if request.start_date < eligibility.eligible_from or end > eligibility.eligible_until:
            # Report overlap even when the earliest unreserved date moved forward.
            if any(p.start_date <= end and p.end_date >= request.start_date for p in eligibility.history):
                fail("PAUSE_OVERLAP")
            fail("INVALID_PAUSE_DATE")
        if any(p.start_date <= end and p.end_date >= request.start_date for p in eligibility.history):
            fail("PAUSE_OVERLAP")
        try:
            new_end = eligibility.current_end_at + timedelta(days=request.days)
        except OverflowError:
            fail("INVALID_PAUSE_DATE")
        values = dict(membership_id=membership.id, start_date=request.start_date, end_date=end,
            resumes_on=end + timedelta(days=1), days=request.days, current_end_at=eligibility.current_end_at,
            new_end_at=new_end, pause_days_remaining_after=eligibility.pause_days_remaining-request.days)
        fingerprint = {**values, "policy": policy_for(self.db, membership).model_dump(), "user_id": membership.user_id}
        token = hashlib.sha256(json.dumps(fingerprint, sort_keys=True, default=str).encode()).hexdigest()
        return PausePreview(**values, preview_token=token)

    def create(self, user_id, membership_id, request, key):
        try:
            # Same customer -> membership lock ordering as wallet purchases and QR validation.
            user = self.db.scalars(select(User).where(User.id == user_id).with_for_update().execution_options(populate_existing=True)).first()
            if not user or user.status != "ACTIVE":
                fail("ACCOUNT_UNAVAILABLE", 403)
            membership = self.membership(user_id, membership_id, True)
            previous = self.db.scalars(select(MembershipPause).where(MembershipPause.membership_id == membership_id,
                MembershipPause.request_key == key).with_for_update()).first()
            if previous:
                if previous.start_date != request.start_date or previous.days != request.days:
                    fail("IDEMPOTENCY_CONFLICT")
                result = self.eligibility(membership, lock=True)
                self.db.commit()
                return result
            preview = self.preview(membership, request, lock=True)
            if preview.preview_token != request.accepted_preview:
                fail("PAUSE_PREVIEW_CHANGED")
            if membership.original_end_at is None:
                membership.original_end_at = membership.end_at
            record = MembershipPause(membership_id=membership.id, request_key=key, start_date=preview.start_date,
                end_date=preview.end_date, days=preview.days, previous_end_at=membership.end_at,
                new_end_at=preview.new_end_at.replace(tzinfo=None))
            self.db.add(record)
            membership.end_at = record.new_end_at
            self.db.flush()
            result = self.eligibility(membership, lock=True)
            self.db.commit()
            return result
        except Exception:
            self.db.rollback()
            raise