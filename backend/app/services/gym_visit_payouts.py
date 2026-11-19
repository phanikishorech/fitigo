"""Fixed visit entitlement only. Unallocated collections are not FitiGo earnings."""
from datetime import timezone
from decimal import Decimal
from uuid import uuid4
from sqlalchemy import select
from app.core.config import settings
from app.core.time import as_ist, stored_instant, utcnow
from app.models.auth import User
from app.models.gym import Gym
from app.models.membership import UserMembership
from app.models.payment_checkout import PaymentCheckout
from app.models.access import Checkin, CustomerDailyAccess, AccessQrToken
from app.models.financial_agreement import FinancialAgreementVersion
from app.models.source_evidence import SourceEvidence, SourceOutbox, GymOwnerEvidence
from app.models.gym_visit_payout import GymVisitPayout
from app.schemas.marketplace_allocation import VisitPayoutPolicy
from app.schemas.financial_agreement import MultiGymTerms
from app.services.marketplace_allocations import verified_payload, funding_for, fee_for_checkout, digest
from app.services.marketplace_calculation import block
from app.services.financial_agreements import resolve, scope
from app.services.agreement_selection import pin_for_source


def allocate_visit(db,event_id):
    with db.begin_nested():
        return _allocate(db,event_id)


def _allocate(db,event_id):
    if not settings.marketplace_allocations_enabled:block('PROCESSING_DISABLED','Allocation processing disabled.')
    event=db.get(SourceOutbox,event_id)
    if not event or event.event_type!='MULTI_GYM_VISIT_VERIFIED':block('SOURCE_NOT_ELIGIBLE','Verified Multi-Gym visit event required.')
    if event.mode=='live' and not settings.marketplace_live_allocations_enabled:block('LIVE_PROCESSING_DISABLED','Live disabled.')
    source=db.get(SourceEvidence,event.evidence_id)
    if not source or source.mode!=event.mode or source.event_type!=event.event_type or source.source_id!=event.source_id or source.occurred_at!=event.occurred_at:
        block('ENVIRONMENT_MISMATCH','Event/evidence mismatch.')
    data=verified_payload(source)
    checkout=db.get(PaymentCheckout,source.checkout_id) if source.checkout_id else None
    if not checkout or checkout.mode!=event.mode:block('SOURCE_DATA_MISSING','Trusted membership checkout required.')
    for user_id in sorted({checkout.user_id,data.get('holder_id_at_event') or checkout.user_id}):
        db.scalar(select(User).where(User.id==user_id).with_for_update())
    db.scalar(select(Gym).where(Gym.id==data.get('gym_id')).with_for_update())
    member=db.scalar(select(UserMembership).where(UserMembership.id==data.get('membership_id')).with_for_update().execution_options(populate_existing=True))
    checkout=db.scalar(select(PaymentCheckout).where(PaymentCheckout.id==checkout.id).with_for_update().execution_options(populate_existing=True))
    # All monthly cap writers in an environment share this stable existing lock.
    # It is conservative but closes the empty-row and platform-wide cap race.
    scope(db,checkout.mode,None,lock=True)
    prior=db.scalar(select(GymVisitPayout).where(GymVisitPayout.mode==event.mode,
        (GymVisitPayout.checkin_id==data.get('checkin_id'))|(GymVisitPayout.daily_access_id==data.get('daily_access_id'))).with_for_update())
    if prior:
        if prior.checkin_id!=data.get('checkin_id'):block('DUPLICATE_DAILY_ACCESS','Daily access already has a different allocated check-in.')
        return prior
    if not member or member.gateway_checkout_id!=checkout.id or member.membership_type!='MULTI_GYM' or member.payment_status!='PAID' or member.status=='CANCELLED':
        block('SOURCE_NOT_ELIGIBLE','Paid Multi-Gym membership required.')
    funding_for(db,checkout)
    scan=db.get(Checkin,data.get('checkin_id'))
    daily=db.get(CustomerDailyAccess,data.get('daily_access_id'))
    token=db.get(AccessQrToken,data.get('qr_token_id'))
    if not scan or not daily or not token or scan.status!='SUCCESS' or scan.user_id!=daily.user_id or scan.access_source!='MEMBERSHIP_ACCESS' or scan.membership_id!=member.id or scan.daily_access_id!=daily.id or daily.membership_id!=member.id or daily.status!='USED' or daily.checkin_id!=scan.id or daily.used_gym_id!=scan.gym_id or token.id!=scan.qr_token_id or token.daily_access_id!=daily.id or token.checkin_id!=scan.id or scan.checkin_time!=source.occurred_at:
        block('SOURCE_DATA_MISMATCH','Consumed membership admission links do not reconcile.')
    if source.source_type!='CHECKIN' or source.source_id!=str(scan.id) or data.get('gym_id')!=scan.gym_id or data.get('customer_id')!=scan.user_id or data.get('service_date')!=str(daily.access_date):
        block('SOURCE_DATA_MISMATCH','Immutable visit identity/service date differs from admission.')
    if source.evidence_status!='VERIFIED_SOURCE' or not token.valid_from or not token.valid_from<=scan.checkin_time<token.expires_at:
        block('SOURCE_DATA_MISSING','Valid admission window required.')
    owner=db.scalar(select(GymOwnerEvidence).where(GymOwnerEvidence.evidence_id==source.id))
    if not owner or owner.gym_id!=scan.gym_id or owner.owner_user_id!=data.get('owner_id_at_event'):
        block('OWNER_EVIDENCE_MISSING','Historical admission owner required.')
    if 'financial_configuration' in data:
        return allocate_configured_visit(db, event, source, checkout, member, scan, daily, owner)
    governing=resolve(db,checkout.mode,scan.gym_id,as_ist(scan.checkin_time),lock=True)
    if not governing:block('AGREEMENT_MISSING','No effective visit agreement.')
    pin=pin_for_source(db,checkout_id=checkout.id,context='MULTI_GYM_VISIT',selection_policy_version_id=governing.id,checkin_id=scan.id)
    agreement=db.get(FinancialAgreementVersion,pin.agreement_version_id)
    from pydantic import ValidationError
    try:
        policy=VisitPayoutPolicy.model_validate(agreement.terms.get('visit_payout_contract') or {})
        rates=MultiGymTerms.model_validate(agreement.terms.get('multi_gym') or {})
    except ValidationError:block('POLICY_INVALID','Visit payout policy invalid.')
    if policy.approval.status!='APPROVED' or any(value is None for value in (rates.payout_per_visit,rates.visits_per_member_month,rates.payout_cap_per_member_month)):
        block('POLICY_MISSING','Approved fixed visit rate and explicit monthly limits/caps are required.')
    instant=as_ist(scan.checkin_time) if policy.period_timezone=='Asia/Kolkata' else as_ist(scan.checkin_time).astimezone(timezone.utc)
    period=instant.date().replace(day=1)
    all_rows=list(db.scalars(select(GymVisitPayout).where(GymVisitPayout.mode==checkout.mode,
        GymVisitPayout.allocation_period==period).with_for_update()))
    if any(row.snapshot.get('method')=='MONTHLY_VERIFIED_VISIT_VOLUME' for row in all_rows):
        block('POLICY_SOURCE_CONFLICT','Legacy cap accounting cannot reinterpret consolidated monthly allocations.')
    # Do not silently change period boundary semantics inside an allocated month.
    if any(row.snapshot['policy']['period_timezone']!=policy.period_timezone for row in all_rows):
        block('POLICY_SOURCE_CONFLICT','Period timezone differs from existing month allocations.')
    if any(row.snapshot['policy']['platform_cap_mode']!=policy.platform_cap_mode or
        row.snapshot['policy']['platform_monthly_cap']!=policy.model_dump(mode='json')['platform_monthly_cap'] for row in all_rows):
        block('POLICY_SOURCE_CONFLICT','Platform cap policy differs within the allocated environment/month.')
    # Member means the verified customer at admission, not a fresh allowance for
    # each renewal/plan ID. Transfer holder identity is preserved by the source.
    own=[row for row in all_rows if row.customer_id==scan.user_id and row.gym_id==scan.gym_id]
    remaining=max(Decimal(0),rates.payout_cap_per_member_month-sum((row.approved_amount for row in own),Decimal(0)))
    if policy.platform_cap_mode!='NOT_APPLICABLE':
        applicable=all_rows if policy.platform_cap_mode=='ALL_MEMBERSHIPS_ALL_GYMS' else [row for row in all_rows if row.membership_id==member.id]
        remaining=min(remaining,max(Decimal(0),policy.platform_monthly_cap-sum((row.approved_amount for row in applicable),Decimal(0))))
    allowed=min(rates.payout_per_visit,remaining)
    status='ACCRUED'
    if len(own)>=rates.visits_per_member_month:allowed=Decimal(0);status='VISIT_LIMIT_REACHED'
    elif allowed<rates.payout_per_visit:
        status='CAPPED'
        if policy.cap_exhaustion=='REJECT_WHOLE_VISIT':allowed=Decimal(0)
    actual_fee,fee_evidence_id=fee_for_checkout(db,checkout)
    fee_status='WALLET_ONLY_NO_GATEWAY_FEE' if checkout.amount==0 and actual_fee is None else 'PENDING_DISTRIBUTION_POLICY'
    snapshot={'policy':policy.model_dump(mode='json'),'rates':rates.model_dump(mode='json'),
        'source_payload_hash':source.payload_hash,'original_purchaser_id':checkout.user_id,'holder_id_at_visit':scan.user_id,
        'fitigo_earnings':None,'fitigo_earnings_status':'POLICY_MISSING','statutory_reporting_enabled':False,
        'cap_order':'SERIALIZED_PROCESSING_ORDER','member_cap_identity':'CUSTOMER_AT_VISIT',
        'prior_member_gym_visits':len(own),'fee_evidence_id':fee_evidence_id}
    row=GymVisitPayout(id=str(uuid4()),source_event_id=event.id,source_evidence_id=source.id,checkout_id=checkout.id,
        membership_id=member.id,customer_id=scan.user_id,gym_id=scan.gym_id,owner_user_id=owner.owner_user_id,
        owner_evidence_id=owner.id,checkin_id=scan.id,daily_access_id=daily.id,agreement_pin_id=pin.id,agreement_version_id=agreement.id,
        service_date=daily.access_date,allocation_period=period,configured_amount=rates.payout_per_visit,
        approved_amount=allowed,applied_cap=remaining,mode=checkout.mode,currency='INR',status=status,
        fee_status=fee_status,idempotency_key=digest({'mode':checkout.mode,'checkin':scan.id}),
        snapshot=snapshot,snapshot_hash=digest(snapshot),created_at=stored_instant(utcnow()))
    db.add(row);db.flush();return row


