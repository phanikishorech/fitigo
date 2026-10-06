"""Authoritative role/session contract, isolated from the configured database."""
import pytest
from sqlalchemy import select, delete
from sqlalchemy.orm import Session
from app.models.auth import Role, User, UserRole
from app.core.security import create_access_token
from app.services.otp_service import OtpService
from test_password_recovery import api, OLD, login


@pytest.mark.parametrize('role',['CUSTOMER','USER','GYM_OWNER','GYM_STAFF','ADMIN','SUPER_ADMIN'])
def test_login_and_session_report_database_roles(api,role):
    client,engine,_=api
    with Session(engine) as db:
        row=db.scalars(select(Role).where(Role.name==role)).first()
        if row is None:
            row=Role(name=role);db.add(row);db.flush()
        db.execute(delete(UserRole).where(UserRole.user_id==1))
        db.add(UserRole(user_id=1,role_id=row.id));db.commit()
    result=login(client)
    assert result['roles']==[role]
    assert result['user']['id']==1
    assert 'password_hash' not in result['user']
    response=client.get('/api/v1/auth/session',headers={'Authorization':f'Bearer {result["access_token"]}'})
    assert response.status_code==200
    assert response.json()['roles']==[role]


def test_session_reloads_changed_roles_not_token_claims_or_email(api):
    client,engine,_=api
    token=login(client)['access_token']
    with Session(engine) as db:
        db.execute(delete(UserRole).where(UserRole.user_id==1))
        db.add(UserRole(user_id=1,role_id=2));db.commit()
    result=client.get('/api/v1/auth/session',headers={'Authorization':f'Bearer {token}'}).json()
    assert result['roles']==['GYM_OWNER']
    assert result['user']['email']=='user-1@example.com'


def test_missing_roles_and_inactive_sessions_are_not_fabricated(api):
    client,engine,_=api
    with Session(engine) as db:
        db.execute(delete(UserRole).where(UserRole.user_id==1));db.commit()
    result=login(client);assert result['roles']==[]
    headers={'Authorization':f'Bearer {result["access_token"]}'}
    assert client.get('/api/v1/auth/session',headers=headers).json()['roles']==[]
    with Session(engine) as db:
        db.get(User,1).status='INACTIVE';db.commit()
    assert client.get('/api/v1/auth/session',headers=headers).status_code==403
    assert client.get('/api/v1/auth/session').status_code==401
    assert client.get('/api/v1/auth/session',headers={'Authorization':'Bearer invalid'}).status_code==401


def test_otp_login_includes_same_role_contract(api,monkeypatch):
    client,_,_=api
    monkeypatch.setattr(OtpService,'_email_store',{})
    monkeypatch.setattr(OtpService,'_generate_otp',lambda self:'654321')
    assert client.post('/api/v1/auth/email/send-otp',json={'email':'user-2@example.com'}).status_code==200
    response=client.post('/api/v1/auth/email/verify-otp',json={'email':'user-2@example.com','otp':'654321'})
    assert response.status_code==200
    assert response.json()['roles']==['GYM_OWNER']