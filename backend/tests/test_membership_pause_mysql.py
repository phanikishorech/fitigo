"""Opt-in real row-lock checks using the existing disposable MySQL fixture."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Barrier

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from test_membership_wallet_mysql import mysql_wallet, pytestmark
from app.models.membership import MembershipPause, UserMembership
from app.models.platform_membership import PlatformMembershipPlan
from app.schemas.membership_pause import PauseConfirm, PauseRequest
from app.services.membership_pause_service import MembershipPauseService


@pytest.mark.parametrize('same_key', [True, False])
def test_concurrent_pause_is_atomic_and_cannot_overspend(mysql_wallet, same_key):
    engine, uid, pid = mysql_wallet
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    with Session(engine) as db:
        plan = db.get(PlatformMembershipPlan, pid)
        plan.pause_allowed = True; plan.max_pause_days = 6
        member = UserMembership(user_id=uid, membership_type='MULTI_GYM', platform_plan_id=pid,
            start_at=now-timedelta(days=1), end_at=now+timedelta(days=30), status='ACTIVE', payment_status='PAID', paid_amount=100)
        db.add(member); db.commit(); mid=member.id; old_end=member.end_at
        request = PauseRequest(start_date=now.date()+timedelta(days=2),days=6)
        preview = MembershipPauseService(db).preview(member,request)
    barrier=Barrier(2)
    def create(index):
        with Session(engine) as db:
            barrier.wait(timeout=10)
            try:
                result=MembershipPauseService(db).create(uid,mid,PauseConfirm(**request.model_dump(),accepted_preview=preview.preview_token), 'same-request-key' if same_key else f'competing-request-{index}')
                return result.pause_days_used
            except HTTPException as error:
                return error.detail['code']
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(create,[0,1]))
    with Session(engine) as db:
        assert db.scalar(select(func.count(MembershipPause.id)))==1
        assert db.get(UserMembership,mid).end_at==old_end+timedelta(days=6)
    assert results==[6,6] if same_key else sorted(map(str,results))==['6','PAUSE_LIMIT_EXCEEDED']