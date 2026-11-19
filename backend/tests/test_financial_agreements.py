"""Versioned agreements on disposable MySQL; no working records or payment calls."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from threading import Barrier
from uuid import uuid4
import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from fastapi import HTTPException
from sqlalchemy import event, func, select, text
from sqlalchemy.orm import Session
from app.models.auth import Role, UserRole
from app.models.financial_agreement import FinancialAgreementScope, FinancialAgreementVersion
from app.schemas.financial_agreement import AgreementCreate
from app.services import financial_agreements as service
from test_owner_dashboard_mysql import mysql_api, pytestmark

NOW = datetime(2026, 11, 12, 12, tzinfo=timezone.utc)


def migration_module():
    path = Path(__file__).resolve().parents[1] / 'alembic/versions/d46e70ba9268_financial_agreements.py'
    spec = spec_from_file_location('agreement_migration', path)
    module = module_from_spec(spec); spec.loader.exec_module(module)
    return module


@pytest.fixture
def configured_api(mysql_api, monkeypatch):
    from app.routers.admin import router
    client, headers, engine = mysql_api
    client.app.include_router(router, prefix='/api/v1')
    monkeypatch.setattr(service, 'utcnow', lambda: NOW)
    with Session(engine) as db:
        db.add(Role(id=2, name='ADMIN')); db.flush(); db.add(UserRole(user_id=5, role_id=2))
        for mode in ('test', 'live'):
            db.add(FinancialAgreementScope(mode=mode, scope_key='DEFAULT', template=deepcopy(migration_module().INITIAL_PROPOSAL)))
        db.commit()
    return client, headers, engine


def payload(*, gym_id=None, mode='test', version=0, days=1, **updates):
    return {'mode': mode, 'gym_id': gym_id, 'expected_version': version,
        'effective_from': (NOW+timedelta(days=days)).isoformat(), 'effective_to': None,
        'action': 'AGREEMENT', 'terms': deepcopy(migration_module().INITIAL_PROPOSAL),
        'agreement_reference': 'Signed agreement fixture', 'reason': 'Initial configured agreement',
        'ca_status': 'PENDING', 'ca_reference': None, 'acknowledge_configuration_only': True, **updates}


def post(api, body, key=None, actor=5):
    return api[0].post('/api/v1/admin/financial-agreements', headers={**api[1][actor],
        'Idempotency-Key': key or str(uuid4())}, json=body)


def test_proposal_is_database_data_not_an_active_contract(configured_api):
    client,headers,engine=configured_api
    response=client.get('/api/v1/admin/financial-agreements?mode=test',headers=headers[5])
    assert response.status_code==200,response.text
    data=response.json();assert data['effective'] is None and data['latest_version']==0
    assert data['template']['attended']=={'gym_percent':'85.00','fitigo_percent':'15.00'}
    assert data['template']['no_show']=={'gym_percent':'70.00','fitigo_percent':'30.00'}
    assert data['template']['settlements']['minimum_payout']=='500.00'
    assert data['template']['multi_gym']['payout_per_visit'] is None
    assert data['statutory_reporting_enabled'] is data['posting_enabled'] is False
    assert response.headers['cache-control']=='no-store'
    with Session(engine) as db:assert db.scalar(select(func.count(FinancialAgreementVersion.id)))==0


def test_create_retry_history_and_no_retroactive_rewrite(configured_api,monkeypatch):
    body=payload();first=post(configured_api,body,'same-request-key')
    assert first.status_code==200,first.text
    row=first.json();assert row['version']==1 and row['state']=='SCHEDULED'
    monkeypatch.setattr(service,'utcnow',lambda:NOW+timedelta(days=2))
    assert post(configured_api,body,'same-request-key').json()['id']==row['id']
    changed=payload(version=1,days=3);changed['terms']['attended']={'gym_percent':'80.25','fitigo_percent':'19.75'}
    second=post(configured_api,changed);assert second.status_code==200,second.text
    with Session(configured_api[2]) as db:
        assert service.resolve(db,'test',1,NOW+timedelta(days=2)).id==row['id']
        assert service.resolve(db,'test',1,NOW+timedelta(days=4)).id==second.json()['id']
        assert db.get(FinancialAgreementVersion,row['id']).terms['attended']['gym_percent']=='85.00'
        assert db.get(FinancialAgreementVersion,row['id']).effective_to is None
    assert post(configured_api,payload(version=2,days=1)).status_code==422
    assert post(configured_api,payload(version=2,days=3)).status_code==409


def test_override_inheritance_expiry_environment_and_ca_gate(configured_api):
    standard=post(configured_api,payload());assert standard.status_code==200
    body=payload(gym_id=1,days=2,effective_to=(NOW+timedelta(days=4)).isoformat(),ca_status='RECORDED_APPROVAL',ca_reference='CA-approved-reference')
    body['terms']['no_show']={'gym_percent':'60.00','fitigo_percent':'40.00'}
    body['terms']['multi_gym']={'payout_per_visit':'75.50','visits_per_member_month':20,'payout_cap_per_member_month':'1000.00'}
    custom=post(configured_api,body);assert custom.status_code==200,custom.text
    assert custom.json()['statutory_reporting_enabled'] is False
    with Session(configured_api[2]) as db:
        assert service.resolve(db,'test',1,NOW+timedelta(days=1)).id==standard.json()['id']
        assert service.resolve(db,'test',1,NOW+timedelta(days=2)).id==custom.json()['id']
        assert service.resolve(db,'test',2,NOW+timedelta(days=2)).id==standard.json()['id']
        assert service.resolve(db,'test',1,NOW+timedelta(days=4)).id==standard.json()['id']
        assert service.resolve(db,'live',1,NOW+timedelta(days=4)) is None
    inherit=post(configured_api,payload(gym_id=1,version=1,days=3,action='INHERIT',terms=None))
    assert inherit.status_code==200,inherit.text
    with Session(configured_api[2]) as db:
        assert service.resolve(db,'test',1,NOW+timedelta(days=3)).id==standard.json()['id']
        assert service.resolve(db,'test',1,NOW+timedelta(days=2)).id==custom.json()['id']


@pytest.mark.parametrize('changes', [
    {'effective_from': '2026-11-13T10:00:00'}, {'effective_from': NOW.isoformat()},
    {'effective_from': (NOW-timedelta(days=1)).isoformat()}, {'effective_to': NOW.isoformat()},
    {'expected_version': True}, {'mode':'mixed'}, {'gym_id':0}, {'reason':'  '},
    {'ca_status':'RECORDED_APPROVAL'}, {'ca_reference':'unapproved'},
    {'acknowledge_configuration_only':False}, {'statutory_reporting_enabled':True},
    {'effective_from':'9999-12-31T23:59:59-12:00'},
    {'action':'INHERIT','terms':None},
])
def test_invalid_contract_metadata_rejected(configured_api,changes):
    response=post(configured_api,payload(**changes));assert response.status_code==422,response.text


@pytest.mark.parametrize('path,value', [
    (('attended','gym_percent'),'85.001'), (('no_show','fitigo_percent'),'20'),
    (('single_gym','gym_percent'),'-1'), (('attended','gym_percent'),'NaN'),
    (('multi_gym','payout_per_visit'),'-1'), (('multi_gym','visits_per_member_month'),1.5),
    (('multi_gym','visits_per_member_month'),True), (('settlements','minimum_payout'),'1.001'),
    (('settlements','admin_approval_required'),False),
])
def test_invalid_terms_rejected(configured_api,path,value):
    data=payload();data['terms'][path[0]][path[1]]=value
    assert post(configured_api,data).status_code==422


def test_stale_save_key_conflict_and_authorization(configured_api):
    api=configured_api
    assert post(api,payload(),actor=1).status_code==403
    assert api[0].get('/api/v1/admin/financial-agreements?mode=test',headers=api[1][1]).status_code==403
    assert api[0].get('/api/v1/admin/financial-agreements?mode=test').status_code==401
    assert post(api,payload(),'request-0001').status_code==200
    assert post(api,payload(reason='Different request'),'request-0001').status_code==409
    assert post(api,payload(days=2)).status_code==409
    assert post(api,payload(gym_id=999)).status_code==404
    assert api[0].put('/api/v1/admin/financial-agreements',headers=api[1][5],json=payload()).status_code==405


def test_mysql_concurrent_admin_changes_only_one_wins(configured_api):
    barrier=Barrier(2);engine=configured_api[2]
    def save(key):
        with Session(engine) as db:
            # Establish an earlier repeatable-read snapshot as auth does.
            db.scalar(select(func.count(FinancialAgreementScope.id)))
            barrier.wait(timeout=15)
            try:return service.create(db,5,AgreementCreate(**payload(gym_id=1)),key)['version']
            except HTTPException as error:return error.status_code
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(save,['concurrent-one','concurrent-two']))
    assert sorted(results)==[1,409]
    with Session(engine) as db:assert db.scalar(select(func.count(FinancialAgreementVersion.id)))==1


def test_history_immutable_and_reads_no_writes(configured_api):
    result=post(configured_api,payload()).json();engine=configured_api[2]
    with Session(engine) as db:
        row=db.get(FinancialAgreementVersion,result['id']);row.reason='Rewrite'
        with pytest.raises(ValueError,match='immutable'):db.commit()
        db.rollback();db.delete(db.get(FinancialAgreementVersion,result['id']))
        with pytest.raises(ValueError,match='immutable'):db.commit()
        db.rollback()
    writes=[]
    def spy(conn,cursor,statement,parameters,context,executemany):
        if statement.lstrip().upper().startswith(('INSERT','UPDATE','DELETE')):writes.append(statement)
    event.listen(engine,'before_cursor_execute',spy)
    try:
        data=configured_api[0].get('/api/v1/admin/financial-agreements?mode=test',headers=configured_api[1][5]).json()
        assert data['history'][0]['reason']=='Initial configured agreement'
        assert writes==[]
    finally:event.remove(engine,'before_cursor_execute',spy)


def test_migration_preserves_data_and_refuses_history_loss(configured_api,monkeypatch):
    module=migration_module();engine=configured_api[2]
    child_path=Path(__file__).resolve().parents[1]/'alembic/versions/e57f81cb0379_policy_evidence_pins.py'
    spec=spec_from_file_location('policy_pin_child',child_path);child=module_from_spec(spec);spec.loader.exec_module(child)
    source_path=Path(__file__).resolve().parents[1]/'alembic/versions/f68a92dc1480_source_evidence.py'
    spec=spec_from_file_location('source_child',source_path);source=module_from_spec(spec);spec.loader.exec_module(source)
    with engine.begin() as connection:
        before=connection.scalar(text('SELECT COUNT(*) FROM users'))
        monkeypatch.setattr(module,'op',Operations(MigrationContext.configure(connection)))
        monkeypatch.setattr(child,'op',Operations(MigrationContext.configure(connection)))
        monkeypatch.setattr(source,'op',Operations(MigrationContext.configure(connection)))
        from allocation_migration_helper import allocation_migration
        allocation=allocation_migration(connection)
        allocation.downgrade();source.downgrade();child.downgrade();module.downgrade();module.upgrade();child.upgrade();source.upgrade();allocation.upgrade()
        assert connection.scalar(text('SELECT COUNT(*) FROM users'))==before
        assert connection.scalar(text('SELECT COUNT(*) FROM financial_agreement_scopes'))==2
        assert connection.scalar(text('SELECT COUNT(*) FROM financial_agreement_versions'))==0
    assert post(configured_api,payload()).status_code==200
    with engine.begin() as connection:
        monkeypatch.setattr(module,'op',Operations(MigrationContext.configure(connection)))
        with pytest.raises(RuntimeError,match='audit history'):module.downgrade()


def test_missing_schema_is_visible_and_writes_fail_closed(configured_api,monkeypatch):
    monkeypatch.setattr(service,'available',lambda db:False)
    client,headers,engine=configured_api
    data=client.get('/api/v1/admin/financial-agreements?mode=test',headers=headers[5]).json()
    assert data['available'] is False and data['template'] is None
    assert 'd46e70ba9268' in data['reason']
    assert post(configured_api,payload()).status_code==503
    with Session(engine) as db:assert db.scalar(select(func.count(FinancialAgreementVersion.id)))==0


def test_ist_timestamp_is_normalized_and_default_gaps_do_not_revive_old_terms(configured_api):
    body=payload(effective_from='2026-11-14T05:30:00+05:30',effective_to='2026-11-15T05:30:00+05:30')
    result=post(configured_api,body);assert result.status_code==200,result.text
    with Session(configured_api[2]) as db:
        row=db.get(FinancialAgreementVersion,result.json()['id'])
        assert row.effective_from==datetime(2026,11,14)
        assert service.resolve(db,'test',1,datetime(2026,11,14,tzinfo=timezone.utc)).id==row.id
        assert service.resolve(db,'test',1,datetime(2026,11,15,tzinfo=timezone.utc)) is None