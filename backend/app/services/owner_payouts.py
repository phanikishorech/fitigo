"""Allocation reservations and Admin-attested actual payments; never bank calls."""
import calendar
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal
from uuid import uuid4
from fastapi import HTTPException
from sqlalchemy import select
from app.core.config import settings
from app.core.time import IST, as_ist, stored_instant, utcnow
from app.models.auth import User,Role,UserRole
from app.models.marketplace_allocation import MarketplaceAllocation
from app.models.gym_visit_payout import GymVisitPayout
from app.models.owner_payout import OwnerPayout,OwnerPayoutItem,OwnerPayoutAudit
from app.models.financial_agreement import FinancialAgreementVersion
from app.services.marketplace_allocations import digest
from app.services.marketplace_calculation import block
from app.schemas.accounting_policy import SettlementPolicy


def authorize(db,actor_id):
    user=db.get(User,actor_id)
    allowed=db.scalar(select(UserRole.id).join(Role).where(UserRole.user_id==actor_id,Role.name.in_(['ADMIN','SUPER_ADMIN'])).limit(1))
    if not user or user.status!='ACTIVE' or not allowed:raise HTTPException(403,'Admin financial permission required.')


def gate(mode):
    if not settings.marketplace_payouts_enabled:block('PAYOUT_WORKFLOW_DISABLED','Manual payout workflow is not enabled.')
    if mode=='live' and not settings.marketplace_live_allocations_enabled:block('LIVE_PROCESSING_DISABLED','Live financial processing disabled.')


def lock_sources(db,sources):
    """Same purchaser -> gym -> booking/membership -> checkout order as mutations."""
    from app.models.gym import Gym
    from app.models.booking import Booking
    from app.models.membership import UserMembership
    from app.models.payment_checkout import PaymentCheckout
    for uid in sorted({r.customer_id for r in sources}):
        db.scalar(select(User).where(User.id==uid).with_for_update())
    for gid in sorted({r.gym_id for r in sources}):
        db.scalar(select(Gym).where(Gym.id==gid).with_for_update())
    for row in sorted(sources,key=lambda r:r.id):
        if isinstance(row,MarketplaceAllocation) and row.booking_id:
            db.scalar(select(Booking).where(Booking.id==row.booking_id).with_for_update().execution_options(populate_existing=True))
        if row.membership_id:
            db.scalar(select(UserMembership).where(UserMembership.id==row.membership_id).with_for_update().execution_options(populate_existing=True))
    for cid in sorted({r.checkout_id for r in sources}):
        db.scalar(select(PaymentCheckout).where(PaymentCheckout.id==cid).with_for_update().execution_options(populate_existing=True))


def schedule_at(row,terms,policy):
    if isinstance(row,MarketplaceAllocation) and row.category=='SINGLE_GYM':return as_ist(row.occurred_at)
    tz=IST if policy.timezone=='Asia/Kolkata' else timezone.utc
    visit=isinstance(row,GymVisitPayout)
    instant=datetime.combine(row.service_date,time.min,tzinfo=tz) if visit else as_ist(row.occurred_at).astimezone(tz)
    clock=time.fromisoformat(policy.cutoff_time)
    cycle='MONTHLY' if visit else terms['settlements']['booking_cycle']
    if cycle=='WEEKLY':
        if policy.weekly_cutoff_day is None:block('POLICY_MISSING','Weekly cutoff day is missing.')
        day=instant.date()+timedelta(days=(policy.weekly_cutoff_day-instant.weekday())%7)
        cutoff=datetime.combine(day,clock,tzinfo=tz)
        if cutoff<=instant:cutoff+=timedelta(days=7)
    elif cycle=='MONTHLY':
        if policy.monthly_cutoff_day is None or policy.short_month is None:block('POLICY_MISSING','Monthly cutoff/short-month rule is missing.')
        year,month=instant.year,instant.month
        if visit:
            month+=1
            if month==13:year+=1;month=1
        for _ in range(24):
            last=calendar.monthrange(year,month)[1]
            if policy.monthly_cutoff_day<=last or policy.short_month=='LAST_CALENDAR_DAY':
                cutoff=datetime(year,month,min(last,policy.monthly_cutoff_day),clock.hour,clock.minute,clock.second,tzinfo=tz)
                if cutoff>instant:break
            month+=1
            if month==13:year+=1;month=1
        else:block('POLICY_INVALID','Cannot resolve monthly cutoff.')
    else:block('POLICY_MISSING','Unsupported settlement frequency.')
    return cutoff+timedelta(days=policy.holding_days)


