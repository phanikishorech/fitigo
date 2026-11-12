from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import patch
from fastapi import HTTPException
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from app.core.config import settings
from app.models.auth import User
from app.models.support import SupportTicket, SupportMessage
from app.schemas.support import SupportCreate, SupportReply
from app.services.support_service import SupportService
from test_owner_dashboard_mysql import mysql_api, pytestmark


def test_concurrent_create_and_reply_prevent_duplicates_and_lost_updates(mysql_api, monkeypatch):
    monkeypatch.setattr(settings, 'support_workflows_enabled', True)
    monkeypatch.setattr(settings, 'operational_workflows_enabled', True)
    engine = mysql_api[2]; barrier = Barrier(2)
    payload = SupportCreate(category='TECHNICAL', subject='Concurrent request', body='One request')
    def create(_):
        with Session(engine) as db:
            actor = db.get(User, 3); barrier.wait(timeout=20)
            return SupportService(db, actor).create(payload, 'concurrent-create-1')['id']
    with ThreadPoolExecutor(max_workers=2) as pool: ids = list(pool.map(create, range(2)))
    assert ids[0] == ids[1]
    barrier = Barrier(2)
    def reply(i):
        with Session(engine) as db:
            service = SupportService(db, db.get(User, 3)); barrier.wait(timeout=20)
            try: return service.reply(ids[0], SupportReply(body=f'Reply {i}', expected_version=1), f'concurrent-reply-{i}')['version']
            except HTTPException as error: return error.status_code
    with ThreadPoolExecutor(max_workers=2) as pool: results = list(pool.map(reply, range(2)))
    assert sorted(results) == [2, 409]
    with Session(engine) as db:
        assert db.scalar(select(func.count(SupportTicket.id))) == 1
        assert db.scalar(select(func.count(SupportMessage.id))) == 2


def test_support_and_readiness_queries_work_read_only(mysql_api, monkeypatch):
    from app.services.readiness_service import readiness
    monkeypatch.setattr(settings, 'support_workflows_enabled', True)
    monkeypatch.setattr(settings, 'operational_workflows_enabled', True)
    with mysql_api[2].connect() as connection:
        connection.exec_driver_sql('SET TRANSACTION READ ONLY'); connection.exec_driver_sql('START TRANSACTION')
        with Session(bind=connection) as db:
            assert SupportService(db, db.get(User, 3)).list(None, '', 20, 0)['total'] == 0
            assert readiness(db)['production_certified'] is False
        connection.rollback()