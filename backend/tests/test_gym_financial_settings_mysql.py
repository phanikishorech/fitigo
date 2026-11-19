from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from uuid import uuid4
import pytest
from fastapi import HTTPException
from sqlalchemy import event, func, select
from sqlalchemy.orm import Session
from app.models.gym import Gym
from app.models.financial_agreement import FinancialAgreementScope, FinancialAgreementVersion
from app.schemas.gym_financial_settings import SettingsCreate
from app.services import financial_agreements as agreements, gym_financial_settings as service
from app.services.gym_service import GymService
from test_financial_agreements import configured_api, mysql_api, pytestmark, NOW, payload as legacy_payload, post as legacy_post

PATH = '/api/v1/admin/financial-settings'


@pytest.fixture
def api(configured_api, monkeypatch):
    monkeypatch.setattr(service, 'utcnow', lambda: NOW)
    return configured_api


def payload(**changes):
    return dict(mode='test', gym_id=1, expected_version=0, expected_effective_version_id=None,
        effective_from=(NOW + timedelta(days=1)).isoformat(), settings=service.defaults(),
        reason='Initialize independent gym settings', acknowledge_configuration_only=True, **changes)


def post(api, data=None, key=None, actor=5):
    return api[0].post(PATH, json=data or payload(), headers={**api[1][actor], 'Idempotency-Key': key or str(uuid4())})


