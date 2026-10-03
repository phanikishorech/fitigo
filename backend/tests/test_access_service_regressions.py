from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from pydantic import TypeAdapter, ValidationError
from sqlalchemy import Integer, MetaData, create_engine, func, select
from sqlalchemy.orm import Session

from app.database.base import Base
from app.models.access import AccessPauseDay, AccessQrToken, Checkin, CustomerDailyAccess
from app.models.auth import User
from app.models.gym import Gym
from app.models.membership import GymMembershipPlan, MembershipDailyAccess, UserMembership
from app.models.platform_membership import PlatformMembershipPlan
from app.models.wallet import WalletAccount, WalletTransaction
from app.services import access_service
from app.services.access_service import AccessService, _utc
from app.schemas.access import TodayAccessResponse


NOW = datetime(2026, 9, 16, 12, tzinfo=timezone.utc)


@pytest.fixture
def access(monkeypatch):
    # Clone only the needed tables; SQLite requires INTEGER autoincrement PKs.
    # Production metadata and the configured database remain untouched.
    engine = create_engine("sqlite://")
    metadata = MetaData()
    for name in (
        "users", "gyms", "gym_membership_plans", "user_memberships",
        "customer_daily_accesses", "access_qr_tokens", "checkins",
        "access_pause_days", "gym_operating_hours", "gym_special_hours",
        "membership_daily_accesses",
        "platform_membership_plans", "wallet_accounts", "wallet_transactions",
    ):
        table = Base.metadata.tables[name].to_metadata(metadata)
        table.c.id.type = Integer()
    metadata.create_all(engine)
    monkeypatch.setattr(access_service, "utcnow", lambda: NOW)
    monkeypatch.setattr(access_service, "utc_today", lambda: NOW.date())
    with Session(engine) as db:
        user = User(email="member@example.com", password_hash="unused", status="ACTIVE")
        db.add(user)
        db.flush()
        gym = Gym(owner_user_id=user.id, name="Test Gym", status="APPROVED", is_active=True)
        db.add(gym)
        db.flush()
        plan = GymMembershipPlan(gym_id=gym.id, name="Monthly", duration_days=30, price=999)
        db.add(plan)
        db.flush()
        membership = UserMembership(
            user_id=user.id, gym_id=gym.id, plan_id=plan.id, status="ACTIVE",
            start_at=NOW - timedelta(days=5), end_at=NOW + timedelta(days=25),
            paid_amount=999, payment_status="PAID",
        )
        db.add(membership)
        db.commit()
        yield AccessService(db), user, gym, membership
    engine.dispose()


def test_rotated_tokens_share_one_daily_use(access):
    service, user, gym, _ = access
    first = service.get_today_access(user_id=user.id)
    second = service.get_today_access(user_id=user.id)
    assert first["qr_token"] != second["qr_token"]
    assert first["expires_at"].utcoffset() == timedelta(0)
    assert service.validate_checkin(gym_id=gym.id, qr_token=first["qr_token"])["success"]
    with pytest.raises(HTTPException) as error:
        service.validate_checkin(gym_id=gym.id, qr_token=second["qr_token"])
    assert error.value.status_code == 409
    assert service.db.scalar(select(func.count(Checkin.id))) == 1
    assert service.get_today_access(user_id=user.id)["status"] == "USED"


@pytest.mark.parametrize("field,value", [("status", "CANCELLED"), ("payment_status", "REFUNDED")])
def test_membership_changes_block_existing_token(access, field, value):
    service, user, gym, membership = access
    qr = service.get_today_access(user_id=user.id)["qr_token"]
    setattr(membership, field, value)
    service.db.commit()
    with pytest.raises(HTTPException) as error:
        service.validate_checkin(gym_id=gym.id, qr_token=qr)
    assert error.value.status_code == 403
    assert service.db.scalar(select(func.count(Checkin.id))) == 0


@pytest.mark.parametrize("customer_status", ["SUSPENDED", "INACTIVE"])
def test_inactive_customer_cannot_use_previously_minted_token(access, customer_status):
    service, user, gym, _ = access
    qr = service.get_today_access(user_id=user.id)["qr_token"]
    user.status = customer_status
    service.db.commit()
    assert service.get_today_access(user_id=user.id)["status"] == "NO_ACCESS"
    with pytest.raises(HTTPException) as error:
        service.validate_checkin(gym_id=gym.id, qr_token=qr)
    assert error.value.status_code == 403


def test_pause_after_mint_blocks_scan(access):
    service, user, gym, _ = access
    qr = service.get_today_access(user_id=user.id)["qr_token"]
    service.db.add(AccessPauseDay(user_id=user.id, access_date=NOW.date()))
    service.db.commit()
    with pytest.raises(HTTPException) as error:
        service.validate_checkin(gym_id=gym.id, qr_token=qr)
    assert error.value.status_code == 403
    days = {str(day["date"]): day for day in service.calendar_month(user_id=user.id, year=2026, month=9)["days"]}
    assert days["2026-09-16"]["qr_status"] == "PAUSED"
    assert days["2026-09-15"]["status"] == "NO_VISIT"