def monthly_settings(terms):
    from app.services.marketplace_calculation import commercial_settings
    policy = commercial_settings(terms).multi_gym
    expected = {'period_timezone':'Asia/Kolkata', 'rounding':'MONTHLY_TOTAL_HALF_UP',
        'version_boundary':'PIN_AT_ADMISSION', 'purchase_fee_attribution':'MEMBERSHIP_COMPLETE_EQUAL_VISITS',
        'invalidated_visit_correction':'APPEND_ONLY_SOURCE_BACKED'}
    if any(getattr(policy,key) != value for key,value in expected.items()):
        block('MONTHLY_POLICY_MISSING', 'Explicit approved monthly timezone/rounding/version/fee/correction settings required.')
    return policy


def allocate_configured_visit(db, event, source, checkout, member, scan, daily, owner):
    from app.services.agreement_selection import pin_commercial_evidence
    from app.models.gym_visit_payout import GymMonthlyCalculation, MembershipVisitFee
    pin = pin_commercial_evidence(db, source, context='MULTI_GYM_VISIT', source_key=f'membership:{member.id}:daily:{daily.id}')
    agreement = db.get(FinancialAgreementVersion, pin.agreement_version_id)
    policy = monthly_settings(agreement.terms)
    period = as_ist(scan.checkin_time).date().replace(day=1)
    if db.scalar(select(GymMonthlyCalculation.id).where(GymMonthlyCalculation.mode==checkout.mode,
            GymMonthlyCalculation.gym_id==scan.gym_id, GymMonthlyCalculation.period==period).limit(1).with_for_update()):
        block('FINALIZED_MONTH_REVIEW', 'Late visits require explicit monthly correction review.')
    if db.scalar(select(MembershipVisitFee.id).where(MembershipVisitFee.checkout_id==checkout.id).with_for_update()):
        block('FINALIZED_FEE_REVIEW', 'Membership fee attribution is closed; late visits require review.')
    actual_fee, fee_id = fee_for_checkout(db, checkout)
    if checkout.amount == 0 and actual_fee not in (None, Decimal(0)):
        block('RECONCILIATION_REQUIRED', 'Wallet-only membership cannot have a gateway fee.')
    snapshot = {'method':'MONTHLY_VERIFIED_VISIT_VOLUME', 'policy':policy.model_dump(mode='json'),
        'configuration':agreement.terms['financial_settings'], 'configuration_hash':digest(agreement.terms),
        'source_payload_hash':source.payload_hash, 'admitted_at':scan.checkin_time.isoformat(),
        'fitigo_earnings':None, 'fitigo_earnings_status':'NOT_APPROVED', 'fee_evidence_id':fee_id,
        'gross_status':'PENDING_MONTH_COMPLETION', 'statutory_reporting_enabled':False}
    row = GymVisitPayout(id=str(uuid4()),source_event_id=event.id,source_evidence_id=source.id,checkout_id=checkout.id,
        membership_id=member.id,customer_id=scan.user_id,gym_id=scan.gym_id,owner_user_id=owner.owner_user_id,
        owner_evidence_id=owner.id,checkin_id=scan.id,daily_access_id=daily.id,agreement_pin_id=pin.id,agreement_version_id=agreement.id,
        service_date=daily.access_date,allocation_period=period,configured_amount=Decimal(0),approved_amount=Decimal(0),applied_cap=None,
        mode=checkout.mode,currency='INR',status='PENDING_MONTH_COMPLETION',
        fee_status='WALLET_ONLY_NO_GATEWAY_FEE' if checkout.amount==0 else 'PENDING_MEMBERSHIP_COMPLETION',
        idempotency_key=digest({'mode':checkout.mode,'checkin':scan.id}),snapshot=snapshot,snapshot_hash=digest(snapshot),created_at=stored_instant(utcnow()))
    db.add(row);db.flush();return row