def test_missing_configuration_get_is_read_only_and_search_is_literal(api):
    client, headers, engine = api
    writes = []
    def spy(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith(('INSERT', 'UPDATE', 'DELETE')): writes.append(statement)
    event.listen(engine, 'before_cursor_execute', spy)
    try:
        response = client.get(PATH + '?mode=test&gym_id=1', headers=headers[5])
        assert response.status_code == 200, response.text
        data = response.json()
        assert data['effective'] is None and data['latest_version'] == 0
        assert data['template'] == service.defaults() and data['posting_enabled'] is False
        assert data['processing_blockers']
        assert response.headers['cache-control'] == 'no-store'
        assert client.get(PATH + '/gyms?q=Gym%202', headers=headers[5]).json()['items'] == [{'id': 2, 'name': 'Gym 2'}]
        assert client.get(PATH + '/gyms?q=%25', headers=headers[5]).json()['total'] == 0
        assert client.get(PATH + '/gyms?limit=1&offset=1', headers=headers[5]).json()['items'][0]['id'] == 2
        assert writes == []
    finally: event.remove(engine, 'before_cursor_execute', spy)


def test_selector_all_pages_and_history_validation_remain_strict(api):
    client, headers, engine = api
    with Session(engine) as db:
        db.add_all([Gym(name=f'Paged gym {i:02}', owner_user_id=1, status='APPROVED') for i in range(43)])
        db.commit()
        expected = set(db.scalars(select(Gym.id)))
    found = []
    for offset in range(0, len(expected), 20):
        response = client.get(PATH + '/gyms', params={'limit': 20, 'offset': offset}, headers=headers[5])
        assert response.status_code == 200
        assert response.json()['total'] == len(expected)
        found.extend(row['id'] for row in response.json()['items'])
    assert len(found) == len(set(found)) and set(found) == expected
    for path in (PATH + '/gyms?offset=-20', PATH + '?mode=test&gym_id=1&offset=-20', PATH):
        assert client.get(path, headers=headers[5]).status_code == 422


def test_existing_history_paginates_and_save_reload_preserves_every_version(api):
    client, headers, engine = api
    created = []
    for version in range(22):
        body = {**payload(), 'expected_version': version, 'effective_from': (NOW + timedelta(days=version + 1)).isoformat(),
            'reason': f'Independent change {version + 1}'}
        key = f'paged-history-change-{version}'
        response = post(api, body, key)
        assert response.status_code == 200, response.text
        assert post(api, body, key).json()['id'] == response.json()['id']
        created.append(response.json())
    pages = [client.get(PATH, params={'mode': 'test', 'gym_id': 1, 'offset': offset}, headers=headers[5]).json() for offset in (0, 20)]
    history = pages[0]['history'] + pages[1]['history']
    assert pages[0]['total'] == pages[1]['total'] == 22
    assert [row['id'] for row in history] == [row['id'] for row in reversed(created)]
    for row, original in zip(reversed(history), created):
        for field in ('terms', 'reason', 'actor_id', 'effective_from', 'created_at'):
            assert row[field] == original[field]
    assert client.get(PATH + '?mode=test&gym_id=2', headers=headers[5]).json()['total'] == 0
    assert client.get(PATH + '?mode=live&gym_id=1', headers=headers[5]).json()['total'] == 0


def test_admin_authorization_and_missing_schema(api, monkeypatch):
    client, headers, engine = api
    assert client.get(PATH + '?mode=test&gym_id=1').status_code == 401
    assert client.get(PATH + '/gyms', headers=headers[1]).status_code == 403
    assert post(api, actor=1).status_code == 403
    assert client.get(PATH + '?mode=test&gym_id=999', headers=headers[5]).status_code == 404
    monkeypatch.setattr(agreements, 'available', lambda db: False)
    data = client.get(PATH + '?mode=test&gym_id=1', headers=headers[5]).json()
    assert data['available'] is False and data['template'] is None
    assert post(api).status_code == 503


def test_future_only_idempotency_scope_independence_and_history(api, monkeypatch):
    body = payload(); key = 'settings-retry-key'
    response = post(api, body, key); assert response.status_code == 200, response.text
    first = response.json()
    assert first['version'] == 1 and first['actor_id'] == 5 and first['state'] == 'SCHEDULED'
    assert post(api, body, key).json()['id'] == first['id']
    assert post(api, {**body, 'reason': 'Different reason'}, key).status_code == 409
    assert post(api, body).status_code == 409
    with Session(api[2]) as db:
        assert agreements.resolve(db, 'test', 1, NOW) is None
        assert agreements.resolve(db, 'test', 1, NOW + timedelta(days=1)).id == first['id']
        assert agreements.resolve(db, 'test', 2, NOW + timedelta(days=2)) is None
        assert agreements.resolve(db, 'live', 1, NOW + timedelta(days=2)) is None
    monkeypatch.setattr(service, 'utcnow', lambda: NOW + timedelta(days=2))
    monkeypatch.setattr(agreements, 'utcnow', lambda: NOW + timedelta(days=2))
    assert post(api, body, key).json()['id'] == first['id']  # Retry even after commencement.
    changed = {**body, 'expected_version': 1, 'expected_effective_version_id': first['id'], 'effective_from': (NOW + timedelta(days=3)).isoformat()}
    changed['settings'] = service.defaults()
    changed['settings']['individual']['revenue'] = {'gym_percent': '80', 'fitigo_percent': '20'}
    second = post(api, changed); assert second.status_code == 200, second.text
    with Session(api[2]) as db:
        assert agreements.resolve(db, 'test', 1, NOW + timedelta(days=2)).id == first['id']
        assert agreements.resolve(db, 'test', 1, NOW + timedelta(days=3)).id == second.json()['id']
        original = db.get(FinancialAgreementVersion, first['id'])
        assert original.terms[service.KEY]['individual']['revenue']['gym_percent'] == '85'
        assert original.effective_to is None
        original.reason = 'Forbidden rewrite'
        with pytest.raises(ValueError, match='immutable'): db.flush()
        db.rollback()
    assert legacy_post(api, legacy_payload(gym_id=1, version=2, days=4)).status_code == 409


@pytest.mark.parametrize('changes,code', [
    ({'effective_from': NOW.isoformat()}, 422),
    ({'effective_from': (NOW - timedelta(days=1)).isoformat()}, 422),
    ({'effective_from': '2030-01-01T00:00:00'}, 422),
    ({'expected_effective_version_id': 999}, 409),
    ({'gym_id': 999}, 404), ({'gym_id': None}, 422), ({'expected_version': 1}, 409),
])
def test_invalid_or_stale_requests(api, changes, code):
    response = post(api, {**payload(), **changes})
    assert response.status_code == code, response.text


def test_legacy_contract_needs_explicit_replacement_and_remains_unchanged(api, monkeypatch):
    legacy = legacy_post(api, legacy_payload()).json()
    monkeypatch.setattr(service, 'utcnow', lambda: NOW + timedelta(days=2))
    monkeypatch.setattr(agreements, 'utcnow', lambda: NOW + timedelta(days=2))
    data = api[0].get(PATH + '?mode=test&gym_id=1', headers=api[1][5]).json()
    assert data['legacy_replacement_required'] and data['effective']['id'] == legacy['id']
    body = {**payload(), 'expected_effective_version_id': legacy['id'], 'effective_from': (NOW + timedelta(days=3)).isoformat()}
    assert post(api, body).status_code == 409
    response = post(api, {**body, 'acknowledge_legacy_replacement': True})
    assert response.status_code == 200, response.text
    with Session(api[2]) as db:
        assert db.get(FinancialAgreementVersion, legacy['id']).terms == legacy['terms']
        assert agreements.resolve(db, 'test', 1, NOW + timedelta(days=2)).id == legacy['id']
        assert agreements.resolve(db, 'test', 2, NOW + timedelta(days=4)).id == legacy['id']


def test_new_gym_initializes_both_environments_atomically_and_is_idempotent(api):
    with Session(api[2]) as db:
        gym = GymService(db).create_gym(owner_user_id=1, data={'name': 'Independent defaults'})
        identifier = gym.id
        service.initialize_new_gym(db, gym, 1); db.commit()
        for mode in ('test', 'live'):
            row = agreements.resolve(db, mode, identifier, NOW)
            assert row.terms == {service.KEY: service.defaults()}
            assert row.actor_id == 1 and row.ca_status == 'PENDING'
        assert db.scalar(select(func.count(FinancialAgreementVersion.id))) == 2
        assert agreements.resolve(db, 'test', 1, NOW) is None  # No existing-gym backfill.
    response = api[0].post('/api/v1/gym-owner/gyms', headers=api[1][1], json={'name': 'API-created gym'})
    assert response.status_code == 200, response.text
    with Session(api[2]) as db:
        assert db.scalar(select(func.count(FinancialAgreementVersion.id))) == 4


def test_new_gym_rolls_back_if_second_environment_initialization_fails(api, monkeypatch):
    original = service.lock_root
    def fail_live(db, mode):
        if mode == 'live': raise HTTPException(409, 'Simulated missing environment')
        return original(db, mode)
    monkeypatch.setattr(service, 'lock_root', fail_live)
    with Session(api[2]) as db:
        with pytest.raises(HTTPException):
            GymService(db).create_gym(owner_user_id=1, data={'name': 'Must roll back'})
        assert db.scalar(select(Gym).where(Gym.name == 'Must roll back')) is None
        assert db.scalar(select(func.count(FinancialAgreementVersion.id))) == 0
        assert db.scalar(select(func.count(FinancialAgreementScope.id))) == 2


def test_concurrent_settings_updates_only_one_wins(api):
    barrier = Barrier(2)
    def save(key):
        with Session(api[2]) as db:
            db.scalar(select(func.count(FinancialAgreementScope.id)))
            barrier.wait(timeout=15)
            try: return service.create(db, 5, SettingsCreate(**payload()), key)['version']
            except HTTPException as error: return error.status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(save, ['concurrent-settings-one', 'concurrent-settings-two']))
    assert sorted(results) == [1, 409]


