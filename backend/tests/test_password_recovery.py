"""All users, credentials, reset mail and session data are isolated fixtures."""
from datetime import datetime, timedelta, timezone
import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Integer, MetaData, create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from app.core.config import settings
from app.core.dependencies import get_current_user, get_optional_user
from app.core.security import create_access_token, hash_password, verify_password
from app.database.base import Base
from app.database.session import get_db
from app.models.auth import User, Role, UserRole, PasswordResetToken, RefreshToken, AuthRateLimit
from app.routers.auth import router
from app.services import password_service

OLD = 'Original Password 123!'
NEW = 'A different Password 456!'


@pytest.fixture
def api(monkeypatch):
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    metadata = MetaData()
    for name in ('users','roles','user_roles','refresh_tokens','password_reset_tokens','auth_rate_limits'):
        table = Base.metadata.tables[name].to_metadata(metadata)
        if 'id' in table.c:
            table.c.id.type = Integer()
    metadata.create_all(engine)
    with Session(engine) as db:
        for uid, role in enumerate(('CUSTOMER','GYM_OWNER','GYM_STAFF'), 1):
            db.add(Role(id=uid,name=role))
            db.add(User(id=uid,email=f'user-{uid}@example.com',password_hash=hash_password(OLD),status='ACTIVE'))
            db.add(UserRole(user_id=uid,role_id=uid))
        db.commit()
    app = FastAPI(); app.include_router(router,prefix='/api/v1')
    @app.get('/identity')
    def identity(user=Depends(get_current_user)):
        return {'id':user.id}
    @app.get('/optional-identity')
    def optional_identity(user=Depends(get_optional_user)):
        return {'id': user.id if user else None}
    def dependency():
        with Session(engine) as db:
            yield db
    app.dependency_overrides[get_db] = dependency
    monkeypatch.setattr(settings,'smtp_host','smtp.example.test')
    monkeypatch.setattr(settings,'smtp_from','no-reply@example.com')
    monkeypatch.setattr(settings,'password_reset_frontend_url','https://app.example.test/auth/reset-password')
    mail=[]
    monkeypatch.setattr(password_service,'send_reset_email',lambda address,token:mail.append((address,token)))
    with TestClient(app) as client:
        yield client,engine,mail
    engine.dispose()


def login(client,uid=1,password=OLD):
    response=client.post('/api/v1/auth/login',json={'email':f'user-{uid}@example.com','password':password})
    assert response.status_code==200,response.text
    return response.json()


@pytest.mark.parametrize('uid',[1,2,3])
def test_change_requires_current_password_and_revokes_all_sessions(api,uid):
    client,engine,_=api
    sessions=[login(client,uid),login(client,uid)]
    assert sessions[0]['refresh_token']!=sessions[1]['refresh_token']
    headers={'Authorization':f'Bearer {sessions[0]["access_token"]}'}
    payload={'current_password':OLD,'new_password':NEW}
    assert client.post('/api/v1/auth/change-password',json=payload).status_code==401
    assert client.post('/api/v1/auth/change-password',headers=headers,json={**payload,'current_password':'incorrect'}).status_code==400
    assert client.post('/api/v1/auth/change-password',headers=headers,json={**payload,'new_password':'short'}).status_code==422
    assert client.post('/api/v1/auth/change-password',headers=headers,json={**payload,'new_password':OLD}).status_code==400
    assert client.post('/api/v1/auth/change-password',headers=headers,json=payload).status_code==200
    for session in sessions:
        assert client.get('/identity',headers={'Authorization':f'Bearer {session["access_token"]}'}).status_code==401
        assert client.get('/optional-identity',headers={'Authorization':f'Bearer {session["access_token"]}'}).status_code==401
        assert client.post('/api/v1/auth/refresh',json={'refresh_token':session['refresh_token']}).status_code==401
    assert client.get('/identity',headers={'Authorization':f'Bearer {create_access_token(str(uid))}'}).status_code==401
    assert client.post('/api/v1/auth/login',json={'email':f'user-{uid}@example.com','password':OLD}).status_code==401
    fresh=login(client,uid,NEW)
    assert client.get('/identity',headers={'Authorization':f'Bearer {fresh["access_token"]}'}).status_code==200
    assert client.get('/optional-identity').json()=={'id':None}
    with Session(engine) as db:
        assert verify_password(NEW,db.get(User,uid).password_hash)
        assert db.get(User,uid).token_version==1
        assert verify_password(OLD,db.get(User,2 if uid!=2 else 1).password_hash)