def processing_gate(mode):
    if mode not in {'test','live'}: block('ENVIRONMENT_MISMATCH', 'Explicit payment environment required.')
    if not settings.marketplace_allocations_enabled: block('PROCESSING_DISABLED','Allocation processing disabled.')
    if mode == 'live' and not settings.marketplace_live_allocations_enabled: block('LIVE_PROCESSING_DISABLED','Live processing disabled.')


def verify_visit_snapshot(row):
    if digest(row.snapshot) != row.snapshot_hash: block('RECONCILIATION_REQUIRED', 'Visit snapshot integrity mismatch.')
    if row.snapshot.get('method') != 'MONTHLY_VERIFIED_VISIT_VOLUME':
        block('POLICY_SOURCE_CONFLICT', 'Legacy fixed-rate visits cannot be converted to monthly formula.')
    return monthly_settings({'financial_settings':row.snapshot['configuration']})


def latest_month(db, mode, gym_id, period, *, lock=False):
    from app.models.gym_visit_payout import GymMonthlyCalculation
    query = select(GymMonthlyCalculation).where(GymMonthlyCalculation.mode==mode,
        GymMonthlyCalculation.gym_id==gym_id, GymMonthlyCalculation.period==period)
    query = query.order_by(GymMonthlyCalculation.revision.desc()).limit(1)
    row = db.scalar(query.with_for_update().execution_options(populate_existing=True) if lock else query)
    if row and digest(row.snapshot) != row.snapshot_hash: block('RECONCILIATION_REQUIRED', 'Monthly snapshot integrity mismatch.')
    return row


