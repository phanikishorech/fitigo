from datetime import timedelta
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import event,select,func
from sqlalchemy.orm import Session
from app.core.security import create_access_token
from app.database.session import get_db
from app.routers.admin_marketplace import router
from app.models.owner_payout import OwnerPayout
from app.models.marketplace_allocation import MarketplaceAllocation
from app.services.marketplace_reconciliation import report
from test_customer_policy_mysql import database
from test_owner_payout_workflow_mysql import prepared


def test_payout_api_permissions_versions_and_exact_money(prepared):
    engine,now,identifier=prepared
    app=FastAPI();app.include_router(router,prefix='/api/v1/admin')
    def session():
        with Session(engine) as db:yield db
    app.dependency_overrides[get_db]=session
    admin={'Authorization':'Bearer '+create_access_token('3'),'Idempotency-Key':'api-create-key'}
    customer={'Authorization':'Bearer '+create_access_token('1')}
    body={'items':[{'allocation_id':identifier,'amount':'84.00'}],'reason':'Approved source review'}
    with TestClient(app) as client:
        path='/api/v1/admin/marketplace/payouts'
        assert client.post(path,json=body).status_code==401
        assert client.post(path,json=body,headers={**customer,'Idempotency-Key':'api-create-key'}).status_code==403
        response=client.post(path,json=body,headers=admin);assert response.status_code==200,response.text
        data=response.json();assert data['amount']=='84.00' and data['status']=='PENDING_APPROVAL'
        assert response.headers['cache-control']=='no-store'
        assert client.post(path,json=body,headers=admin).json()['id']==data['id']
        assert client.get(path+'/'+data['id']+'?mode=live',headers=admin).status_code==404
        transition={'expected_version':99,'status':'APPROVED','reason':'Approval reason'}
        r=client.post(path+'/'+data['id']+'/transition',json=transition,headers={**admin,'Idempotency-Key':'bad-version-key'})
        assert r.status_code==409 and r.json()['detail']['code']=='VERSION_CONFLICT'
        transition['expected_version']=1
        r=client.post(path+'/'+data['id']+'/transition',json=transition,headers={**admin,'Idempotency-Key':'approve-api-key'})
        assert r.status_code==200 and r.json()['payment_reference'] is None
        detail=client.get(path+'/'+data['id']+'?mode=test',headers=admin).json()
        assert len(detail['history'])==2


def test_historical_review_does_not_mutate_sources_or_allocate(prepared):
    engine,now,identifier=prepared
    writes=[]
    def spy(conn,cursor,statement,parameters,context,executemany):
        if statement.lstrip().upper().startswith(('INSERT','UPDATE','DELETE')):writes.append(statement)
    event.listen(engine,'before_cursor_execute',spy)
    try:
        with Session(engine) as db:
            before=db.scalar(select(func.count(MarketplaceAllocation.id)))
            data=report(db,'test')
            assert data['read_only'] and data['historical_adjustments_enabled'] is False
            assert db.scalar(select(func.count(MarketplaceAllocation.id)))==before
            assert db.scalar(select(func.count(OwnerPayout.id)))==0
        assert writes==[]
    finally:event.remove(engine,'before_cursor_execute',spy)