def test_reset_generic_response_hashed_expiring_one_time_and_session_revocation(api):
    client,engine,mail=api
    session=login(client)
    known=client.post('/api/v1/auth/forgot-password',json={'email':'USER-1@example.com'})
    unknown=client.post('/api/v1/auth/forgot-password',json={'email':'unknown@example.com'})
    assert known.status_code==unknown.status_code==200
    assert known.json()==unknown.json()
    assert len(mail)==1
    token=mail[0][1]
    assert token not in known.text
    with Session(engine) as db:
        record=db.scalars(select(PasswordResetToken)).one()
        assert record.token_hash==password_service.digest(token)
        assert record.token_hash!=token
    assert client.post('/api/v1/auth/reset-password',json={'token':'x'*43,'new_password':NEW}).status_code==400
    result=client.post('/api/v1/auth/reset-password',json={'token':token,'new_password':NEW})
    assert result.status_code==200,result.text
    assert client.post('/api/v1/auth/reset-password',json={'token':token,'new_password':OLD}).status_code==400
    assert client.get('/identity',headers={'Authorization':f'Bearer {session["access_token"]}'}).status_code==401
    assert client.post('/api/v1/auth/refresh',json={'refresh_token':session['refresh_token']}).status_code==401
    login(client,password=NEW)


def test_expired_reset_and_inactive_account_cannot_change_password(api):
    client,engine,mail=api
    client.post('/api/v1/auth/forgot-password',json={'email':'user-1@example.com'})
    with Session(engine) as db:
        db.scalars(select(PasswordResetToken)).one().expires_at=datetime.now(timezone.utc)-timedelta(seconds=1)
        db.get(User,2).status='INACTIVE';db.commit()
    assert client.post('/api/v1/auth/reset-password',json={'token':mail[0][1],'new_password':NEW}).status_code==400
    assert client.post('/api/v1/auth/forgot-password',json={'email':'user-2@example.com'}).status_code==200
    assert len(mail)==1
    login(client)


def test_missing_mail_configuration_reports_unavailable_without_fake_send(api,monkeypatch):
    client,_,mail=api
    monkeypatch.setattr(settings,'smtp_host',None)
    assert client.get('/api/v1/auth/password-reset/options').json()=={'email_available':False}
    assert client.post('/api/v1/auth/forgot-password',json={'email':'user-1@example.com'}).status_code==503
    assert mail==[]


def test_delivery_failure_does_not_expose_account_or_create_valid_token(api,monkeypatch):
    client,engine,_=api
    def fail(*args): raise RuntimeError('private SMTP diagnostic')
    monkeypatch.setattr(password_service,'send_reset_email',fail)
    a=client.post('/api/v1/auth/forgot-password',json={'email':'user-1@example.com'})
    b=client.post('/api/v1/auth/forgot-password',json={'email':'unknown@example.com'})
    assert a.json()==b.json()
    assert 'private' not in a.text
    with Session(engine) as db:
        assert db.scalars(select(PasswordResetToken)).all()==[]


def test_reset_request_throttled_for_existing_and_unknown_email(api):
    client,_,_=api
    for email in ('user-1@example.com','unknown@example.com'):
        for _ in range(3): assert client.post('/api/v1/auth/forgot-password',json={'email':email}).status_code==200
        assert client.post('/api/v1/auth/forgot-password',json={'email':email}).status_code==429