def finalize_month(db, *, mode, gym_id, period, correction_evidence_id=None, actor_id=None):
    """Internal caller-owned transaction; never triggered by GET/payment/access.

    Original month is final. Only an explicit source-backed invalidation can append
    a revision. All affected reservations/fee budgets are checked before correction.
    """
    from datetime import datetime
    from app.core.time import IST
    from app.models.gym_visit_payout import GymMonthlyCalculation, MembershipVisitFee
    from app.models.owner_payout import OwnerPayout, OwnerPayoutItem
    from app.services.marketplace_calculation import monthly_visit_amounts, exact_amount
    processing_gate(mode)
    if period.day != 1: block('SOURCE_DATA_INVALID', 'Period must be the first calendar day of the month.')
    end = period.replace(year=period.year+1,month=1) if period.month==12 else period.replace(month=period.month+1)
    start_at = stored_instant(datetime.combine(period,datetime.min.time(),tzinfo=IST))
    end_at = stored_instant(datetime.combine(end,datetime.min.time(),tzinfo=IST))
    if stored_instant(utcnow()) < end_at: block('MONTH_NOT_COMPLETE', 'Calendar month has not ended.')
    with db.begin_nested():
        from app.services.owner_payouts import lock_sources
        candidates=list(db.scalars(select(GymVisitPayout).where(GymVisitPayout.mode==mode,
            GymVisitPayout.gym_id==gym_id,GymVisitPayout.allocation_period==period)))
        lock_sources(db,candidates)
        if not db.scalar(select(Gym.id).where(Gym.id==gym_id).with_for_update()): block('SOURCE_DATA_MISSING','Gym missing.')
        scope(db,mode,None,lock=True)
        previous = latest_month(db,mode,gym_id,period,lock=True)
        if previous and correction_evidence_id is None: return previous
        rows = list(db.scalars(select(GymVisitPayout).where(GymVisitPayout.mode==mode,
            GymVisitPayout.gym_id==gym_id,GymVisitPayout.allocation_period==period).with_for_update()))
        rows.sort(key=lambda row:(row.snapshot.get('admitted_at',''),row.checkin_id))
        if not rows: block('SOURCE_DATA_MISSING','No allocated verified visits for this gym/month.')
        for row in rows: verify_visit_snapshot(row)
        excluded = set(previous.snapshot['excluded_visit_ids']) if previous else set()
        if correction_evidence_id:
            from app.services.owner_payouts import authorize
            authorize(db,actor_id)
            if not previous: block('SOURCE_DATA_MISSING','Finalize original month before correcting it.')
            retry = db.scalar(select(GymMonthlyCalculation).where(GymMonthlyCalculation.source_evidence_id==correction_evidence_id).with_for_update())
            if retry:
                if retry.mode!=mode or retry.gym_id!=gym_id or retry.period!=period or retry.actor_id!=actor_id:
                    block('RECONCILIATION_REQUIRED','Correction request identity mismatch.')
                return retry
            source=db.get(SourceEvidence,correction_evidence_id)
            if not source or source.event_type!='MULTI_GYM_VISIT_INVALIDATED' or source.mode!=mode or source.evidence_status!='VERIFIED_SOURCE':
                block('SOURCE_DATA_MISSING','Verified invalidation evidence required.')
            data=verified_payload(source)
            target=next((r for r in rows if r.checkin_id==data.get('checkin_id')),None)
            if not target or source.checkout_id!=target.checkout_id or data.get('gym_id')!=gym_id or data.get('actor_id')!=actor_id or not data.get('reason'):
                block('SOURCE_DATA_MISMATCH','Invalidation does not identify this visit/actor/gym.')
            if data.get('original_evidence_id')!=target.source_evidence_id or data.get('original_payload_hash')!=target.snapshot['source_payload_hash']:
                block('SOURCE_DATA_MISMATCH','Invalidation must reference the immutable original admission.')
            if db.get(Checkin,target.checkin_id).status=='SUCCESS': block('SOURCE_NOT_ELIGIBLE','Admission has not been invalidated.')
            if target.id in excluded: block('DUPLICATE_SOURCE_UNIT','Visit already excluded by an earlier correction.')
            identifiers=[r.id for r in rows]
            if db.scalar(select(OwnerPayoutItem.id).join(OwnerPayout).where(OwnerPayoutItem.visit_payout_id.in_(identifiers),
                    OwnerPayout.status!='REVERSED').limit(1).with_for_update()):
                block('PAYOUT_RESERVATION_REVIEW','Monthly rounding correction touches reserved/paid allocations; coordinated review required.')
            if db.scalar(select(MembershipVisitFee.id).where(MembershipVisitFee.checkout_id.in_([r.checkout_id for r in rows])).limit(1).with_for_update()):
                block('FINALIZED_FEE_REVIEW','Invalidation affects closed membership fee budgets; explicit coordinated review required.')
            excluded.add(target.id)
        # Completeness: all successful admissions with a trusted checkout in this
        # gym/month must be allocated. A missed event cannot silently disappear.
        successful=set(db.scalars(select(Checkin.id).join(UserMembership,UserMembership.id==Checkin.membership_id)
            .join(PaymentCheckout,PaymentCheckout.id==UserMembership.gateway_checkout_id).where(Checkin.gym_id==gym_id,
                Checkin.checkin_time>=start_at,Checkin.checkin_time<end_at,Checkin.status=='SUCCESS',
                UserMembership.membership_type=='MULTI_GYM',PaymentCheckout.mode==mode).with_for_update()))
        active=[r for r in rows if r.id not in excluded]
        if successful != {r.checkin_id for r in active}:
            block('MONTH_INCOMPLETE','Successful admissions and allocated visits differ; process missing events or explicit invalidation evidence.')
        for row in active:
            checkout=db.get(PaymentCheckout,row.checkout_id)
            funding_for(db,checkout)
        policies=[verify_visit_snapshot(row) for row in active]
        gross, amounts=monthly_visit_amounts([(p.reference_amount,p.reference_visits) for p in policies])
        exact_amount(gross)
        snapshot={'period_timezone':'Asia/Kolkata','rounding':'MONTHLY_TOTAL_HALF_UP',
            'previous_calculation_id':previous.id if previous else None,'excluded_visit_ids':sorted(excluded),
            'visits':[{'visit_id':row.id,'checkin_id':row.checkin_id,'agreement_version_id':row.agreement_version_id,
                'snapshot_hash':row.snapshot_hash,'gross_amount':str(amount),'owner_user_id':row.owner_user_id}
                for row,amount in zip(active,amounts)],'verified_visits':len(active),
            'fitigo_earnings':None,'unallocated_collection_is_commission':False}
        result=GymMonthlyCalculation(id=str(uuid4()),mode=mode,gym_id=gym_id,period=period,
            revision=previous.revision+1 if previous else 1,source_evidence_id=correction_evidence_id,actor_id=actor_id,
            gross_amount=gross,snapshot=snapshot,snapshot_hash=digest(snapshot),created_at=stored_instant(utcnow()))
        db.add(result);db.flush();return result


