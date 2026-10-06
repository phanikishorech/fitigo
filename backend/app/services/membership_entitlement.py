"""Shared read-only membership scope/eligibility for discovery, profile and check-in."""
from datetime import datetime, timezone
from sqlalchemy import select, or_
from sqlalchemy.orm import Session
from app.models.membership import UserMembership, GymMembershipPlan
from app.models.gym import Gym
from app.models.membership import MembershipPause


def active_memberships(db: Session, user_id: int, at: datetime, *, lock: bool = False, include_paused: bool = False) -> list[UserMembership]:
    now = at.astimezone(timezone.utc).replace(tzinfo=None) if at.tzinfo else at
    query = select(UserMembership).where(
        UserMembership.user_id == user_id, UserMembership.status == "ACTIVE",
        UserMembership.payment_status == "PAID", UserMembership.start_at <= now, UserMembership.end_at > now,
    ).order_by(UserMembership.end_at.desc(), UserMembership.id.desc())
    if not include_paused:
        query = query.where(~select(MembershipPause.id).where(MembershipPause.membership_id == UserMembership.id,
            MembershipPause.start_date <= now.date(), MembershipPause.end_date >= now.date()).exists())
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    return list(db.scalars(query))


def covers(memberships: list[UserMembership], gym: Gym) -> bool:
    if gym.status != "APPROVED" or not gym.is_active:
        return False
    return any((m.membership_type == "MULTI_GYM" and gym.multi_gym_enabled) or
               (m.membership_type == "SINGLE_GYM" and m.gym_id == gym.id) for m in memberships)


def included_ids(db: Session, user_id: int, at: datetime) -> set[int]:
    memberships = active_memberships(db, user_id, at)
    if not memberships:
        return set()
    single_ids = [m.gym_id for m in memberships if m.membership_type == "SINGLE_GYM" and m.gym_id is not None]
    eligibility = Gym.id.in_(single_ids)
    if any(m.membership_type == "MULTI_GYM" for m in memberships):
        eligibility = or_(eligibility, Gym.multi_gym_enabled.is_(True))
    return set(db.scalars(select(Gym.id).where(Gym.status == "APPROVED", Gym.is_active.is_(True), eligibility)))


def membership_name(db: Session, membership: UserMembership) -> str | None:
    if membership.terms_snapshot:
        return membership.terms_snapshot.get("name")
    plan = db.get(GymMembershipPlan, membership.plan_id) if membership.plan_id else None
    return plan.name if plan else None


def scope(memberships: list[UserMembership]) -> str | None:
    if not memberships:
        return None
    return "MULTI_GYM" if any(m.membership_type == "MULTI_GYM" for m in memberships) or len({m.gym_id for m in memberships}) > 1 else "SINGLE_GYM"