from typing import Literal
from datetime import date
from fastapi import APIRouter,Depends,Header,HTTPException,Query,Response
from fastapi.encoders import jsonable_encoder
from sqlalchemy import inspect,select,func
from sqlalchemy.orm import Session
from app.core.dependencies import require_role
from app.database.session import get_db
from app.models.auth import User
from app.models.owner_payout import OwnerPayout,OwnerPayoutAudit
from app.schemas.owner_payout import PayoutCreate,PayoutTransition
from app.services import owner_payouts
from app.services.marketplace_calculation import AllocationBlocked

router=APIRouter(prefix='/marketplace')
admin=require_role({'ADMIN','SUPER_ADMIN'})


@router.get('/historical-review')
def historical_review(response:Response,mode:Literal['test','live'],limit:int=Query(50,ge=1,le=100),offset:int=Query(0,ge=0),
    db:Session=Depends(get_db),user:User=Depends(admin)):
    from app.services.marketplace_reconciliation import report
    response.headers['Cache-Control']='no-store'
    return encode(report(db,mode,limit,offset))


@router.get('/financial-summary')
def financial_summary(response:Response,mode:Literal['test','live'],date_from:date|None=None,date_to:date|None=None,
    gym_id:int|None=Query(None,gt=0),owner_user_id:int|None=Query(None,gt=0),
    category:Literal['ATTENDED_BOOKING','NO_SHOW','SINGLE_GYM','MULTI_GYM']|None=None,
    gateway:Literal['RAZORPAY','CASHFREE','WALLET']|None=None,limit:int=Query(25,ge=1,le=100),offset:int=Query(0,ge=0),
    db:Session=Depends(get_db),user:User=Depends(admin)):
    from app.services.marketplace_reporting import report
    response.headers['Cache-Control']='no-store'
    return encode(report(db,mode=mode,date_from=date_from,date_to=date_to,gym_id=gym_id,owner_user_id=owner_user_id,
        category=category,gateway=gateway,limit=limit,offset=offset))


def require_schema(db):
    if not inspect(db.connection()).has_table('owner_payouts'):
        raise HTTPException(503,'Marketplace payout migration c91dc50f4713 is not deployed.')


def encode(value):
    from decimal import Decimal
    return jsonable_encoder(value,custom_encoder={Decimal:lambda v:format(v,'.2f')})


@router.post('/payouts')
def create_payout(body:PayoutCreate,response:Response,
    idempotency_key:str=Header(...,alias='Idempotency-Key',min_length=8,max_length=64,pattern=r'^[A-Za-z0-9_-]+$'),
    db:Session=Depends(get_db),user:User=Depends(admin)):
    response.headers['Cache-Control']='no-store';require_schema(db)
    try:
        row=owner_payouts.create(db,user.id,body,idempotency_key);db.commit()
        return encode(owner_payouts.present(row))
    except AllocationBlocked as error:
        db.rollback();raise HTTPException(409,{'code':error.code,'message':str(error)}) from None
    except Exception:db.rollback();raise


@router.post('/payouts/{payout_id}/transition')
def transition_payout(payout_id:str,body:PayoutTransition,response:Response,
    idempotency_key:str=Header(...,alias='Idempotency-Key',min_length=8,max_length=64,pattern=r'^[A-Za-z0-9_-]+$'),
    db:Session=Depends(get_db),user:User=Depends(admin)):
    response.headers['Cache-Control']='no-store';require_schema(db)
    try:
        row=owner_payouts.transition(db,user.id,payout_id,body,idempotency_key);db.commit()
        return encode(owner_payouts.present(row))
    except AllocationBlocked as error:
        db.rollback();raise HTTPException(409,{'code':error.code,'message':str(error)}) from None
    except Exception:db.rollback();raise


@router.get('/payouts')
def list_payouts(response:Response,mode:Literal['test','live'],gym_id:int|None=Query(None,gt=0),
    owner_user_id:int|None=Query(None,gt=0),limit:int=Query(25,ge=1,le=100),offset:int=Query(0,ge=0),
    db:Session=Depends(get_db),user:User=Depends(admin)):
    response.headers['Cache-Control']='no-store';require_schema(db)
    query=select(OwnerPayout).where(OwnerPayout.mode==mode)
    if gym_id:query=query.where(OwnerPayout.gym_id==gym_id)
    if owner_user_id:query=query.where(OwnerPayout.owner_user_id==owner_user_id)
    total=db.scalar(select(func.count()).select_from(query.subquery()))
    return encode({'total':total,'items':[owner_payouts.present(r) for r in db.scalars(query.order_by(OwnerPayout.created_at.desc(),OwnerPayout.id).limit(limit).offset(offset))]})


@router.get('/payouts/{payout_id}')
def payout_detail(payout_id:str,response:Response,mode:Literal['test','live'],db:Session=Depends(get_db),user:User=Depends(admin)):
    response.headers['Cache-Control']='no-store';require_schema(db)
    row=db.get(OwnerPayout,payout_id)
    if not row or row.mode!=mode:raise HTTPException(404,'Payout not found.')
    history=list(db.scalars(select(OwnerPayoutAudit).where(OwnerPayoutAudit.payout_id==row.id).order_by(OwnerPayoutAudit.created_at,OwnerPayoutAudit.id)))
    return encode({'payout':owner_payouts.present(row),'history':[{'actor_id':r.actor_id,'from_status':r.from_status,
        'to_status':r.to_status,'reason':r.reason,'evidence':r.evidence,'created_at':r.created_at} for r in history]})