def test_customer_registration_existing_contract_and_role(api):
    client,engine,_=api
    data={'first_name':'New','last_name':'Customer','email':'new@example.com','phone':None,'password':OLD,'role':'SUPER_ADMIN'}
    created=client.post('/api/v1/auth/register/customer',json=data)
    assert created.status_code==200
    assert 'password' not in created.text
    assert client.post('/api/v1/auth/register/customer',json=data).status_code==409
    assert client.post('/api/v1/auth/login',json={'email':data['email'],'password':OLD}).status_code==200
    with Session(engine) as db:
        roles=db.scalars(select(Role.name).join(UserRole).where(UserRole.user_id==created.json()['id'])).all()
        assert roles==['CUSTOMER']


def test_reset_invalidates_all_outstanding_recovery_links(api):
    client,_,mail=api
    for _ in range(2):
        assert client.post('/api/v1/auth/forgot-password',json={'email':'user-1@example.com'}).status_code==200
    assert client.post('/api/v1/auth/reset-password',json={'token':mail[0][1],'new_password':NEW}).status_code==200
    assert client.post('/api/v1/auth/reset-password',json={'token':mail[1][1],'new_password':OLD}).status_code==400


def test_wrong_current_password_is_rate_limited(api):
    client,_,_=api
    headers={'Authorization':f'Bearer {login(client)["access_token"]}'}
    payload={'current_password':'Wrong password','new_password':NEW}
    for _ in range(5):
        assert client.post('/api/v1/auth/change-password',headers=headers,json=payload).status_code==400
    assert client.post('/api/v1/auth/change-password',headers=headers,json=payload).status_code==429


def test_smtp_uses_tls_and_fragment_link_without_password(monkeypatch):
    events=[]
    class Mail:
        def __init__(self,*args,**kwargs): events.append('connect')
        def __enter__(self): return self
        def __exit__(self,*args): pass
        def ehlo(self): events.append('ehlo')
        def starttls(self,context): events.append('tls')
        def login(self,*args): events.append('login')
        def send_message(self,message): events.append(message)
    monkeypatch.setattr(password_service.smtplib,'SMTP',Mail)
    monkeypatch.setattr(settings,'smtp_host','smtp.example.com')
    monkeypatch.setattr(settings,'smtp_from','no-reply@example.com')
    monkeypatch.setattr(settings,'password_reset_frontend_url','https://app.example.com/auth/reset-password')
    monkeypatch.setattr(settings,'smtp_security','starttls')
    monkeypatch.setattr(settings,'smtp_username','test')
    monkeypatch.setattr(settings,'smtp_password','test-only')
    password_service.send_reset_email('user-1@example.com','opaque-fixture')
    assert events[:5]==['connect','ehlo','tls','ehlo','login']
    assert '#token=opaque-fixture' in events[-1].get_content()
    assert OLD not in events[-1].get_content()


def test_password_migration_upgrade_downgrade_disposable_database():
    from importlib.util import spec_from_file_location, module_from_spec
    from pathlib import Path
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy import inspect, text
    path=Path(__file__).parents[1]/'alembic/versions/5da03e4f6b82_password_recovery.py'
    spec=spec_from_file_location('password_migration',path); migration=module_from_spec(spec);spec.loader.exec_module(migration)
    engine=create_engine('sqlite://')
    with engine.begin() as connection:
        connection.execute(text('CREATE TABLE users (id INTEGER PRIMARY KEY, password_hash VARCHAR(255))'))
        connection.execute(text("INSERT INTO users VALUES (1, 'unchanged')"))
        migration.op=Operations(MigrationContext.configure(connection))
        migration.upgrade()
        assert connection.execute(text('SELECT password_hash, token_version FROM users')).one()==('unchanged',0)
        assert 'password_reset_tokens' in inspect(connection).get_table_names()
        migration.downgrade()
        assert connection.execute(text('SELECT password_hash FROM users')).scalar()=='unchanged'
        assert 'password_reset_tokens' not in inspect(connection).get_table_names()
    engine.dispose()