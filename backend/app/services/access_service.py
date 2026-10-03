from __future__ import annotations

import hashlib
import secrets
from datetime import date, datetime, time, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.time import utc_today, utcnow
from app.models.access import (
    AccessPauseDay,
    AccessQrToken,
    Checkin,
    CheckinStatus,
    CustomerDailyAccess,
    DailyAccessStatus,
    QrTokenStatus,
)
from app.models.auth import User, UserStatus
from app.models.gym import Gym
from app.models.membership import MembershipDailyAccess, MembershipStatus, UserMembership
from app.services.membership_entitlement import active_memberships, covers, scope


def _sha256_hex(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _token_prefix() -> str:
    return "GYMACCESS:"


def _utc(value: datetime) -> datetime:
    # MySQL returns naive DATETIME values; they are stored as UTC.
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _format_access_key(*, user_id: int, membership_id: int, access_date: date, gym_id: int | None) -> str:
    # gym_id=None used for MULTI_GYM
    return f"u:{user_id}|m:{membership_id}|d:{access_date.isoformat()}|g:{gym_id if gym_id is not None else 'ANY'}"


def _month_bounds(*, year: int, month: int) -> tuple[date, date]:
    if month < 1 or month > 12:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid month")
    start = date(year, month, 1)
    if month == 12:
        end = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        end = date(year, month + 1, 1) - timedelta(days=1)
    return start, end


class AccessService:
    def __init__(self, db: Session):
        self.db = db

    def _get_user(self, user_id: int) -> User:
        u = self.db.execute(select(User).where(User.id == user_id)).scalars().first()
        if not u:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        return u

    def _is_paused(self, *, user_id: int, access_date: date) -> bool:
        row = (
            self.db.execute(
                select(AccessPauseDay.id).where(AccessPauseDay.user_id == user_id, AccessPauseDay.access_date == access_date).limit(1)
            )
            .first()
        )
        return bool(row)

    def _active_memberships_for_date(self, *, user_id: int, at: datetime) -> list[UserMembership]:
        # Membership rows use timezone-aware columns, but historically MySQL may return naive.
        # We stick to naive UTC comparisons (datetime.utcnow) elsewhere. Here we only compare
        # using datetime.utcnow() style values.
        # at is timezone-aware (utcnow); we convert to naive UTC for safety.
        at_naive = _utc(at).replace(tzinfo=None)
        return list(
            self.db.execute(
                select(UserMembership).where(
                    UserMembership.user_id == user_id,
                    UserMembership.status == MembershipStatus.ACTIVE.value,
                    UserMembership.payment_status == "PAID",
                    UserMembership.start_at <= at_naive,
                    UserMembership.end_at > at_naive,
                )
            )
            .scalars()
            .all()
        )

    def _resolve_today_access_context(self, *, user_id: int) -> dict:
        now = utcnow()
        today = now.date()

        if self._get_user(user_id).status != UserStatus.ACTIVE.value:
            return {"status": "NO_ACCESS", "today": today, "now": now}

        if self._is_paused(user_id=user_id, access_date=today):
            return {"status": "PAUSED", "today": today, "now": now}

        memberships = self._active_memberships_for_date(user_id=user_id, at=now)
        if not memberships:
            return {"status": "NO_ACCESS", "today": today, "now": now}

        # Determine access type based on number of active gyms.
        gym_ids = sorted({int(m.gym_id) for m in memberships if m.gym_id is not None})
        access_type = scope(memberships)

        # Choose a stable membership_id for uniqueness/audit.
        # SINGLE_GYM: the only membership.
        # MULTI_GYM: choose the one with latest end_at.
        primary = max(memberships, key=lambda m: (_utc(m.end_at), int(m.id)))
        gym_id = gym_ids[0] if access_type == "SINGLE_GYM" else None

        gym = None
        if gym_id is not None:
            gym = self.db.execute(select(Gym).where(Gym.id == gym_id)).scalars().first()

        return {
            "status": "OK",
            "today": today,
            "now": now,
            "access_type": access_type,
            "gym": gym,
            "membership_id": int(primary.id),
            "gym_id": gym_id,
        }

    def _get_or_create_daily_access(self, *, user_id: int, membership_id: int, access_type: str, access_date: date, gym_id: int | None) -> CustomerDailyAccess:
        access_key = _format_access_key(user_id=user_id, membership_id=membership_id, access_date=access_date, gym_id=gym_id)

        existing = self.db.execute(select(CustomerDailyAccess).where(CustomerDailyAccess.access_key == access_key)).scalars().first()
        if existing:
            return existing

        rec = CustomerDailyAccess(
            user_id=user_id,
            membership_id=membership_id,
            access_type=access_type,
            gym_id=gym_id,
            access_date=access_date,
            access_key=access_key,
            status=DailyAccessStatus.AVAILABLE.value,
            used_at=None,
            used_gym_id=None,
            checkin_id=None,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )

        self.db.add(rec)
        try:
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            # Race: someone else created it.
            existing2 = self.db.execute(select(CustomerDailyAccess).where(CustomerDailyAccess.access_key == access_key)).scalars().first()
            if existing2:
                return existing2
            raise
        self.db.refresh(rec)
        return rec

    def _get_active_token_for_daily_access(self, *, daily_access_id: int, now: datetime) -> AccessQrToken | None:
        now_naive = now.replace(tzinfo=None)
        return (
            self.db.execute(
                select(AccessQrToken)
                .where(
                    AccessQrToken.daily_access_id == daily_access_id,
                    AccessQrToken.status == QrTokenStatus.ACTIVE.value,
                    AccessQrToken.expires_at > now_naive,
                )
                .order_by(AccessQrToken.id.desc())
            )
            .scalars()
            .first()
        )

    def _mint_qr_token(self, *, daily_access_id: int, ttl_minutes: int = 5) -> tuple[str, AccessQrToken]:
        # Opaque random token; QR contains only prefix + token.
        raw = secrets.token_urlsafe(32)
        token_hash = _sha256_hex(raw)
        now = utcnow()
        exp = min(now + timedelta(minutes=ttl_minutes), datetime.combine(now.date() + timedelta(days=1), time.min, tzinfo=timezone.utc))
        rec = AccessQrToken(
            daily_access_id=daily_access_id,
            token_hash=token_hash,
            status=QrTokenStatus.ACTIVE.value,
            generated_at=now,
            expires_at=exp,
            used_at=None,
            used_gym_id=None,
            checkin_id=None,
            created_at=now,
            updated_at=now,
        )
        self.db.add(rec)
        self.db.commit()
        self.db.refresh(rec)
        return f"{_token_prefix()}{raw}", rec

    def get_today_access(self, *, user_id: int) -> dict:
        """Return today's access status.

        For ACTIVE status we always return a usable short-lived qr_token.
        """

        return self.get_or_create_active_qr_token(user_id=user_id)

    def get_or_create_active_qr_token(self, *, user_id: int) -> dict:
        # Helper for API: always return a qr_token when access is ACTIVE.
        used = self._used_access(user_id=user_id, access_date=utc_today())
        if used:
            gym = self.db.get(Gym, used.used_gym_id) if used.used_gym_id else None
            return {"status": "USED", "gym_name": gym.name if gym else None, "used_at": _utc(used.used_at) if used.used_at else None}
        legacy = self._legacy_visit(user_id=user_id, access_date=utc_today())
        if legacy:
            gym = self.db.get(Gym, legacy.gym_id)
            return {"status": "USED", "gym_name": gym.name if gym else None, "used_at": _utc(legacy.scanned_at or legacy.created_at)}
        ctx = self._resolve_today_access_context(user_id=user_id)
        today = ctx["today"]
        now = ctx["now"]

        if ctx["status"] in {"PAUSED", "NO_ACCESS"}:
            return {"status": ctx["status"]}

        access_type = ctx["access_type"]
        gym_id = ctx["gym_id"]
        membership_id = ctx["membership_id"]
        gym = ctx.get("gym")

        daily = self._get_or_create_daily_access(
            user_id=user_id,
            membership_id=membership_id,
            access_type=access_type,
            access_date=today,
            gym_id=gym_id,
        )

        if daily.status == DailyAccessStatus.USED.value:
            gym_name = None
            if daily.used_gym_id:
                g = self.db.execute(select(Gym).where(Gym.id == daily.used_gym_id)).scalars().first()
                gym_name = g.name if g else None
            return {"status": "USED", "gym_name": gym_name, "used_at": _utc(daily.used_at) if daily.used_at else None}

        if daily.status != DailyAccessStatus.AVAILABLE.value:
            return {"status": "NO_ACCESS" if daily.status == DailyAccessStatus.REVOKED.value else daily.status}

        # In this MVP we always mint a fresh short-lived token (rotating). You can call this
        # endpoint repeatedly to refresh QR while daily access remains AVAILABLE.
        qr_token, rec = self._mint_qr_token(daily_access_id=int(daily.id))
        return {
            "status": "ACTIVE",
            "access_type": access_type,
            "gym": ({"id": int(gym.id), "name": gym.name} if gym else None),
            "qr_token": qr_token,
            "expires_at": _utc(rec.expires_at),
        }

    def _legacy_visit(self, *, user_id: int, access_date: date) -> MembershipDailyAccess | None:
        return self.db.execute(select(MembershipDailyAccess).where(
            MembershipDailyAccess.user_id == user_id,
            MembershipDailyAccess.access_date == access_date,
            MembershipDailyAccess.status == "SCANNED",
        )).scalars().first()

    def _used_access(self, *, user_id: int, access_date: date, lock: bool = False) -> CustomerDailyAccess | None:
        query = select(CustomerDailyAccess).where(
            CustomerDailyAccess.user_id == user_id,
            CustomerDailyAccess.access_date == access_date,
            CustomerDailyAccess.status == DailyAccessStatus.USED.value,
        )
        if lock:
            query = query.with_for_update()
        return self.db.execute(query).scalars().first()

    def _validate_checkin_time_window(self, *, gym_id: int, at: datetime) -> None:
        """Validate that `at` is within gym operating hours for that date.

        Uses GymSpecialHours override if present; otherwise GymOperatingHours.

        If no hours are configured, this check is permissive (MVP), but still blocks if marked closed.
        """

        from app.models.class_booking import GymSpecialHours
        from app.models.gym import GymOperatingHours

        d = at.date()
        t = at.time()

        sp = (
            self.db.execute(select(GymSpecialHours).where(GymSpecialHours.gym_id == gym_id, GymSpecialHours.date == d))
            .scalars()
            .first()
        )
        if sp:
            if sp.is_closed:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Gym is closed")
            if sp.open_time and sp.close_time:
                if not (sp.open_time <= t <= sp.close_time):
                    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Outside allowed check-in window")
            return

        dow = d.weekday()
        row = (
            self.db.execute(select(GymOperatingHours).where(GymOperatingHours.gym_id == gym_id, GymOperatingHours.day_of_week == dow))
            .scalars()
            .first()
        )
        if not row:
            return
        if row.is_closed:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Gym is closed")
        if row.open_time and row.close_time:
            if not (row.open_time <= t <= row.close_time):
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Outside allowed check-in window")

    def validate_checkin(self, *, gym_id: int, qr_token: str) -> dict:
        # Parse token
        if not qr_token.startswith(_token_prefix()):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid QR")
        raw = qr_token[len(_token_prefix()) :]
        if not raw or len(raw) < 10:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid QR")
        token_hash = _sha256_hex(raw)

        now = utcnow()
        today = now.date()

        # Validate scanning gym is approved/active
        gym = (
            self.db.execute(select(Gym).where(Gym.id == gym_id, Gym.status == "APPROVED", Gym.is_active.is_(True)))
            .scalars()
            .first()
        )
        if not gym:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Gym not found")

        # Start txn / lock QR row
        try:
            # Serialize scans across ALL entitlements for this customer. Membership
            # purchases/cancellations can change the computed daily access key.
            user_id = self.db.execute(
                select(CustomerDailyAccess.user_id)
                .join(AccessQrToken, AccessQrToken.daily_access_id == CustomerDailyAccess.id)
                .where(AccessQrToken.token_hash == token_hash)
            ).scalar_one_or_none()
            if user_id is None:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired QR")
            user = self.db.execute(
                select(User).where(User.id == user_id).with_for_update().execution_options(populate_existing=True)
            ).scalars().first()
            if not user or user.status != UserStatus.ACTIVE.value:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Customer is not active")
            gym = self.db.scalars(select(Gym).where(Gym.id == gym_id).with_for_update().execution_options(populate_existing=True)).first()
            if not gym or gym.status != "APPROVED" or not gym.is_active:
                raise HTTPException(status_code=403, detail={"code": "GYM_NOT_ELIGIBLE"})
            token_row = (
                self.db.execute(select(AccessQrToken).where(AccessQrToken.token_hash == token_hash).with_for_update().execution_options(populate_existing=True))
                .scalars()
                .first()
            )
            if not token_row:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired QR")

            if token_row.status != QrTokenStatus.ACTIVE.value:
                if token_row.status == QrTokenStatus.USED.value:
                    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="QR code has already been used.")
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired QR")

            if _utc(token_row.expires_at) <= now:
                # Expire token
                token_row.status = QrTokenStatus.EXPIRED.value
                self.db.commit()
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired QR")

            daily = (
                self.db.execute(select(CustomerDailyAccess).where(CustomerDailyAccess.id == token_row.daily_access_id).with_for_update().execution_options(populate_existing=True))
                .scalars()
                .first()
            )
            if not daily:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid QR")

            # Validate daily access eligibility
            if daily.access_date != today:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="QR is only valid for today")

            if self._used_access(user_id=int(daily.user_id), access_date=today, lock=True):
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Today's gym access has already been used.")
            if self._legacy_visit(user_id=int(daily.user_id), access_date=today):
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Today's gym access has already been used.")
            if daily.status == DailyAccessStatus.PAUSED.value:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This visit has been paused.")
            if daily.status in {DailyAccessStatus.EXPIRED.value, DailyAccessStatus.REVOKED.value}:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access is not available.")

            # Validate membership is still active (defense-in-depth)
            m = (
                self.db.execute(select(UserMembership).where(UserMembership.id == daily.membership_id).with_for_update().execution_options(populate_existing=True))
                .scalars()
                .first()
            )
            if not m:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No active membership")

            # ensure membership dates
            if (
                m.status != MembershipStatus.ACTIVE.value
                or m.user_id != daily.user_id
                or m.payment_status != "PAID"
                or _utc(m.start_at) > now
                or _utc(m.end_at) <= now
            ):
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Membership is not active")

            # Pause-day policy
            if self._is_paused(user_id=int(daily.user_id), access_date=today):
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This visit has been paused.")

            # Access type rules
            if daily.access_type == "SINGLE_GYM":
                if daily.gym_id is None or daily.gym_id != m.gym_id:
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid access")
                if int(daily.gym_id) != int(gym_id):
                    g_assigned = self.db.execute(select(Gym).where(Gym.id == daily.gym_id)).scalars().first()
                    assigned_name = g_assigned.name if g_assigned else "assigned gym"
                    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"This access is valid only at {assigned_name}.")

            elif daily.access_type == "MULTI_GYM":
                memberships = active_memberships(self.db, int(daily.user_id), now, lock=True)
                if not covers(memberships, gym):
                    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail={"code": "GYM_NOT_ELIGIBLE"})
            else:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid access")

            # Allowed time window: enforce within operating hours for the scanning gym.
            self._validate_checkin_time_window(gym_id=int(gym_id), at=now)

            # Create checkin
            full_name = " ".join([p for p in [user.first_name, user.last_name] if p]) or "Member"

            checkin = Checkin(
                user_id=int(daily.user_id),
                daily_access_id=int(daily.id),
                qr_token_id=int(token_row.id),
                gym_id=int(gym_id),
                checkin_time=now,
                status=CheckinStatus.SUCCESS.value,
                note=None,
                created_at=now,
            )
            self.db.add(checkin)
            self.db.flush()  # assign id

            # Mark used
            daily.status = DailyAccessStatus.USED.value
            daily.used_at = now
            daily.used_gym_id = int(gym_id)
            daily.checkin_id = int(checkin.id)
            daily.updated_at = datetime.utcnow()

            token_row.status = QrTokenStatus.USED.value
            token_row.used_at = now
            token_row.used_gym_id = int(gym_id)
            token_row.checkin_id = int(checkin.id)
            token_row.updated_at = datetime.utcnow()

            self.db.commit()

            return {
                "success": True,
                "status": "CHECKED_IN",
                "customer_name": full_name,
                "gym_name": gym.name,
                "access_type": daily.access_type,
                "checkin_time": _utc(checkin.checkin_time),
            }
        except HTTPException:
            self.db.rollback()
            raise
        except Exception:
            self.db.rollback()
            raise

    def calendar_month(self, *, user_id: int, year: int, month: int) -> dict:
        start, end = _month_bounds(year=year, month=month)
        today = utc_today()

        # Determine access type for THIS MONTH context based on memberships active today (MVP)
        ctx = self._resolve_today_access_context(user_id=user_id)
        access_type = ctx.get("access_type") if ctx.get("status") == "OK" else None
        gym = ctx.get("gym") if access_type == "SINGLE_GYM" else None

        # Load checkins in month
        rows = list(
            self.db.execute(
                select(Checkin, Gym)
                .join(Gym, Gym.id == Checkin.gym_id)
                .where(Checkin.user_id == user_id, Checkin.status == CheckinStatus.SUCCESS.value, func.date(Checkin.checkin_time) >= start, func.date(Checkin.checkin_time) <= end)
                .order_by(Checkin.checkin_time.asc())
            ).all()
        )
        visited_map: dict[date, dict] = {}
        for c, g in rows:
            d = (c.checkin_time.date() if isinstance(c.checkin_time, datetime) else today)
            visited_map[d] = {"gym_id": int(g.id), "gym_name": g.name, "checkin_time": c.checkin_time.time()}

        # Legacy attendance remains visible without manufacturing new credentials.
        legacy_rows = self.db.execute(select(MembershipDailyAccess, Gym).join(
            Gym, Gym.id == MembershipDailyAccess.gym_id,
        ).where(
            MembershipDailyAccess.user_id == user_id,
            MembershipDailyAccess.status == "SCANNED",
            MembershipDailyAccess.access_date >= start,
            MembershipDailyAccess.access_date <= end,
        )).all()
        for visit, visited_gym in legacy_rows:
            visited_map.setdefault(visit.access_date, {
                "gym_id": int(visited_gym.id), "gym_name": visited_gym.name,
                "checkin_time": _utc(visit.scanned_at or visit.created_at).time(),
            })

        paused_dates = set(
            d
            for (d,) in self.db.execute(
                select(AccessPauseDay.access_date)
                .where(AccessPauseDay.user_id == user_id, AccessPauseDay.access_date >= start, AccessPauseDay.access_date <= end)
            ).all()
        )

        # Keep each historical membership interval separate: gaps between plans
        # are not missed visits, and pausing today must not erase past eligibility.
        memberships = self.db.execute(select(UserMembership).where(
            UserMembership.user_id == user_id,
            UserMembership.payment_status == "PAID",
            UserMembership.status.in_([status.value for status in MembershipStatus]),
            UserMembership.start_at < datetime.combine(end + timedelta(days=1), time.min),
            UserMembership.end_at > datetime.combine(start, time.min),
        )).scalars().all()
        intervals = []
        for membership in memberships:
            interval_end = _utc(membership.end_at)
            if membership.status == MembershipStatus.CANCELLED.value:
                if membership.cancelled_at is None:
                    continue
                interval_end = min(interval_end, _utc(membership.cancelled_at))
            intervals.append((_utc(membership.start_at), interval_end))

        daily_states = {daily.access_date: daily.status for daily in self.db.execute(
            select(CustomerDailyAccess).where(
                CustomerDailyAccess.user_id == user_id,
                CustomerDailyAccess.access_date >= start,
                CustomerDailyAccess.access_date <= end,
            ).order_by(CustomerDailyAccess.id.asc())
        ).scalars()}
        used_today = self._used_access(user_id=user_id, access_date=today)

        # Build day list
        days: list[dict] = []
        cur = start
        while cur <= end:
            if cur in visited_map:
                v = visited_map[cur]
                days.append(
                    {
                        "date": cur,
                        "status": "VISITED" if cur != today else "TODAY",
                        "qr_available": False,
                        "qr_status": "USED",
                        "gym_id": v["gym_id"],
                        "gym_name": v["gym_name"],
                        "checkin_time": v["checkin_time"],
                    }
                )
            elif cur in paused_dates:
                days.append({"date": cur, "status": "PAUSED" if cur != today else "TODAY", "qr_available": False, "qr_status": "PAUSED"})
            else:
                if cur == today:
                    today_status = ctx["status"]
                    daily_status = daily_states.get(today)
                    if used_today:
                        days.append({"date": cur, "status": "TODAY", "qr_available": False, "qr_status": "USED"})
                    elif daily_status in {"PAUSED", "EXPIRED", "REVOKED"}:
                        days.append({"date": cur, "status": "TODAY", "qr_available": False, "qr_status": "NO_ACCESS" if daily_status == "REVOKED" else daily_status})
                    elif today_status == "OK":
                        days.append({"date": cur, "status": "TODAY", "qr_available": True, "qr_status": "ACTIVE"})
                    elif today_status == "PAUSED":
                        days.append({"date": cur, "status": "TODAY", "qr_available": False, "qr_status": "PAUSED"})
                    else:
                        days.append({"date": cur, "status": "TODAY", "qr_available": False, "qr_status": "NO_ACCESS"})
                elif cur < today:
                    day_start = datetime.combine(cur, time.min, tzinfo=timezone.utc)
                    day_end = day_start + timedelta(days=1)
                    eligible = any(interval_start < day_end and interval_end > day_start for interval_start, interval_end in intervals)
                    if eligible:
                        days.append({"date": cur, "status": "NO_VISIT", "qr_available": False, "qr_status": "EXPIRED"})
                    else:
                        days.append({"date": cur, "status": "NONE", "qr_available": False, "qr_status": None})
                else:
                    days.append({"date": cur, "status": "FUTURE", "qr_available": False, "qr_status": None})

            cur = cur + timedelta(days=1)

        return {
            "month": month,
            "year": year,
            "access_type": access_type,
            "gym": ({"id": int(gym.id), "name": gym.name} if gym else None),
            "days": days,
        }
