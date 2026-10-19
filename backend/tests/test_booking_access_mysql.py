"""Opt-in concurrent scans in a disposable local MySQL schema; no application writes."""
import os
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from app.core.time import IST, stored_instant
from datetime import time, timedelta
from threading import Barrier
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import Session

pytestmark = pytest.mark.skipif(os.getenv("FITIGO_MYSQL_BOOKING_QR_TESTS") != "1", reason="Disposable MySQL schema is opt-in")


@pytest.fixture
def mysql_access(monkeypatch):
    from app.main import app
    from app.core.config import settings
    from app.database.base import Base
    from app.database.session import engine as application_engine
    from app.models.auth import User
    from app.models.gym import Gym, GymOperatingHours
    from app.models.slot import GymSlot
    from app.services import access_service, booking_access_service
    from app.services.booking_service import BookingService
    from test_booking_access_qr import NOW
    assert settings.environment == "development"
    assert application_engine.url.host in ("localhost", "127.0.0.1", "::1")
    name = "fitigo_booking_qr_test_" + uuid4().hex[:12]
    control = create_engine(application_engine.url.set(database=None), isolation_level="AUTOCOMMIT")
    created, engine = False, None
    try:
        with control.connect() as connection:
            connection.execute(text(f"CREATE DATABASE `{name}` CHARACTER SET utf8mb4")); created = True
        engine = create_engine(application_engine.url.set(database=name), pool_pre_ping=True)
        # Apply actual migrations, not create_all, to exercise deployment on MySQL.
        from alembic import command
        from alembic.config import Config
        config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
        config.set_main_option("script_location", str(Path(__file__).resolve().parents[1] / "alembic"))
        monkeypatch.setattr(settings, "database_url", engine.url.render_as_string(hide_password=False))
        command.upgrade(config, "head")
        command.downgrade(config, "6eb14f5a7c93")
        # Reproduce partial MySQL DDL committed before a failed constraint add.
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE bookings ADD visitor_names JSON NULL"))
            connection.execute(text("ALTER TABLE cart_items ADD visitor_names JSON NULL"))
            connection.execute(text("ALTER TABLE access_qr_tokens MODIFY daily_access_id BIGINT NULL"))
            connection.execute(text("ALTER TABLE access_qr_tokens ADD booking_id BIGINT NULL"))
        command.upgrade(config, "head")
        monkeypatch.setattr(access_service, "utcnow", lambda: NOW)
        monkeypatch.setattr(booking_access_service, "utcnow", lambda: NOW)
        monkeypatch.setattr(BookingService, "_now", lambda self: stored_instant(NOW.replace(hour=9)))
        with Session(engine) as db:
            user = User(email="booking-qr-test@example.test", password_hash="unused", status="ACTIVE")
            db.add(user); db.flush()
            gym = Gym(owner_user_id=user.id, name="Isolated gym", status="APPROVED", is_active=True)
            db.add(gym); db.flush()
            for day in range(7):
                db.add(GymOperatingHours(gym_id=gym.id, day_of_week=day, open_time=time(6), close_time=time(23), is_closed=False))
            slot = GymSlot(gym_id=gym.id, name="Visit", start_time=time(10), end_time=time(14), capacity=50, price=100, is_active=1)
            db.add(slot); db.commit()
            yield engine, user.id, gym.id, slot.id
    finally:
        if engine is not None: engine.dispose()
        if created:
            with control.connect() as connection:
                connection.execute(text(f"DROP DATABASE `{name}`"))
        control.dispose()


@pytest.mark.parametrize("group", [False, True])
def test_concurrent_scans_consume_each_visitor_once(mysql_access, group):
    from app.models.access import Checkin
    from app.models.booking import Booking
    from app.services.access_service import AccessService
    from app.services.booking_access_service import BookingAccessService
    from app.services.booking_service import BookingService
    from test_booking_access_qr import NOW
    engine, uid, gym_id, slot_id = mysql_access
    with Session(engine) as db:
        booking = BookingService(db).create_booking(user_id=uid, gym_slot_id=slot_id, slot_date=NOW.date(),
            quantity=2 if group else 1, visitor_names=["David", "Mary"] if group else ["David"], notes=None)
        booking_id = booking.id
        BookingService(db).pay_dummy(user_id=uid, booking_id=booking_id)
        passes = BookingAccessService(db).issue(booking_id, uid)["passes"]
        tokens = [passes[0]["qr_token"], passes[-1]["qr_token"]]
    barrier = Barrier(2)
    def scan(token):
        with Session(engine) as db:
            barrier.wait(timeout=10)
            try:
                return AccessService(db).validate_checkin(gym_id=gym_id, qr_token=token, scanned_by=uid)["status"]
            except HTTPException as error:
                return error.detail["code"]
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(scan, tokens))
    assert results.count("CHECKED_IN") == (2 if group else 1)
    if not group: assert results.count("BOOKING_ALREADY_USED") == 1
    with Session(engine) as db:
        assert db.scalar(select(func.count(Checkin.id))) == (2 if group else 1)
        assert db.get(Booking, booking_id).attendance_status == "ATTENDED"