def attribute_membership_fee(db, checkout_id):
    """Close exactly one original provider fee budget, after complete membership use.

    Unknown fee or incomplete evidence produces no attribution. The original
    provider observation and monthly gross calculations are never modified.
    """
    from app.models.gym_visit_payout import MembershipVisitFee
    from app.services.marketplace_calculation import equal_units, split_actual_fee
    with db.begin_nested():
        checkout=db.get(PaymentCheckout,checkout_id)
        if not checkout: block('SOURCE_DATA_MISSING','Membership checkout missing.')
        processing_gate(checkout.mode)
        db.scalar(select(User).where(User.id==checkout.user_id).with_for_update())
        member=db.scalar(select(UserMembership).where(UserMembership.gateway_checkout_id==checkout_id).with_for_update())
        checkout=db.scalar(select(PaymentCheckout).where(PaymentCheckout.id==checkout_id).with_for_update().execution_options(populate_existing=True))
        scope(db,checkout.mode,None,lock=True)
        previous=db.scalar(select(MembershipVisitFee).where(MembershipVisitFee.checkout_id==checkout_id).with_for_update())
        if previous:
            if digest(previous.snapshot)!=previous.snapshot_hash: block('RECONCILIATION_REQUIRED','Membership fee snapshot integrity mismatch.')
            return previous
        if not member or member.membership_type!='MULTI_GYM':
            block('MEMBERSHIP_NOT_COMPLETE','Membership may still fund visits; net remains pending.')
        if member.status in {'PAUSED','CANCELLED'} or member.end_at>stored_instant(utcnow()):
            block('MEMBERSHIP_NOT_COMPLETE','Paused/cancelled or incomplete membership requires review.')
        funding_for(db,checkout)
        if checkout.amount==0: block('NO_GATEWAY_FEE','Wallet-only membership does not need a provider fee budget.')
        fee, evidence_id=fee_for_checkout(db,checkout)
        if fee is None: block('FEE_PENDING','Actual provider-confirmed fee is unavailable.')
        rows=list(db.scalars(select(GymVisitPayout).where(GymVisitPayout.checkout_id==checkout_id).order_by(GymVisitPayout.checkin_id).with_for_update()))
        if not rows: block('FEE_ATTRIBUTION_INCOMPLETE','No eligible verified visits; retain unallocated fee, never fabricate visits.')
        success=set(db.scalars(select(Checkin.id).where(Checkin.membership_id==member.id,Checkin.status=='SUCCESS').with_for_update()))
        active=[]
        for row in rows:
            verify_visit_snapshot(row)
            month=latest_month(db,row.mode,row.gym_id,row.allocation_period,lock=True)
            if not month: block('FEE_ATTRIBUTION_INCOMPLETE','All visit months must be finalized before membership fee attribution.')
            if row.id not in month.snapshot['excluded_visit_ids']: active.append(row)
        if success!={r.checkin_id for r in active} or not active:
            block('FEE_ATTRIBUTION_INCOMPLETE','Membership admissions do not reconcile to finalized eligible visits.')
        portions=equal_units(fee,len(active),'LOWEST_VISITOR_INDEX')
        entries=[]
        for row,amount in zip(active,portions):
            policy=verify_visit_snapshot(row)
            gym,fitigo=split_actual_fee(amount,'FITIGO',policy.gateway_fee.gym_percent)
            entries.append({'visit_id':row.id,'agreement_version_id':row.agreement_version_id,
                'fee_percentages':policy.gateway_fee.model_dump(mode='json'),'fee_amount':str(amount),
                'gym_fee':str(gym),'fitigo_fee':str(fitigo)})
        snapshot={'membership_id':member.id,'completed_end_at':member.end_at.isoformat(),
            'provider_payment_id':checkout.gateway_payment_id,'fee_evidence_id':evidence_id,'visits':entries,
            'attribution':'MEMBERSHIP_COMPLETE_EQUAL_VISITS','fitigo_earnings':None}
        result=MembershipVisitFee(id=str(uuid4()),checkout_id=checkout.id,fee_evidence_id=evidence_id,mode=checkout.mode,
            actual_fee=fee,snapshot=snapshot,snapshot_hash=digest(snapshot),created_at=stored_instant(utcnow()))
        db.add(result);db.flush();return result