def financial_position(db,row,*,lock=False,now=None):
    """Read-only position calculation from stored entries, no financial posting."""
    from app.services.financial_reviews import require_undisputed
    require_undisputed(db,row,lock=lock)
    if isinstance(row,GymVisitPayout):return visit_position(db,row,lock=lock,now=now)
    if row.entry_kind!='ORIGINAL':block('SOURCE_NOT_ELIGIBLE','Only original entitlement roots may be reserved.')
    from app.models.payment_checkout import PaymentCheckout,PaymentAttempt
    from app.models.booking import Booking
    from app.models.membership import UserMembership
    purchase_query=select(PaymentCheckout).where(PaymentCheckout.id==row.checkout_id)
    purchase=db.scalar((purchase_query.with_for_update() if lock else purchase_query).execution_options(populate_existing=True))
    if not purchase or purchase.mode!=row.mode or purchase.status!='PAID':
        block('SOURCE_NOT_ELIGIBLE','Purchase is no longer eligible for payout; reconcile cancellation/refund first.')
    refunded=select(PaymentAttempt.id).where(PaymentAttempt.checkout_id==row.checkout_id,PaymentAttempt.refunded_amount>0).limit(1)
    if db.scalar(refunded.with_for_update() if lock else refunded):
        block('REFUND_REVIEW_REQUIRED','Refunded source cannot be paid before reversal review.')
    booking=db.get(Booking,row.booking_id) if row.booking_id else None
    member=db.get(UserMembership,row.membership_id) if row.membership_id else None
    if (booking and booking.status!='CONFIRMED') or (member and (member.status=='CANCELLED' or member.payment_status!='PAID')):
        block('SOURCE_NOT_ELIGIBLE','Entitlement source was cancelled or refunded.')
    if digest(row.calculation_snapshot)!=row.calculation_hash:block('RECONCILIATION_REQUIRED','Allocation integrity mismatch.')
    query=select(MarketplaceAllocation).where((MarketplaceAllocation.reversal_of_id==row.id)|(MarketplaceAllocation.adjustment_of_id==row.id))
    changes=list(db.scalars(query.with_for_update() if lock else query))
    if any(r.entry_kind=='REVERSAL' for r in changes):block('SOURCE_NOT_ELIGIBLE','Original allocation was reversed.')
    for change in changes:
        if digest(change.calculation_snapshot)!=change.calculation_hash:block('RECONCILIATION_REQUIRED','Adjustment integrity mismatch.')
    agreement=db.get(FinancialAgreementVersion,row.agreement_version_id)
    if not agreement or agreement.version!=row.agreement_version:block('AGREEMENT_MISSING','Pinned agreement unavailable.')
    modern = 'financial_settings' in agreement.terms
    if modern:
        if row.calculation_snapshot.get('configuration_hash') and digest(agreement.terms)!=row.calculation_snapshot['configuration_hash']:
            block('RECONCILIATION_REQUIRED','Pinned settlement configuration differs from the allocation snapshot.')
        from app.services.commercial_settlement import policy_for
        policy=policy_for(agreement.terms,row.category)
        minimum=policy.minimum_payout
    else:
        policy,minimum=legacy_settlement(agreement)
    amount=row.gym_owner_net_entitlement
    fee_rows=[change for change in changes if change.entry_kind=='FEE_ADJUSTMENT']
    if amount is None:
        if fee_rows:amount=row.gym_gross_share
        elif row.calculation_snapshot['policy']['fee_before_payout']=='ALLOW_PROVISIONAL_GROSS':amount=row.gym_gross_share
        else:block('FEE_PENDING','Actual gateway fee is pending.')
    amount+=sum((r.gym_owner_net_entitlement for r in fee_rows),Decimal(0))
    fitigo_net=row.fitigo_gross_commission-(row.fitigo_gateway_fee_share or Decimal(0))-sum((r.fitigo_gateway_fee_share or Decimal(0) for r in fee_rows),Decimal(0))
    if fitigo_net<0:block('NEGATIVE_NET_REVIEW','Negative platform net requires financial review before payout.')
    if amount<=0:block('NO_AVAILABLE_ENTITLEMENT','Nonpositive entitlement requires review.')
    from app.services.commercial_settlement import due_at
    due=due_at(row,agreement.terms,policy) if modern else schedule_at(row,agreement.terms,policy)
    claims=select(OwnerPayoutItem).join(OwnerPayout).where(OwnerPayoutItem.allocation_id==row.id,OwnerPayout.status!='REVERSED')
    reserved=sum((r.amount for r in db.scalars(claims.with_for_update() if lock else claims)),Decimal(0))
    return {'entitlement':amount,'reserved':reserved,'remaining':amount-reserved,'available_at':due,
        'status':'AVAILABLE' if as_ist(now or utcnow())>=due else 'ACCRUED',
        'policy':policy,'minimum':Decimal(str(minimum))}


