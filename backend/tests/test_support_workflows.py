"""Private support API regression, disposable schema only."""
from unittest.mock import patch
import pytest
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from app.core.config import settings
from app.models.auth import User
from app.models.support import SupportTicket, SupportMessage
from app.models.operations import OperationAudit
from app.routers import support_requests, readiness
from app.schemas.support import SupportCreate
from app.services.support_service import SupportService
from test_phase5_workflows import api as phase5_api, booking_api


@pytest.fixture
def api(phase5_api, monkeypatch):
    monkeypatch.setattr(settings, 'support_workflows_enabled', True)
    monkeypatch.setattr(settings, 'operational_workflows_enabled', True)
    for router in [support_requests.router, support_requests.admin_router, readiness.router]:
        phase5_api[0].app.include_router(router, prefix='/api/v1')
    return phase5_api


def create(api, actor=1, key='support-request-0001', **updates):
    return api[0].post('/api/v1/support/tickets', headers={**api[1][actor], 'Idempotency-Key': key},
        json={'subject': 'Help with gym access', 'category': 'TECHNICAL', 'body': 'Please review this issue.', **updates})


def test_create_idempotent_owned_and_safe_audit(api):
    response = create(api); assert response.status_code == 200, response.text
    assert response.headers['cache-control'] == 'no-store'
    assert create(api).json()['id'] == response.json()['id']
    assert create(api, subject='Different request').status_code == 409
    tid = response.json()['id']
    for actor in [2, 3, 5]:
        assert api[0].get(f'/api/v1/support/tickets/{tid}', headers=api[1][actor]).status_code == 404
        assert api[0].get('/api/v1/support/tickets', headers=api[1][actor]).json()['total'] == 0
    with Session(api[2]) as db:
        assert db.scalar(select(func.count(SupportTicket.id))) == 1
        assert db.scalar(select(func.count(SupportMessage.id))) == 1
        audit = db.scalar(select(OperationAudit))
        assert audit.action == 'SUPPORT_CREATED' and audit.actor_id == 1 and audit.context == {}


def test_auth_and_input_validation(api):
    client, headers, _ = api
    assert client.get('/api/v1/support/tickets').status_code == 401
    for actor in [1, 2, 3, 5]: assert client.get('/api/v1/admin/support/tickets', headers=headers[actor]).status_code == 403
    for update in [{'user_id': 2}, {'subject': ' '}, {'body': ' '}, {'body': 'x' * 2001}, {'status': 'RESOLVED'}, {'category': 'PAYMENT_SECRET'}, {'subject': 'line\nbreak'}]:
        assert create(api, **update).status_code == 422
    assert client.post('/api/v1/support/tickets', headers=headers[1], json={'subject': 'Help', 'category': 'OTHER', 'body': 'Details'}).status_code == 422
    for query in ['limit=0', 'limit=101', 'offset=-1', 'status=DELETED']:
        assert client.get('/api/v1/support/tickets?' + query, headers=headers[1]).status_code == 422
    assert create(api, key='bad').status_code == 422


def test_thread_reply_status_conflicts_and_history(api):
    client, headers, engine = api
    ticket = create(api).json(); tid = ticket['id']
    private = f'/api/v1/support/tickets/{tid}'
    admin = f'/api/v1/admin/support/tickets/{tid}'
    payload = {'body': 'Administrator response', 'expected_version': 1}
    h = {**headers[4], 'Idempotency-Key': 'admin-response-0001'}
    reply = client.post(admin + '/messages', headers=h, json=payload)
    assert reply.status_code == 200 and reply.json()['version'] == 2
    assert client.post(admin + '/messages', headers=h, json=payload).json()['version'] == 2
    assert client.post(admin + '/messages', headers=h, json={**payload, 'body': 'Other text'}).status_code == 409
    assert client.post(private + '/messages', headers={**headers[1], 'Idempotency-Key': 'reply-stale-0001'}, json={'body': 'Stale reply', 'expected_version': 1}).status_code == 409
    assert client.patch(admin + '/status', headers=headers[4], json={'status': 'RESOLVED', 'expected_version': 1}).status_code == 409
    changed = client.patch(admin + '/status', headers=headers[4], json={'status': 'RESOLVED', 'expected_version': 2})
    assert changed.status_code == 200 and changed.json()['version'] == 3
    assert client.post(private + '/messages', headers={**headers[1], 'Idempotency-Key': 'reply-closed-0001'}, json={'body': 'Another reply', 'expected_version': 3}).status_code == 409
    assert client.patch(admin + '/status', headers=headers[1], json={'status': 'OPEN', 'expected_version': 3}).status_code == 403
    assert client.patch(admin + '/status', headers=headers[4], json={'status': 'OPEN', 'expected_version': 3}).status_code == 200
    assert client.post(private + '/messages', headers={**headers[1], 'Idempotency-Key': 'reply-current-0001'}, json={'body': 'Thanks', 'expected_version': 4}).status_code == 200
    detail = client.get(private + '?limit=1&offset=1', headers=headers[1]).json()
    assert detail['message_total'] == 3 and detail['messages'][0]['author_kind'] == 'ADMIN'
    assert detail['version'] == 5 and not detail['can_change_status']
    with Session(engine) as db:
        assert db.scalar(select(func.count(SupportMessage.id))) == 3
        events = db.scalars(select(OperationAudit)).all()
        assert len(events) == 5 and all('body' not in e.context for e in events)


