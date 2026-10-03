"""Isolated foundation tests. Never connects to the configured application database."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Integer, MetaData, create_engine, func, inspect, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.security import create_access_token
from app.database.base import Base
from app.database.session import get_db
from app.models.auth import Role, User, UserRole
from app.models.platform_membership import PlatformMembershipAudit, PlatformMembershipOrder, PlatformMembershipPlan
from app.routers.platform_memberships import router
from app.services import platform_membership_service


NOW = datetime(2026, 9, 30, 12, tzinfo=timezone.utc)


@pytest.fixture
def api(monkeypatch):
    from app.core.config import settings
    from app.models.membership import UserMembership, GymMembershipPlan
    from app.models.wallet import WalletAccount, WalletTransaction
    from app.models.gym import Gym
    from app.models.access import CustomerDailyAccess, AccessQrToken, Checkin, AccessPauseDay
    from app.models.class_booking import GymSpecialHours
    from app.models.booking import Booking
    from app.models.slot import GymSlot
    monkeypatch.setattr(settings, "environment", "production")
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    metadata = MetaData()
    for name in ("gym_slots", "bookings"):
        table = Base.metadata.tables[name].to_metadata(metadata)
        table.c.id.type = Integer()
    for name in ("users", "roles", "user_roles", "gyms", "gym_membership_plans", "wallet_accounts", "wallet_transactions", "user_memberships", "platform_membership_plans", "platform_membership_offers", "platform_membership_orders", "platform_membership_audit", "customer_daily_accesses", "access_qr_tokens", "checkins", "access_pause_days", "membership_daily_accesses", "gym_operating_hours", "gym_special_hours"):
        table = Base.metadata.tables[name].to_metadata(metadata)
        if "id" in table.c and name != "platform_membership_orders":
            table.c.id.type = Integer()
    metadata.create_all(engine)
    monkeypatch.setattr(platform_membership_service, "utcnow", lambda: NOW)
    with Session(engine) as db:
        users = []
        for index, role_name in enumerate(("ADMIN", "CUSTOMER", "GYM_OWNER", "CUSTOMER")):
            role = db.scalars(select(Role).where(Role.name == role_name)).first()
            if role is None:
                role = Role(name=role_name)
                db.add(role)
                db.flush()
            user = User(email=f"platform-{index}@example.test", password_hash="unused", status="ACTIVE")
            db.add(user)
            db.flush()
            db.add(UserRole(user_id=user.id, role_id=role.id))
            users.append(user.id)
        db.commit()
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    from app.routers.memberships import router as memberships_router
    from app.routers.wallet import router as wallet_router
    from app.routers.profile import router as profile_router
    app.include_router(memberships_router, prefix="/api/v1")
    app.include_router(wallet_router, prefix="/api/v1")
    app.include_router(profile_router, prefix="/api/v1")

    def test_db():
        with Session(engine) as db:
            yield db

    app.dependency_overrides[get_db] = test_db
    headers = [{"Authorization": f"Bearer {create_access_token(str(uid))}"} for uid in users]
    with TestClient(app) as client:
        yield client, headers, engine
    engine.dispose()


def plan_body(**updates):
    return dict(code="test-monthly", name="Test monthly", description="Test-only plan",
                duration_value=1, duration_unit="MONTH", base_price="1200.00", currency="INR",
                benefits=["Backend supplied benefit"], badge=None, display_order=5, is_active=True, **updates)


def create(api, updates=None):
    client, headers, _ = api
    payload = plan_body()
    payload.update(updates or {})
    response = client.post("/api/v1/admin/membership-plans", json=payload, headers=headers[0])
    assert response.status_code == 201, response.text
    return response.json()


def offer(api, plan, **updates):
    client, headers, _ = api
    payload = dict(expected_version=plan["version"], kind="FIXED", value="125.00", title="Test promotion",
                   starts_at=(NOW-timedelta(days=1)).isoformat(), ends_at=(NOW+timedelta(days=1)).isoformat(), is_active=True)
    payload.update(updates)
    return client.put(f"/api/v1/admin/membership-plans/{plan['id']}/offer", headers=headers[0], json=payload)


def test_empty_and_server_ordered_active_catalog(api):
    client, _, _ = api
    response = client.get("/api/v1/memberships/plans")
    assert response.json()["items"] == []
    assert response.headers["cache-control"] == "no-store"
    create(api)
    create(api, {"code": "test-weekly", "duration_value": 7, "duration_unit": "DAY", "display_order": 1, "badge": "New"})
    hidden = create(api, {"code": "hidden", "is_active": False})
    catalog = client.get("/api/v1/memberships/plans").json()
    assert [p["code"] for p in catalog["items"]] == ["test-weekly", "test-monthly"]
    assert catalog["checkout_available"] is False
    plan = catalog["items"][1]
    assert plan["final_price"] == "1200.00" and plan["offer"] is None
    assert plan["pause_rule"] is None and plan["purchase_available"] is False
    assert client.get(f"/api/v1/memberships/plans/{hidden['id']}").status_code == 404
    assert client.get("/api/v1/memberships/plans?membership_type=SINGLE_GYM").status_code == 422


@pytest.mark.parametrize("kind,value,expected,percent", [("FIXED", "125.00", "1075.00", None), ("PERCENTAGE", "12.50", "1050.00", "12.50"), ("FIXED", "9999.00", "0.00", None)])
def test_server_offer_pricing(api, kind, value, expected, percent):
    plan = create(api)
    response = offer(api, plan, kind=kind, value=value)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["final_price"] == expected
    assert data["discount_percentage"] == percent
    assert data["offer"]["title"] == "Test promotion"
    assert Decimal(data["base_price"]) - Decimal(data["discount_amount"]) == Decimal(expected)


@pytest.mark.parametrize("updates", [
    {"ends_at": NOW.isoformat()}, {"starts_at": (NOW+timedelta(hours=1)).isoformat()}, {"is_active": False},
])
def test_expired_scheduled_disabled_offers_are_not_promoted(api, updates):
    data = offer(api, create(api), **updates).json()
    assert data["offer"] is None
    assert data["final_price"] == data["base_price"]
    assert data["discount_percentage"] is None


def test_rounding_and_exact_start_boundary(api):
    plan = create(api, {"base_price": "1.01"})
    data = offer(api, plan, kind="PERCENTAGE", value="50", starts_at=NOW.isoformat()).json()
    assert data["discount_amount"] == "0.51"
    assert data["final_price"] == "0.50"


def test_admin_permissions_validation_and_optimistic_versions(api):
    client, headers, engine = api
    for identity in (headers[1], headers[2], {}):
        assert client.post("/api/v1/admin/membership-plans", json=plan_body(), headers=identity).status_code in (401, 403)
    plan = create(api)
    assert offer(api, plan, kind="PERCENTAGE", value="101").status_code == 422
    assert offer(api, plan, ends_at=(NOW-timedelta(days=2)).isoformat()).status_code == 422
    assert offer(api, plan, starts_at="2026-09-01T12:00:00").status_code == 422
    for key, value in (("base_price", "-1"), ("currency", "XXX"), ("pause_allowance", 10), ("base_price", "NaN")):
        body = plan_body()
        body[key] = value
        assert client.post("/api/v1/admin/membership-plans", json=body, headers=headers[0]).status_code == 422
    assert offer(api, plan).status_code == 200
    stale = offer(api, plan)
    assert stale.status_code == 409 and stale.json()["detail"]["code"] == "PLAN_VERSION_CHANGED"
    assert client.post("/api/v1/admin/membership-plans", json=plan_body(), headers=headers[0]).status_code == 409
    with Session(engine) as db:
        assert db.scalar(select(func.count(PlatformMembershipAudit.id))) == 2


def test_orders_only_accept_plan_id_and_are_idempotent_owned_unpaid(api):
    client, headers, engine = api
    plan = create(api)
    auth = {**headers[1], "Idempotency-Key": "test-order-001"}
    url = "/api/v1/memberships/orders"
    assert client.post(url, json={"plan_id": plan["id"]}, headers=headers[1]).status_code == 422
    for field in ("price", "final_price", "discount", "payment_status", "user_id"):
        assert client.post(url, json={"plan_id": plan["id"], field: 1}, headers=auth).status_code == 422
    assert client.post(url, json={"plan_id": plan["id"]}, headers={"Idempotency-Key": "test-order-001"}).status_code == 401
    assert client.post(url, json={"plan_id": plan["id"]}, headers={**headers[2], "Idempotency-Key": "test-order-001"}).status_code == 403
    response = client.post(url, json={"plan_id": plan["id"]}, headers=auth)
    assert response.status_code == 200, response.text
    order = response.json()
    assert order["plan"]["final_price"] == "1200.00"
    assert order["status"] == "PAYMENT_DISABLED" and order["payment_status"] == "NOT_STARTED"
    assert order["eligibility_status"] == "NOT_EVALUATED" and order["membership_id"] is None
    assert order["requires_review"] is False
    assert client.post(url, json={"plan_id": plan["id"]}, headers=auth).json()["id"] == order["id"]
    other = create(api, {"code": "second"})
    assert client.post(url, json={"plan_id": other["id"]}, headers=auth).status_code == 409
    location = f"{url}/{order['id']}"
    assert client.get(location, headers=headers[3]).status_code == 404
    assert client.post(location + "/payment-session", headers=headers[3]).status_code == 404
    blocked = client.post(location + "/payment-session", headers=headers[1])
    assert blocked.status_code == 409 and blocked.json()["detail"]["code"] == "PAYMENT_NOT_CONFIGURED"
    with Session(engine) as db:
        assert db.scalar(select(func.count(PlatformMembershipOrder.id))) == 1
        assert db.scalars(select(PlatformMembershipOrder)).one().status == "PAYMENT_DISABLED"


def test_order_revalidates_current_pricing_without_overwriting_snapshot(api):
    client, headers, _ = api
    plan = create(api)
    auth = {**headers[1], "Idempotency-Key": "stale-price-001"}
    order = client.post("/api/v1/memberships/orders", headers=auth, json={"plan_id": plan["id"]}).json()
    updated = offer(api, plan).json()
    current = client.get(f"/api/v1/memberships/orders/{order['id']}", headers=headers[1]).json()
    assert current["requires_review"] is True
    assert current["current_plan"]["final_price"] == "1075.00"
    assert current["plan"]["final_price"] == "1200.00"
    payload = {**plan_body(), "expected_version": updated["version"], "is_active": False}
    assert client.put(f"/api/v1/admin/membership-plans/{plan['id']}", headers=headers[0], json=payload).status_code == 200
    assert client.get(f"/api/v1/memberships/orders/{order['id']}", headers=headers[1]).json()["current_plan"] is None
    assert client.post("/api/v1/memberships/orders", headers={**auth, "Idempotency-Key": "new-order-001"}, json={"plan_id": plan["id"]}).status_code == 404


def test_additive_migration_upgrade_and_downgrade_in_isolation():
    file = Path(__file__).parents[1] / "alembic/versions/3b8e1c2d4f60_platform_membership_catalog_orders.py"
    spec = spec_from_file_location("platform_migration", file)
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE users (id BIGINT PRIMARY KEY)")
        context = MigrationContext.configure(connection)
        with Operations.context(context):
            module.upgrade()
            assert len(inspect(connection).get_table_names()) == 5
            module.downgrade()
            assert inspect(connection).get_table_names() == ["users"]
    engine.dispose()


def test_initial_configuration_is_valid_and_duplicate_codes_are_rejected(tmp_path):
    from app.scripts.import_platform_membership_plans import read_plans

    config = Path(__file__).parents[1] / "config/multi_gym_plans.json"
    plans = read_plans(config)
    assert len(plans) == 4
    assert all(plan.currency == "INR" and plan.is_active for plan in plans)
    duplicate = tmp_path / "duplicate.json"
    import json
    duplicate.write_text(json.dumps([plan_body(), plan_body()]), encoding="utf-8")
    with pytest.raises(ValueError, match="unique"):
        read_plans(duplicate)


def test_application_openapi_registers_foundation_without_replacing_existing_routes():
    from app.main import app

    paths = app.openapi()["paths"]
    for path in (
        "/api/v1/memberships/plans", "/api/v1/memberships/orders",
        "/api/v1/memberships/orders/{order_id}/payment-session",
        "/api/v1/memberships/gyms/{gym_id}/plans", "/api/v1/memberships/gyms/{gym_id}/purchase",
        "/api/v1/cart/checkout/wallet", "/api/v1/customer/access/today",
    ):
        assert path in paths


@pytest.mark.parametrize("updates,state", [
    ({}, "ACTIVE"),
    ({"starts_at": (NOW + timedelta(hours=1)).isoformat()}, "SCHEDULED"),
    ({"ends_at": NOW.isoformat()}, "EXPIRED"),
    ({"is_active": False}, "DISABLED"),
])
def test_admin_can_read_complete_offer_configuration_without_public_leak(api, updates, state):
    client, headers, _ = api
    plan = create(api)
    url = f"/api/v1/admin/membership-plans/{plan['id']}"
    assert client.get(url, headers=headers[0]).json()["offer_configuration"] is None
    saved = offer(api, plan, **updates)
    assert saved.status_code == 200
    response = client.get(url, headers=headers[0])
    assert response.status_code == 200
    assert response.headers['cache-control'] == 'no-store'
    detail = response.json()
    config = detail['offer_configuration']
    assert config['state'] == state
    assert config['value'] == '125.00'
    assert config['starts_at'].endswith('Z') and config['ends_at'].endswith('Z')
    assert detail['plan']['version'] == saved.json()['version']
    for auth in ({}, headers[1], headers[2]):
        assert client.get(url, headers=auth).status_code in (401, 403)
    public = client.get(f"/api/v1/memberships/plans/{plan['id']}").json()
    assert 'offer_configuration' not in public
    if state != 'ACTIVE':
        assert public['offer'] is None


def test_admin_screen_edit_disable_and_reenable_offer_preserve_full_config(api):
    client, headers, _ = api
    plan = create(api)
    saved = offer(api, plan).json()
    url = f"/api/v1/admin/membership-plans/{plan['id']}"
    configuration = client.get(url, headers=headers[0]).json()['offer_configuration']
    editable = {key: value for key, value in configuration.items() if key not in ('id', 'state')}
    disabled = client.put(url + '/offer', headers=headers[0], json={**editable, 'expected_version': saved['version'], 'is_active': False})
    assert disabled.status_code == 200
    assert disabled.json()['offer'] is None
    current = client.get(url, headers=headers[0]).json()
    assert current['offer_configuration']['value'] == '125.00'
    assert current['offer_configuration']['state'] == 'DISABLED'
    enabled = client.put(url + '/offer', headers=headers[0], json={**editable, 'expected_version': current['plan']['version'], 'is_active': True})
    assert enabled.status_code == 200 and enabled.json()['final_price'] == '1075.00'
    body = {**plan_body(), 'base_price': '1500.00', 'expected_version': enabled.json()['version']}
    changed = client.put(url, headers=headers[0], json=body)
    assert changed.status_code == 200
    assert changed.json()['final_price'] == '1375.00'
    assert client.get('/api/v1/memberships/plans').json()['items'][0]['final_price'] == '1375.00'