def legacy_settlement(agreement):
    raw=((agreement.terms.get('policy_contract') or {}).get('settlements') or {})
    from pydantic import ValidationError
    try:policy=SettlementPolicy.model_validate(raw)
    except ValidationError:block('POLICY_INVALID','Settlement contract invalid.')
    required=('cutoff_time','timezone','holding_days','eligible_deductions','partial_settlement','failed_settlement')
    if policy.approval.status!='APPROVED' or any(getattr(policy,k) is None for k in required):
        block('POLICY_MISSING','Approved cutoff/holding/deduction/partial/failed settlement settings required.')
    minimum=(agreement.terms.get('settlements') or {}).get('minimum_payout')
    if minimum is None:block('POLICY_MISSING','Minimum payout is not configured.')
    return policy,minimum


def visit_position(db,row,*,lock=False,now=None):
    if digest(row.snapshot)!=row.snapshot_hash:block('RECONCILIATION_REQUIRED','Visit allocation integrity mismatch.')
    if row.snapshot.get('method')=='MONTHLY_VERIFIED_VISIT_VOLUME':
        from app.services.commercial_settlement import visit_position as commercial_position
        return commercial_position(db,row,lock=lock,now=now or utcnow())
    if row.fee_status!='WALLET_ONLY_NO_GATEWAY_FEE':
        block('FEE_DISTRIBUTION_POLICY_MISSING','Multi-Gym entitlement is accrued; purchase-fee distribution must be approved before payout.')
    from app.models.payment_checkout import PaymentCheckout
    from app.models.membership import UserMembership
    from app.services.marketplace_allocations import fee_for_checkout
    checkout_query=select(PaymentCheckout).where(PaymentCheckout.id==row.checkout_id)
    checkout=db.scalar(checkout_query.with_for_update() if lock else checkout_query)
    member=db.get(UserMembership,row.membership_id)
    if not checkout or checkout.mode!=row.mode or checkout.status!='PAID' or checkout.amount!=0 or not member or member.status=='CANCELLED' or member.payment_status!='PAID':
        block('SOURCE_NOT_ELIGIBLE','Visit purchase no longer supports payout.')
    # Only payout mutations fetch/lock fee evidence; reporting uses immutable fee
    # state and does not expose this route for visit availability at present.
    if lock and fee_for_checkout(db,checkout)[0] is not None:
        block('FEE_DISTRIBUTION_POLICY_MISSING','New actual fee evidence requires review before visit payout.')
    agreement=db.get(FinancialAgreementVersion,row.agreement_version_id)
    if not agreement:block('AGREEMENT_MISSING','Visit agreement unavailable.')
    from pydantic import ValidationError
    try:policy=SettlementPolicy.model_validate((agreement.terms.get('policy_contract') or {}).get('settlements') or {})
    except ValidationError:block('POLICY_INVALID','Invalid visit settlement settings.')
    required=('monthly_cutoff_day','short_month','cutoff_time','timezone','holding_days','eligible_deductions','partial_settlement','failed_settlement')
    if policy.approval.status!='APPROVED' or any(getattr(policy,k) is None for k in required):
        block('POLICY_MISSING','Approved monthly settlement settings are required.')
    if policy.timezone!=row.snapshot['policy']['period_timezone']:
        block('POLICY_SOURCE_CONFLICT','Visit allocation and monthly payout period timezones differ.')
    minimum=(agreement.terms.get('settlements') or {}).get('minimum_payout')
    if minimum is None:block('POLICY_MISSING','Minimum payout missing.')
    if row.approved_amount<=0:block('NO_AVAILABLE_ENTITLEMENT','Visit has no approved payable amount.')
    claims=select(OwnerPayoutItem).join(OwnerPayout).where(OwnerPayoutItem.visit_payout_id==row.id,OwnerPayout.status!='REVERSED')
    reserved=sum((i.amount for i in db.scalars(claims.with_for_update() if lock else claims)),Decimal(0))
    due=schedule_at(row,agreement.terms,policy)
    return {'entitlement':row.approved_amount,'reserved':reserved,'remaining':row.approved_amount-reserved,
        'available_at':due,'status':'AVAILABLE' if as_ist(now or utcnow())>=due else 'ACCRUED','policy':policy,'minimum':Decimal(str(minimum))}


