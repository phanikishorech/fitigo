"""Review-only state machine. Approval cannot execute corrections or release claims."""
from uuid import uuid4
from sqlalchemy import select,inspect,func
from fastapi import HTTPException
from app.core.time import stored_instant,utcnow
from app.models.gym import Gym
from app.models.source_evidence import SourceEvidence
from app.models.marketplace_allocation import MarketplaceAllocation
from app.models.gym_visit_payout import GymVisitPayout,GymMonthlyCalculation,MembershipVisitFee
from app.models.owner_payout import OwnerPayout,OwnerPayoutItem
from app.models.financial_review import FinancialReviewEvent
from app.services.marketplace_allocations import digest,verified_payload
from app.services.owner_payouts import authorize
from app.services.marketplace_calculation import block


def require_schema(db):
    if not inspect(db.connection()).has_table('financial_review_events'):
        raise HTTPException(503,'Financial review migration eb3f70126935 is not deployed.')


def impact(db,source,gym_id,*,lock=False):
    data=verified_payload(source)
    if source.evidence_status!='VERIFIED_SOURCE':block('SOURCE_DATA_MISSING','Verified source evidence is required for review.')
    if not source.checkout_id or data.get('gym_id')!=gym_id or source.mode not in {'test','live'}:
        block('SOURCE_DATA_MISMATCH','Review source gym/environment/checkout is incomplete.')
    def rows(query):
        return list(db.scalars(query.with_for_update().execution_options(populate_existing=True) if lock else query))
    visits=rows(select(GymVisitPayout).where(GymVisitPayout.checkout_id==source.checkout_id).order_by(GymVisitPayout.id))
    allocations=rows(select(MarketplaceAllocation).where(MarketplaceAllocation.checkout_id==source.checkout_id).order_by(MarketplaceAllocation.id))
    # A month rounding correction may affect other memberships' allocations too.
    periods={r.allocation_period for r in visits if r.gym_id==gym_id}
    if source.occurred_at:periods.add(source.occurred_at.date().replace(day=1))
    from app.core.time import as_ist
    if source.occurred_at:periods.add(as_ist(source.occurred_at).date().replace(day=1))
    months=rows(select(GymMonthlyCalculation).where(GymMonthlyCalculation.mode==source.mode,
        GymMonthlyCalculation.gym_id==gym_id,GymMonthlyCalculation.period.in_(periods)).order_by(GymMonthlyCalculation.period,GymMonthlyCalculation.revision))
    monthly_visits=rows(select(GymVisitPayout).where(GymVisitPayout.mode==source.mode,
        GymVisitPayout.gym_id==gym_id,GymVisitPayout.allocation_period.in_(periods)))
    visit_ids=sorted({r.id for r in visits+monthly_visits})
    checkout_ids=sorted({source.checkout_id,*[r.checkout_id for r in monthly_visits]})
    fees=rows(select(MembershipVisitFee).where(MembershipVisitFee.checkout_id.in_(checkout_ids)).order_by(MembershipVisitFee.id))
    claims_query=select(OwnerPayoutItem,OwnerPayout).join(OwnerPayout).where(OwnerPayout.mode==source.mode,
        OwnerPayout.status!='REVERSED', (OwnerPayoutItem.visit_payout_id.in_(visit_ids)) |
        (OwnerPayoutItem.allocation_id.in_([a.id for a in allocations]))).order_by(OwnerPayoutItem.id)
    claims=list(db.execute(claims_query.with_for_update().execution_options(populate_existing=True) if lock else claims_query))
    return {'source_evidence_id':source.id,'source_payload_hash':source.payload_hash,'checkout_id':source.checkout_id,
        'allocation_ids':[r.id for r in allocations],'visit_ids':visit_ids,
        'monthly_calculations':[{'id':r.id,'revision':r.revision,'hash':r.snapshot_hash} for r in months],
        'closed_fee_budgets':[{'id':r.id,'hash':r.snapshot_hash} for r in fees],
        'protected_claims':[{'item_id':i.id,'payout_id':p.id,'status':p.status,'version':p.version,'amount':str(i.amount)} for i,p in claims],
        'execution_enabled':False}


def latest(db,case_id,lock=False):
    query=select(FinancialReviewEvent).where(FinancialReviewEvent.case_id==case_id).order_by(FinancialReviewEvent.revision.desc()).limit(1)
    row=db.scalar(query.with_for_update().execution_options(populate_existing=True) if lock else query)
    if row and digest(row.snapshot)!=row.snapshot_hash:block('RECONCILIATION_REQUIRED','Review history integrity mismatch.')
    return row


