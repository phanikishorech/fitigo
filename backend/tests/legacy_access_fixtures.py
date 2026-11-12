"""Explicit isolated entitlement/assignment fixtures, not retired purchase APIs.

These tests exercise admission, not payment or invitation delivery. Payment and
invitation lifecycles have separate tests. Never import this from application code.
"""
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from app.models.auth import User
from app.models.membership import UserMembership
from app.models.staff import GymStaffAssignment
from app.services.auth_service import AuthService


def active_membership(db, customer_id, gym_id=None, plan_id=None, multi=False):
    now = datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)
    row = UserMembership(user_id=customer_id, gym_id=None if multi else gym_id, plan_id=None if multi else plan_id,
        membership_type='MULTI_GYM' if multi else 'SINGLE_GYM', start_at=now-timedelta(days=3),
        end_at=now+timedelta(days=30), status='ACTIVE', payment_status='PAID', paid_amount=999,
        payment_provider='TEST_FIXTURE')
    db.add(row); db.commit(); db.refresh(row)
    return row


def assigned_staff(db, gym_id):
    staff = AuthService(db).register_user(first_name='Fixture', last_name='Staff',
        email=f'access-staff-{uuid4().hex}@example.com', phone=None, password='Fixture password 123!', role_name='GYM_STAFF')
    db.add(GymStaffAssignment(gym_id=gym_id, user_id=staff.id, role='STAFF')); db.commit()
    return staff.id