def audit(db,row,actor,old,target,reason,key,request_hash,evidence=None):
    db.add(OwnerPayoutAudit(id=str(uuid4()),payout_id=row.id,actor_id=actor,from_status=old,to_status=target,
        mode=row.mode,actual_reference=evidence.get('reference') if evidence else None,
        reason=reason,request_key=key,request_hash=request_hash,evidence=evidence or {},created_at=stored_instant(utcnow())))


def create(db,actor_id,body,key):
    authorize(db,actor_id)
    with db.begin_nested():
        identifiers=[item.allocation_id or item.visit_payout_id for item in body.items]
        if len(set(identifiers))!=len(identifiers):block('DUPLICATE_ALLOCATION','Duplicate source items.')
        sources=[]
        for item in body.items:
            model=MarketplaceAllocation if item.allocation_id else GymVisitPayout
            row=db.get(model,item.allocation_id or item.visit_payout_id)
            if not row:block('SOURCE_DATA_MISSING','Payout allocation not found.')
            sources.append(row)
        modes={r.mode for r in sources};owners={r.owner_user_id for r in sources};gyms={r.gym_id for r in sources}
        categories={r.category if isinstance(r,MarketplaceAllocation) else 'MULTI_GYM' for r in sources}
        if any(len(values)!=1 for values in (modes,owners,gyms,categories)):
            block('PAYOUT_SCOPE_MISMATCH','One owner, gym, category and environment per payout required.')
        mode=modes.pop();gate(mode);owner=owners.pop();gym=gyms.pop();category=categories.pop()
        lock_sources(db,sources)
        # Existing source locks serialize competing claims. Do not lock the owner
        # after the purchaser: reciprocal owner/customer identities could deadlock.
        fingerprint=digest({'actor_id':actor_id,'body':body.model_dump(mode='json')})
        previous=db.scalar(select(OwnerPayout).where(OwnerPayout.mode==mode,OwnerPayout.request_key==key).with_for_update())
        if previous:
            if previous.request_hash!=fingerprint:block('IDEMPOTENCY_CONFLICT','Payout request key already used.')
            return previous
        positions=[]
        for source in sorted(sources,key=lambda r:r.id):
            db.scalar(select(type(source)).where(type(source).id==source.id).with_for_update().execution_options(populate_existing=True))
            positions.append((source,financial_position(db,source,lock=True)))
        requested={item.allocation_id or item.visit_payout_id:item.amount for item in body.items}
        for row,pos in positions:
            amount=requested[row.id]
            if pos['status']!='AVAILABLE':block('NOT_DUE','Configured settlement cutoff/holding period has not elapsed.')
            if amount>pos['remaining']:block('PAYOUT_EXCEEDS_ENTITLEMENT','Claim exceeds unreserved entitlement.')
            if pos['policy'].partial_settlement=='FULL_ENTITLEMENT_ONLY' and amount!=pos['remaining']:
                block('PARTIAL_PAYOUT_NOT_APPROVED','Full available entitlement is required.')
        entitlement=sum(requested.values(),Decimal(0));deduction=sum((item.amount for item in body.deductions),Decimal(0))
        for item in body.deductions:
            if any(item.kind not in pos['policy'].eligible_deductions for _,pos in positions):
                block('DEDUCTION_NOT_APPROVED','Deduction is not allowed by every selected agreement.')
        net=entitlement-deduction
        if net<=0 or net<max(pos['minimum'] for _,pos in positions):block('MINIMUM_PAYOUT','Payout is nonpositive or below configured minimum.')
        if entitlement>Decimal('9999999999.99'):block('AMOUNT_OUT_OF_RANGE','Payout exceeds storage precision.')
        days=[as_ist(row.occurred_at).date() if isinstance(row,MarketplaceAllocation) else row.service_date for row in sources]
        payout=OwnerPayout(id=str(uuid4()),mode=mode,gym_id=gym,owner_user_id=owner,category=category,
            period_start=min(days),period_end=max(days),entitlement_amount=entitlement,deduction_amount=deduction,
            amount=net,currency='INR',status='PENDING_APPROVAL',version=1,requested_by=actor_id,
            request_key=key,request_hash=fingerprint,deductions=[d.model_dump(mode='json') for d in body.deductions],created_at=stored_instant(utcnow()))
        db.add(payout);db.flush()
        for item in body.items:db.add(OwnerPayoutItem(id=str(uuid4()),payout_id=payout.id,allocation_id=item.allocation_id,visit_payout_id=item.visit_payout_id,amount=item.amount))
        audit(db,payout,actor_id,None,'PENDING_APPROVAL',body.reason,key,fingerprint)
        db.flush();return payout