def present(row):
    return {key:getattr(row,key) for key in ('id','case_id','revision','mode','gym_id','checkout_id','source_evidence_id','kind','status','actor_id','reason','snapshot','snapshot_hash','created_at')}


def create(db,actor,body,key):
    authorize(db,actor);require_schema(db)
    with db.begin_nested():
        if not db.scalar(select(Gym.id).where(Gym.id==body.gym_id).with_for_update()):raise HTTPException(404,'Gym not found.')
        fingerprint=digest({'actor':actor,'body':body.model_dump(mode='json')})
        prior=db.scalar(select(FinancialReviewEvent).where(FinancialReviewEvent.mode==body.mode,FinancialReviewEvent.request_key==key).with_for_update())
        if prior:
            if prior.request_hash!=fingerprint:block('IDEMPOTENCY_CONFLICT','Review key belongs to another request.')
            return prior
        source=db.get(SourceEvidence,body.source_evidence_id)
        if not source or source.mode!=body.mode:raise HTTPException(404,'Source evidence not found in this environment.')
        snapshot=impact(db,source,body.gym_id)
        if body.kind=='LATE_VISIT' and source.event_type!='MULTI_GYM_VISIT_VERIFIED':block('SOURCE_DATA_MISMATCH','Late visit review needs a verified admission event.')
        if body.kind=='MONTH_CORRECTION' and not snapshot['monthly_calculations']:block('SOURCE_DATA_MISSING','No finalized monthly calculation affected.')
        if body.kind=='CLOSED_FEE_BUDGET' and not snapshot['closed_fee_budgets']:block('SOURCE_DATA_MISSING','No closed membership fee budget affected.')
        if body.kind=='RESERVED_OR_PAID' and not snapshot['protected_claims']:block('SOURCE_DATA_MISSING','No reserved/paid claims affected.')
        # Do not open competing reviews for the same evidence and kind.
        duplicate=db.scalar(select(FinancialReviewEvent.id).where(FinancialReviewEvent.mode==body.mode,
            FinancialReviewEvent.source_evidence_id==source.id,FinancialReviewEvent.kind==body.kind).limit(1).with_for_update())
        if duplicate:block('REVIEW_EXISTS','A review already exists; append a decision to its history.')
        row=FinancialReviewEvent(id=str(uuid4()),case_id=str(uuid4()),revision=1,mode=body.mode,gym_id=body.gym_id,
            checkout_id=source.checkout_id,source_evidence_id=source.id,kind=body.kind,status='OPEN',actor_id=actor,
            reason=body.reason,request_key=key,request_hash=fingerprint,snapshot=snapshot,snapshot_hash=digest(snapshot),created_at=stored_instant(utcnow()))
        db.add(row);db.flush();return row


def decide(db,actor,case_id,body,key):
    authorize(db,actor);require_schema(db)
    with db.begin_nested():
        current=latest(db,case_id)
        if not current or current.mode!=body.mode:raise HTTPException(404,'Review not found.')
        db.scalar(select(Gym.id).where(Gym.id==current.gym_id).with_for_update())
        current=latest(db,case_id,True)
        fingerprint=digest({'actor':actor,'case_id':case_id,'body':body.model_dump(mode='json')})
        previous=db.scalar(select(FinancialReviewEvent).where(FinancialReviewEvent.mode==body.mode,FinancialReviewEvent.request_key==key).with_for_update())
        if previous:
            if previous.request_hash!=fingerprint:block('IDEMPOTENCY_CONFLICT','Review decision key conflict.')
            return previous
        if current.revision!=body.expected_revision:block('VERSION_CONFLICT','Review changed; reload history.')
        # This is an impact attestation only. It never grants executable authority,
        # so a later payout/source change cannot be authorized by this snapshot.
        if current.status not in {'OPEN','NEEDS_EVIDENCE'}:block('INVALID_TRANSITION','This review decision is final; no ledger execution was authorized.')
        if not body.acknowledge_no_execution:block('ACKNOWLEDGMENT_REQUIRED','Review approval does not execute financial adjustments.')
        source=db.get(SourceEvidence,current.source_evidence_id);snapshot=impact(db,source,current.gym_id)
        if digest(snapshot)!=body.expected_impact_hash:block('IMPACT_CHANGED','Affected month/fees/payouts changed; refresh review impact before deciding.')
        if snapshot['protected_claims'] and not body.acknowledge_reserved_paid:block('PROTECTED_AMOUNT_REVIEW_REQUIRED','Explicit reserved/paid impact acknowledgment required.')
        if body.status=='APPROVED_FOR_RECONCILIATION' and actor==db.scalar(select(FinancialReviewEvent.actor_id).where(FinancialReviewEvent.case_id==case_id,FinancialReviewEvent.revision==1)):
            block('INDEPENDENT_REVIEW_REQUIRED','A different Admin must approve the proposed reconciliation.')
        snapshot={**snapshot,'previous_event_id':current.id,'previous_hash':current.snapshot_hash,
            'acknowledge_reserved_paid':body.acknowledge_reserved_paid}
        row=FinancialReviewEvent(id=str(uuid4()),case_id=case_id,revision=current.revision+1,mode=current.mode,gym_id=current.gym_id,
            checkout_id=current.checkout_id,source_evidence_id=current.source_evidence_id,kind=current.kind,status=body.status,actor_id=actor,
            reason=body.reason,request_key=key,request_hash=fingerprint,snapshot=snapshot,snapshot_hash=digest(snapshot),created_at=stored_instant(utcnow()))
        db.add(row);db.flush();return row