def test_literal_search_pagination_and_no_admin_bypass_through_personal_routes(api):
    create(api, subject='Percent % issue')
    create(api, key='support-request-0002', subject='Second issue')
    other = create(api, actor=2).json()
    client, headers, _ = api
    assert client.get('/api/v1/support/tickets?q=%25', headers=headers[1]).json()['total'] == 1
    assert len(client.get('/api/v1/support/tickets?limit=1&offset=1', headers=headers[1]).json()['items']) == 1
    assert client.get('/api/v1/admin/support/tickets', headers=headers[4]).json()['total'] == 3
    assert client.get(f"/api/v1/support/tickets/{other['id']}", headers=headers[4]).status_code == 404
    assert client.get(f"/api/v1/admin/support/tickets/{other['id']}", headers=headers[4]).status_code == 200


def test_disabled_gate_does_not_touch_tables(api, monkeypatch):
    monkeypatch.setattr(settings, 'support_workflows_enabled', False)
    assert not api[0].get('/api/v1/meta/support').json()['ticketing_available']
    assert create(api).status_code == 409
    assert api[0].get('/api/v1/support/tickets', headers=api[1][1]).status_code == 409
    with Session(api[2]) as db: assert db.scalar(select(func.count(SupportTicket.id))) == 0


def test_rollback_keeps_ticket_message_audit_atomic(api):
    with Session(api[2]) as db:
        service = SupportService(db, db.get(User, 1))
        # Rate-limit storage intentionally has its own transaction; the business
        # commit must still roll back request/message/audit together.
        with patch.object(service, 'throttle'), patch.object(db, 'commit', side_effect=RuntimeError('fixture')):
            with pytest.raises(RuntimeError): service.create(SupportCreate(category='OTHER', subject='Rollback', body='No commit'), 'rollback-request-01')
        db.rollback()
        assert db.scalar(select(func.count(SupportTicket.id))) == 0
        assert db.scalar(select(func.count(SupportMessage.id))) == 0
        assert db.scalar(select(func.count(OperationAudit.id))) == 0


def test_support_writes_rate_limited(api):
    for i in range(30): assert create(api, key=f'limited-request-{i:03d}').status_code == 200
    assert create(api, key='limited-request-final').status_code == 429


def test_readiness_is_admin_only_safe_and_not_certification(api):
    client, headers, _ = api
    for actor in [1, 2, 3, 5]: assert client.get('/api/v1/admin/readiness', headers=headers[actor]).status_code == 403
    response = client.get('/api/v1/admin/readiness', headers=headers[4])
    assert response.status_code == 200 and response.headers['cache-control'] == 'no-store'
    data = response.json(); assert not data['production_certified']
    assert all(value is False for value in data['financial_workflows'].values())
    assert any(c['code'] == 'WORKER_SCHEDULING' and c['status'] == 'MANUAL_CHECK' for c in data['checks'])
    assert 'password' not in response.text.lower() and '127.0.0.1' not in response.text


def test_message_history_cannot_be_rewritten_and_no_subject_or_body_in_audit(api):
    response = create(api, subject='Private subject', body='Private body with <script>literal text</script>')
    tid = response.json()['id']
    with Session(api[2]) as db:
        message = db.scalar(select(SupportMessage))
        message.body = 'Rewrite'
        with pytest.raises(ValueError, match='append-only'): db.commit()
        db.rollback()
        message = db.scalar(select(SupportMessage)); db.delete(message)
        with pytest.raises(ValueError, match='append-only'): db.commit()
        db.rollback()
        event = db.scalar(select(OperationAudit)); assert event.context == {} and event.resource_id == tid
    result = api[0].get('/api/v1/admin/audit-logs', headers=api[1][4])
    assert 'Private body' not in result.text and 'Private subject' not in result.text


def test_readiness_disabled_missing_schema_returns_explicit_blocker(api, monkeypatch):
    from sqlalchemy import create_engine
    from app.services.readiness_service import readiness
    engine = create_engine('sqlite://')
    try:
        with Session(engine) as db:
            result = readiness(db)
            check = next(c for c in result['checks'] if c['code'] == 'WORKFLOW_SCHEMA')
            assert check['status'] == 'BLOCKED' and not result['production_certified']
    finally: engine.dispose()


def test_revoked_session_and_admin_role_are_rechecked_before_write(api):
    from app.models.auth import UserRole, Role
    from fastapi import HTTPException
    with Session(api[2]) as db:
        user = db.get(User, 1)
        service = SupportService(db, user)
        user.token_version += 1; db.commit()
        with pytest.raises(HTTPException) as error:
            service.create(SupportCreate(category='OTHER', subject='Stale', body='Do not save'), 'stale-session-key')
        assert error.value.status_code == 401
        db.rollback()
        admin = SupportService(db, db.get(User, 4), admin=True)
        role = db.scalar(select(Role.id).where(Role.name == 'ADMIN'))
        assignment = db.scalar(select(UserRole).where(UserRole.user_id == 4, UserRole.role_id == role))
        db.delete(assignment); db.commit()
        with pytest.raises(HTTPException) as error: admin.authorize(lock=True)
        assert error.value.status_code == 403
        db.rollback()
        assert db.scalar(select(func.count(SupportTicket.id))) == 0