"""Operational settlement readiness from the original gym version, never today's defaults."""
from datetime import timedelta
from types import SimpleNamespace
from pydantic import ValidationError
from app.core.time import as_ist, utcnow
from app.schemas.gym_financial_settings import SettlementSettings
from app.services.marketplace_calculation import block


def readiness(raw, category):
    try: policy = SettlementSettings.model_validate(raw or {})
    except ValidationError:
        return {'ready': False, 'missing': ['INVALID_SETTLEMENT_POLICY']}
    required = ['minimum_payout','timezone','holding_days','eligible_deductions','payout_eligibility',
        'partial_settlement','failed_settlement']
    cycle_field = 'multi_gym_cycle' if category == 'MULTI_GYM' else 'single_gym_cycle' if category == 'SINGLE_GYM' else 'booking_cycle'
    required.append(cycle_field)
    cycle = getattr(policy, cycle_field)
    if cycle != 'UPFRONT': required.append('cutoff_time')
    if cycle == 'WEEKLY': required.append('weekly_cutoff_day')
    if cycle == 'MONTHLY': required.extend(['monthly_cutoff_day','short_month'])
    missing = [name for name in required if getattr(policy,name) is None]
    if category == 'MULTI_GYM' and policy.timezone not in (None,'Asia/Kolkata'):
        missing.append('MULTI_GYM_TIMEZONE_MUST_MATCH_ADMISSIONS')
    return {'ready': not missing, 'missing': missing}


def policy_for(terms, category):
    raw = (terms.get('financial_settings') or {}).get('settlements')
    result = readiness(raw,category)
    if not result['ready']:
        block('SETTLEMENT_TIMING_UNCONFIGURED', 'Missing explicit settlement settings: '+', '.join(result['missing']))
    return SettlementSettings.model_validate(raw)


def due_at(row, terms, policy):
    from app.models.marketplace_allocation import MarketplaceAllocation
    from app.services.owner_payouts import schedule_at
    if isinstance(row,MarketplaceAllocation) and row.category=='SINGLE_GYM':
        if policy.single_gym_cycle=='UPFRONT': return as_ist(row.occurred_at)+timedelta(days=policy.holding_days)
        # The legacy scheduler's upfront bypass is not used for an explicit
        # commercial Single-Gym weekly/monthly settlement choice.
        proxy=SimpleNamespace(occurred_at=row.occurred_at)
        return schedule_at(proxy,{'settlements':{'booking_cycle':policy.single_gym_cycle}},policy)
    return schedule_at(row,{'settlements':policy.model_dump(mode='json')},policy)


def visit_position(db,row,*,lock=False,now=None):
    from sqlalchemy import select
    from app.models.access import Checkin
    from app.models.membership import UserMembership
    from app.models.payment_checkout import PaymentCheckout,PaymentAttempt
    from app.models.financial_agreement import FinancialAgreementVersion
    from app.models.owner_payout import OwnerPayout,OwnerPayoutItem
    from app.services.gym_visit_payouts import monthly_position
    from app.services.marketplace_allocations import digest
    from decimal import Decimal
    def current(model,identifier):
        query=select(model).where(model.id==identifier)
        return db.scalar(query.with_for_update().execution_options(populate_existing=True) if lock else query)
    checkout=current(PaymentCheckout,row.checkout_id)
    member=current(UserMembership,row.membership_id)
    scan=current(Checkin,row.checkin_id)
    if not checkout or checkout.mode!=row.mode or checkout.status!='PAID' or not member or member.status=='CANCELLED' or member.payment_status!='PAID' or not scan or scan.status!='SUCCESS':
        block('SOURCE_NOT_ELIGIBLE','Admission or purchase no longer supports settlement.')
    refunds=select(PaymentAttempt.id).where(PaymentAttempt.checkout_id==row.checkout_id,PaymentAttempt.refunded_amount>0).limit(1)
    if db.scalar(refunds.with_for_update() if lock else refunds): block('REFUND_REVIEW_REQUIRED','Refunded purchase needs reconciliation.')
    result=monthly_position(db,row)
    if result['net'] is None: block(result['status'],'Monthly completion or actual fee attribution is pending.')
    if result['net']<=0: block('NO_AVAILABLE_ENTITLEMENT','Nonpositive or invalidated entitlement requires review.')
    if lock:
        from app.services.marketplace_allocations import funding_for,fee_for_checkout
        from app.models.gym_visit_payout import MembershipVisitFee
        funding_for(db,checkout)
        actual,source_id=fee_for_checkout(db,checkout)
        if checkout.amount==0:
            if actual not in (None,Decimal(0)):block('RECONCILIATION_REQUIRED','Wallet-only checkout has conflicting gateway fee evidence.')
        else:
            budget=db.scalar(select(MembershipVisitFee).where(MembershipVisitFee.checkout_id==checkout.id).with_for_update())
            if not budget or actual is None or budget.actual_fee!=actual:
                block('FEE_BUDGET_REVIEW','Actual provider fee differs from the immutable membership fee budget.')
    agreement=db.get(FinancialAgreementVersion,row.agreement_version_id)
    if not agreement or digest(agreement.terms)!=row.snapshot.get('configuration_hash'):
        block('RECONCILIATION_REQUIRED','Pinned commercial configuration does not match the visit snapshot.')
    policy=policy_for(agreement.terms,'MULTI_GYM')
    claims=select(OwnerPayoutItem).join(OwnerPayout).where(OwnerPayoutItem.visit_payout_id==row.id,OwnerPayout.status!='REVERSED')
    reserved=sum((r.amount for r in db.scalars(claims.with_for_update() if lock else claims)),Decimal(0))
    due=due_at(row,agreement.terms,policy)
    return {'entitlement':result['net'],'reserved':reserved,'remaining':result['net']-reserved,'available_at':due,
        'status':'AVAILABLE' if as_ist(now or utcnow())>=due else 'ACCRUED','policy':policy,'minimum':policy.minimum_payout}