def test_new_gym_missing_schema_fails_without_partial_creation(api, monkeypatch):
    monkeypatch.setattr(agreements, 'available', lambda db: False)
    with Session(api[2]) as db:
        with pytest.raises(HTTPException) as error:
            GymService(db).create_gym(owner_user_id=1, data={'name': 'Missing schema gym'})
        assert error.value.status_code == 503
        assert db.scalar(select(Gym).where(Gym.name == 'Missing schema gym')) is None


def test_editing_new_gym_defaults_does_not_change_other_gym_or_environment(api):
    with Session(api[2]) as db:
        first = GymService(db).create_gym(owner_user_id=1, data={'name': 'First independent gym'})
        second = GymService(db).create_gym(owner_user_id=1, data={'name': 'Second independent gym'})
        first_id, second_id = first.id, second.id
        original = agreements.resolve(db, 'test', first_id, NOW)
        original_id = original.id
    body = {**payload(), 'gym_id': first_id, 'expected_version': 1, 'expected_effective_version_id': original_id}
    body['settings']['single_gym']['gateway_fee'] = {'gym_percent': '100', 'fitigo_percent': '0'}
    response = post(api, body); assert response.status_code == 200, response.text
    with Session(api[2]) as db:
        at = NOW + timedelta(days=2)
        assert agreements.resolve(db, 'test', first_id, at).terms[service.KEY]['single_gym']['gateway_fee']['gym_percent'] == '100'
        for mode, identifier in [('live', first_id), ('test', second_id), ('live', second_id)]:
            assert agreements.resolve(db, mode, identifier, at).terms[service.KEY] == service.defaults()
        assert db.get(FinancialAgreementVersion, original_id).terms[service.KEY] == service.defaults()