def test_used_access_survives_membership_key_change(access):
    service, user, gym, membership = access
    qr = service.get_today_access(user_id=user.id)["qr_token"]
    # Create another entitlement before the first scan, as can happen on renewal.
    other = service._get_or_create_daily_access(
        user_id=user.id, membership_id=membership.id, access_type="MULTI_GYM",
        access_date=NOW.date(), gym_id=None,
    )
    other_qr, _ = service._mint_qr_token(daily_access_id=other.id)
    service.validate_checkin(gym_id=gym.id, qr_token=qr)
    with pytest.raises(HTTPException) as error:
        service.validate_checkin(gym_id=gym.id, qr_token=other_qr)
    assert error.value.status_code == 409
    membership.status = "CANCELLED"
    service.db.commit()
    assert service.get_today_access(user_id=user.id)["status"] == "USED"


def test_calendar_preserves_expired_history_and_gaps(access):
    service, user, _, membership = access
    membership.status = "EXPIRED"
    membership.start_at = NOW.replace(day=2, hour=0)
    membership.end_at = NOW.replace(day=5, hour=0)
    service.db.add(UserMembership(
        user_id=user.id, gym_id=membership.gym_id, plan_id=membership.plan_id,
        status="CANCELLED", start_at=NOW.replace(day=8, hour=0),
        end_at=NOW.replace(day=20, hour=0), cancelled_at=NOW.replace(day=10, hour=0),
        paid_amount=999, payment_status="PAID",
    ))
    service.db.commit()
    days = {day["date"].day: day for day in service.calendar_month(user_id=user.id, year=2026, month=9)["days"]}
    assert days[2]["status"] == "NO_VISIT"
    assert days[4]["status"] == "NO_VISIT"
    assert days[5]["status"] == "NONE"
    assert days[7]["status"] == "NONE"
    assert days[9]["status"] == "NO_VISIT"
    assert days[10]["status"] == "NONE"


def test_expired_token_does_not_consume_access(access):
    service, user, gym, _ = access
    qr = service.get_today_access(user_id=user.id)["qr_token"]
    token = service.db.scalars(select(AccessQrToken)).one()
    token.expires_at = NOW
    service.db.commit()
    with pytest.raises(HTTPException) as error:
        service.validate_checkin(gym_id=gym.id, qr_token=qr)
    assert error.value.status_code == 400
    assert service.db.scalars(select(CustomerDailyAccess)).one().status == "AVAILABLE"
    assert service.db.scalars(select(AccessQrToken)).one().status == "EXPIRED"


def test_utc_normalizes_naive_and_offset_datetimes():
    assert _utc(NOW.replace(tzinfo=None)) == NOW
    assert _utc(NOW.astimezone(timezone(timedelta(hours=5, minutes=30)))) == NOW


def test_today_response_rejects_incomplete_active_payload():
    adapter = TypeAdapter(TodayAccessResponse)
    with pytest.raises(ValidationError):
        adapter.validate_python({"status": "ACTIVE"})
    assert adapter.validate_python({"status": "PAUSED"}).status == "PAUSED"


def test_revoked_daily_access_is_unavailable_in_api_and_calendar(access):
    service, user, _, _ = access
    service.get_today_access(user_id=user.id)
    daily = service.db.scalars(select(CustomerDailyAccess)).one()
    daily.status = "REVOKED"
    service.db.commit()
    assert service.get_today_access(user_id=user.id)["status"] == "NO_ACCESS"
    today = next(day for day in service.calendar_month(user_id=user.id, year=2026, month=9)["days"] if day["date"] == NOW.date())
    assert today["qr_available"] is False
    assert today["qr_status"] == "NO_ACCESS"


def test_legacy_visit_blocks_new_issuance_and_scan_and_preserves_history(access):
    service, user, gym, _ = access
    qr = service.get_today_access(user_id=user.id)["qr_token"]
    service.db.add(MembershipDailyAccess(
        user_id=user.id, gym_id=gym.id, access_date=NOW.date(),
        status="SCANNED", scanned_at=NOW,
    ))
    service.db.commit()
    assert service.get_today_access(user_id=user.id)["status"] == "USED"
    with pytest.raises(HTTPException) as error:
        service.validate_checkin(gym_id=gym.id, qr_token=qr)
    assert error.value.status_code == 409
    day = next(d for d in service.calendar_month(user_id=user.id, year=2026, month=9)["days"] if d["date"] == NOW.date())
    assert day["qr_status"] == "USED"
    assert day["gym_name"] == gym.name
    assert day["qr_available"] is False


def test_qr_expiry_is_capped_at_utc_midnight(access, monkeypatch):
    service, user, _, _ = access
    monkeypatch.setattr(access_service, "utcnow", lambda: NOW.replace(hour=23, minute=59))
    result = service.get_today_access(user_id=user.id)
    assert result["expires_at"] == NOW.replace(day=17, hour=0, minute=0)