def transition(db,actor_id,payout_id,body,key):
    authorize(db,actor_id)
    with db.begin_nested():
        current=db.get(OwnerPayout,payout_id)
        if not current:block('SOURCE_DATA_MISSING','Payout not found.')
        gate(current.mode)
        # Allocation locks precede payout locks, as in reservation creation.
        items=list(db.scalars(select(OwnerPayoutItem).where(OwnerPayoutItem.payout_id==payout_id)))
        sources=[db.get(MarketplaceAllocation,item.allocation_id) if item.allocation_id else db.get(GymVisitPayout,item.visit_payout_id) for item in items]
        lock_sources(db,sources)
        for item in sorted(items,key=lambda i:i.allocation_id or i.visit_payout_id):
            if item.allocation_id:db.scalar(select(MarketplaceAllocation).where(MarketplaceAllocation.id==item.allocation_id).with_for_update())
            else:db.scalar(select(GymVisitPayout).where(GymVisitPayout.id==item.visit_payout_id).with_for_update())
        row=db.scalar(select(OwnerPayout).where(OwnerPayout.id==payout_id).with_for_update().execution_options(populate_existing=True))
        fingerprint=digest({'actor_id':actor_id,'body':body.model_dump(mode='json')})
        prior=db.scalar(select(OwnerPayoutAudit).where(OwnerPayoutAudit.payout_id==payout_id,OwnerPayoutAudit.request_key==key).with_for_update())
        if prior:
            if prior.request_hash!=fingerprint:block('IDEMPOTENCY_CONFLICT','Transition request key already used.')
            return row
        if row.version!=body.expected_version:block('VERSION_CONFLICT','Payout changed; reload before action.')
        allowed={'PENDING_APPROVAL':{'APPROVED','REVERSED'},'APPROVED':{'PROCESSING','REVERSED'},
            'PROCESSING':{'PAID','FAILED'},'FAILED':{'PENDING_APPROVAL'},'PAID':{'REVERSED'}}
        if body.status not in allowed.get(row.status,set()):block('INVALID_TRANSITION','Payout state transition not allowed.')
        if body.status in {'APPROVED','PROCESSING','PAID','PENDING_APPROVAL'}:
            for item in items:
                source=db.get(MarketplaceAllocation,item.allocation_id) if item.allocation_id else db.get(GymVisitPayout,item.visit_payout_id)
                position=financial_position(db,source,lock=True)
                if position['reserved']>position['entitlement'] or position['status']!='AVAILABLE':
                    block('RECONCILIATION_REQUIRED','Current entitlement no longer supports all reservations.')
        actual=body.payment_evidence
        returning=row.status=='PAID' and body.status=='REVERSED'
        if returning and row.deduction_amount:
            block('DEDUCTION_RETURN_REVIEW','A paid payout with deductions requires separate withholding/adjustment return evidence.')
        if body.status=='PAID' or returning:
            if actual is None or actual.amount!=row.amount or actual.owner_user_id!=row.owner_user_id or stored_instant(actual.paid_at)>stored_instant(utcnow()) or stored_instant(actual.paid_at)<row.created_at:
                block('ACTUAL_PAYMENT_EVIDENCE_REQUIRED','Matching actual amount, beneficiary, reference and non-future date required.')
            collision=db.scalar(select(OwnerPayoutAudit.id).where(OwnerPayoutAudit.mode==row.mode,OwnerPayoutAudit.actual_reference==actual.reference).limit(1))
            if collision:block('DUPLICATE_PAYMENT_REFERENCE','Payment or return reference is already recorded.')
            if returning and (actual.reference==row.payment_reference or stored_instant(actual.paid_at)<row.paid_at):
                block('RETURN_EVIDENCE_REQUIRED','Paid reversal requires later, distinct bank return evidence.')
        elif actual is not None:block('UNEXPECTED_PAYMENT_EVIDENCE','Payment evidence is only accepted for actual payment/return.')
        old=row.status;row.status=body.status;row.version+=1
        if body.status=='APPROVED':row.approved_by=actor_id
        if body.status=='PAID':
            row.payment_reference=actual.reference;row.paid_at=stored_instant(actual.paid_at)
            row.payment_evidence={**actual.model_dump(mode='json'),'verification_status':'ADMIN_ATTESTED_DOCUMENT','recorded_by':actor_id}
        audit(db,row,actor_id,old,row.status,body.reason,key,fingerprint,actual.model_dump(mode='json') if actual else {})
        db.flush();return row


def present(row):
    return {name:getattr(row,name) for name in ('id','mode','gym_id','owner_user_id','category','period_start','period_end',
        'entitlement_amount','deduction_amount','amount','currency','status','version','requested_by','approved_by',
        'payment_reference','paid_at','payment_evidence','deductions','created_at')}