from typing import Literal
from fastapi import APIRouter,Depends,Header,HTTPException,Query,Response
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.core.dependencies import require_role
from app.database.session import get_db
from app.models.auth import User
from app.models.financial_review import FinancialReviewEvent
from app.models.source_evidence import SourceEvidence
from app.schemas.financial_review import ReviewCreate,ReviewDecision,ReviewExecution
from app.services import financial_readiness,financial_reviews
from app.services.marketplace_calculation import AllocationBlocked
from app.routers.admin_marketplace import encode

router=APIRouter(prefix='/financial-reconciliation')
admin=require_role({'ADMIN','SUPER_ADMIN'})
View=Literal['individual','single_gym','no_show','multi_gym','fees','sources','collections','balances','corrections']


@router.get('')
def report(response:Response,mode:Literal['test','live'],view:View='sources',gym_id:int|None=Query(None,gt=0),
           limit:int=Query(20,ge=1,le=100),offset:int=Query(0,ge=0),db:Session=Depends(get_db),user:User=Depends(admin)):
    response.headers['Cache-Control']='no-store'
    return encode(financial_readiness.report(db,mode=mode,view=view,gym_id=gym_id,limit=limit,offset=offset))


@router.get('/reviews')
def reviews(response:Response,mode:Literal['test','live'],gym_id:int|None=Query(None,gt=0),limit:int=Query(20,ge=1,le=100),
            offset:int=Query(0,ge=0),db:Session=Depends(get_db),user:User=Depends(admin)):
    response.headers['Cache-Control']='no-store'
    return encode(financial_reviews.list_cases(db,mode,gym_id,limit,offset))


@router.get('/records/{kind}/{identifier}')
def record(kind:Literal['source','allocation','month','fee_budget'],identifier:str,response:Response,
           mode:Literal['test','live'],db:Session=Depends(get_db),user:User=Depends(admin)):
    from sqlalchemy import inspect
    from app.models.marketplace_allocation import MarketplaceAllocation
    from app.models.gym_visit_payout import GymMonthlyCalculation,MembershipVisitFee
    response.headers['Cache-Control']='no-store'
    model={'source':SourceEvidence,'allocation':MarketplaceAllocation,'month':GymMonthlyCalculation,'fee_budget':MembershipVisitFee}[kind]
    if not inspect(db.connection()).has_table(model.__tablename__):raise HTTPException(503,'Required financial evidence schema is not deployed.')
    row=db.get(model,identifier)
    if not row or row.mode!=mode:raise HTTPException(404,'Record not found in this environment.')
    snapshot=row.payload if kind=='source' else row.calculation_snapshot if kind=='allocation' else row.snapshot
    fingerprint=row.payload_hash if kind=='source' else row.calculation_hash if kind=='allocation' else row.snapshot_hash
    return encode({'id':identifier,'kind':kind,'mode':mode,'snapshot':snapshot,'snapshot_hash':fingerprint,
        'integrity_valid':financial_reviews.digest(snapshot)==fingerprint,'read_only':True})


@router.get('/reviews/{case_id}')
def detail(case_id:str,response:Response,mode:Literal['test','live'],db:Session=Depends(get_db),user:User=Depends(admin)):
    response.headers['Cache-Control']='no-store';financial_reviews.require_schema(db)
    row=financial_reviews.latest(db,case_id)
    if not row or row.mode!=mode:raise HTTPException(404,'Review not found.')
    source=db.get(SourceEvidence,row.source_evidence_id)
    current=financial_reviews.impact(db,source,row.gym_id)
    history=list(db.scalars(select(FinancialReviewEvent).where(FinancialReviewEvent.case_id==case_id).order_by(FinancialReviewEvent.revision)))
    return encode({'case':financial_reviews.present(row),'impact':current,'impact_hash':financial_reviews.digest(current),
        'history':[financial_reviews.present(r) for r in history],'execution_enabled':False})


def mutate(db,operation):
    try:
        result=operation();db.commit();return encode(financial_reviews.present(result))
    except AllocationBlocked as error:
        db.rollback();raise HTTPException(409,{'code':error.code,'message':str(error)}) from None
    except Exception:db.rollback();raise


@router.post('/reviews')
def create(body:ReviewCreate,response:Response,idempotency_key:str=Header(...,alias='Idempotency-Key',min_length=8,max_length=64,pattern=r'^[A-Za-z0-9_-]+$'),
           db:Session=Depends(get_db),user:User=Depends(admin)):
    response.headers['Cache-Control']='no-store'
    return mutate(db,lambda:financial_reviews.create(db,user.id,body,idempotency_key))


@router.post('/reviews/{case_id}/decisions')
def decide(case_id:str,body:ReviewDecision,response:Response,idempotency_key:str=Header(...,alias='Idempotency-Key',min_length=8,max_length=64,pattern=r'^[A-Za-z0-9_-]+$'),
           db:Session=Depends(get_db),user:User=Depends(admin)):
    response.headers['Cache-Control']='no-store'
    return mutate(db,lambda:financial_reviews.decide(db,user.id,case_id,body,idempotency_key))


@router.post('/reviews/{case_id}/execute')
def execute(case_id:str,body:ReviewExecution,response:Response,idempotency_key:str=Header(...,alias='Idempotency-Key',min_length=8,max_length=64,pattern=r'^[A-Za-z0-9_-]+$'),
            db:Session=Depends(get_db),user:User=Depends(admin)):
    response.headers['Cache-Control']='no-store'
    return mutate(db,lambda:financial_reviews.execute(db,user.id,case_id,body,idempotency_key))