def monthly_position(db,row):
    """Read-only gross/net projection from finalized immutable evidence."""
    from app.models.gym_visit_payout import MembershipVisitFee
    verify_visit_snapshot(row)
    month=latest_month(db,row.mode,row.gym_id,row.allocation_period)
    result={'gross':None,'net':None,'gym_fee':None,'fitigo_fee':None,'status':'PENDING_MONTH_COMPLETION'}
    if not month: return result
    item=next((v for v in month.snapshot['visits'] if v['visit_id']==row.id),None)
    if item is None: return {**result,'gross':Decimal(0),'net':Decimal(0),'status':'INVALIDATED'}
    if item['snapshot_hash']!=row.snapshot_hash: block('RECONCILIATION_REQUIRED','Monthly visit snapshot mismatch.')
    gross=Decimal(item['gross_amount'])
    result.update(gross=gross,status='FEE_PENDING')
    if row.fee_status=='WALLET_ONLY_NO_GATEWAY_FEE':
        return {**result,'net':gross,'gym_fee':Decimal(0),'fitigo_fee':Decimal(0),'status':'NET_VALIDATED'}
    fee=db.scalar(select(MembershipVisitFee).where(MembershipVisitFee.checkout_id==row.checkout_id))
    if not fee: return result
    if digest(fee.snapshot)!=fee.snapshot_hash: block('RECONCILIATION_REQUIRED','Fee budget integrity mismatch.')
    entry=next((v for v in fee.snapshot['visits'] if v['visit_id']==row.id),None)
    if not entry: block('RECONCILIATION_REQUIRED','Visit absent from completed fee attribution.')
    gym,fitigo=Decimal(entry['gym_fee']),Decimal(entry['fitigo_fee'])
    return {**result,'net':gross-gym,'gym_fee':gym,'fitigo_fee':fitigo,
        'status':'NET_VALIDATED' if gross>=gym else 'NEGATIVE_NET_REVIEW'}