def list_cases(db,mode,gym_id,limit,offset):
    require_schema(db)
    last=select(FinancialReviewEvent.case_id,func.max(FinancialReviewEvent.revision).label('revision')).where(FinancialReviewEvent.mode==mode).group_by(FinancialReviewEvent.case_id).subquery()
    query=select(FinancialReviewEvent).join(last,(FinancialReviewEvent.case_id==last.c.case_id)&(FinancialReviewEvent.revision==last.c.revision))
    if gym_id:query=query.where(FinancialReviewEvent.gym_id==gym_id)
    total=db.scalar(select(func.count()).select_from(query.subquery()))
    return {'items':[present(r) for r in db.scalars(query.order_by(FinancialReviewEvent.created_at.desc(),FinancialReviewEvent.id).limit(limit).offset(offset))],'total':total}


def require_undisputed(db,row,*,lock=False):
    """A recorded review never bypasses payout safety, even after review approval."""
    if not inspect(db.connection()).has_table('financial_review_events'): return
    query=select(FinancialReviewEvent).where(FinancialReviewEvent.mode==row.mode).order_by(FinancialReviewEvent.case_id,FinancialReviewEvent.revision)
    events=list(db.scalars(query.with_for_update().execution_options(populate_existing=True) if lock else query))
    cases={event.case_id:event for event in events}
    for review in cases.values():
        if digest(review.snapshot)!=review.snapshot_hash:block('RECONCILIATION_REQUIRED','Review integrity mismatch.')
        if review.status in {'REJECTED','EXECUTED'}: continue
        if review.checkout_id==row.checkout_id or row.id in review.snapshot.get('visit_ids',[]) or row.id in review.snapshot.get('allocation_ids',[]):
            block('FINANCIAL_REVIEW_OPEN','An unresolved financial review protects this entitlement. Review approval is not execution clearance.')


def execute(db,actor,case_id,body,key):
    """Explicit execution of the safe subset only; no payout/bank operation.

    Independent review approval is not execution. This appends a monthly
    invalidation revision and its execution audit in one caller-owned transaction.
    Closed fee budgets, claims, late visits and arbitrary replacement remain blocked.
    """
    from app.core.config import settings
    from app.services.owner_payouts import lock_sources
    from app.services.gym_visit_payouts import processing_gate,finalize_month
    from app.services.financial_agreements import scope
    authorize(db,actor);require_schema(db)
    if not body.authorize_execution:block('EXECUTION_AUTHORIZATION_REQUIRED','Explicit execution authorization is required.')
    if not settings.source_evidence_enabled:block('SOURCE_PROCESSING_DISABLED','Source evidence gate is disabled.')
    processing_gate(body.mode)
    with db.begin_nested():
        initial=latest(db,case_id)
        if not initial or initial.mode!=body.mode:raise HTTPException(404,'Review not found in this environment.')
        source=db.get(SourceEvidence,initial.source_evidence_id)
        if not source or source.event_type!='MULTI_GYM_VISIT_INVALIDATED' or initial.kind!='MONTH_CORRECTION':
            block('EXECUTION_NOT_SUPPORTED','Only reviewed source-backed monthly invalidations can execute. Late visits, fee-budget and paid recovery require a separately designed execution policy.')
        target=db.scalar(select(GymVisitPayout).where(GymVisitPayout.source_evidence_id==source.payload.get('original_evidence_id')))
        if not target or target.gym_id!=initial.gym_id or target.mode!=body.mode or target.checkout_id!=source.checkout_id:
            block('SOURCE_DATA_MISMATCH','Invalidation does not identify the reviewed allocation.')
        candidates=list(db.scalars(select(GymVisitPayout).where(GymVisitPayout.mode==body.mode,
            GymVisitPayout.gym_id==target.gym_id,GymVisitPayout.allocation_period==target.allocation_period)))
        lock_sources(db,candidates)
        db.scalar(select(Gym.id).where(Gym.id==initial.gym_id).with_for_update())
        scope(db,body.mode,None,lock=True)
        current=latest(db,case_id,True)
        fingerprint=digest({'actor':actor,'case_id':case_id,'body':body.model_dump(mode='json')})
        previous=db.scalar(select(FinancialReviewEvent).where(FinancialReviewEvent.mode==body.mode,FinancialReviewEvent.request_key==key).with_for_update())
        if previous:
            if previous.request_hash!=fingerprint or previous.case_id!=case_id or previous.status!='EXECUTED':
                block('IDEMPOTENCY_CONFLICT','Execution request key belongs to another action.')
            return previous
        if current.revision!=body.expected_revision:block('VERSION_CONFLICT','Review changed before execution.')
        if current.status!='APPROVED_FOR_RECONCILIATION':block('EXECUTION_NOT_APPROVED','Independent review approval required before explicit execution.')
        first=db.scalar(select(FinancialReviewEvent).where(FinancialReviewEvent.case_id==case_id,FinancialReviewEvent.revision==1).with_for_update())
        if not first or first.actor_id==current.actor_id:block('INDEPENDENT_REVIEW_REQUIRED','Approval must be independent of the proposer.')
        source=db.scalar(select(SourceEvidence).where(SourceEvidence.id==current.source_evidence_id).with_for_update().execution_options(populate_existing=True))
        fresh=impact(db,source,current.gym_id,lock=True)
        approved={k:v for k,v in current.snapshot.items() if k not in {'previous_event_id','previous_hash','acknowledge_reserved_paid'}}
        if digest(fresh)!=body.expected_impact_hash or digest(fresh)!=digest(approved):
            block('IMPACT_CHANGED','Source/financial impact changed since approval; execution refused.')
        if fresh['protected_claims']:block('PAYOUT_RESERVATION_REVIEW','Reserved/paid amounts cannot be changed by this executor.')
        if fresh['closed_fee_budgets']:block('FINALIZED_FEE_REVIEW','Closed membership fee budgets cannot be changed by this executor.')
        if db.scalar(select(GymMonthlyCalculation.id).where(GymMonthlyCalculation.source_evidence_id==source.id).with_for_update()):
            block('CORRECTION_ALREADY_POSTED','Source already has a correction outside this execution audit; reconcile explicitly.')
        # Existing source actor validation and all original financial safeguards
        # remain in the finalizer; the executor identity is recorded separately.
        result=finalize_month(db,mode=body.mode,gym_id=target.gym_id,period=target.allocation_period,
            correction_evidence_id=source.id,actor_id=source.payload.get('actor_id'))
        snapshot={'previous_event_id':current.id,'previous_hash':current.snapshot_hash,'approved_impact_hash':digest(approved),
            'rechecked_impact':fresh,'authorization_reference':body.authorization_reference,'execution_actor_id':actor,
            'monthly_calculation_id':result.id,'monthly_revision':result.revision,'monthly_hash':result.snapshot_hash,
            'financial_action':'APPEND_MONTHLY_INVALIDATION_REVISION','transfers_initiated':False}
        row=FinancialReviewEvent(id=str(uuid4()),case_id=case_id,revision=current.revision+1,mode=current.mode,gym_id=current.gym_id,
            checkout_id=current.checkout_id,source_evidence_id=current.source_evidence_id,kind=current.kind,status='EXECUTED',actor_id=actor,
            reason=body.reason,request_key=key,request_hash=fingerprint,snapshot=snapshot,snapshot_hash=digest(snapshot),created_at=stored_instant(utcnow()))
        db.add(row);db.flush();return row