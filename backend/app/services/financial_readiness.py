"""Read-only, source-traceable reconciliation. Never infer tax or post on GET."""
from decimal import Decimal, InvalidOperation
from sqlalchemy import inspect, select, func
from app.core.config import settings
from app.models.source_evidence import SourceEvidence
from app.models.payment_checkout import PaymentCheckout, PaymentAttempt
from app.models.checkout_funding import CheckoutFunding
from app.models.booking import Booking
from app.models.marketplace_allocation import MarketplaceAllocation
from app.models.gym_visit_payout import GymVisitPayout, GymMonthlyCalculation, MembershipVisitFee
from app.models.owner_payout import OwnerPayout, OwnerPayoutItem
from app.models.financial_agreement import FinancialAgreementVersion
from app.services.marketplace_allocations import digest
from app.services.marketplace_calculation import AllocationBlocked

GATES=('source_evidence_enabled','marketplace_allocations_enabled','marketplace_live_allocations_enabled','marketplace_payouts_enabled')
TABLES=('financial_source_evidence','financial_source_outbox','financial_agreement_pins','marketplace_allocations',
    'gym_visit_payouts','gym_monthly_calculations','membership_visit_fees','owner_payouts','owner_payout_items','checkout_funding','booking_funding','financial_review_events')


def money(value):
    return None if value is None else format(value,'.2f')


def exact(value):
    if value is None or isinstance(value,(float,bool)): return None
    try:
        result=Decimal(str(value))
        if not result.is_finite() or result<0 or result>Decimal('9999999999.99') or result!=result.quantize(Decimal('.01')): return None
        return result
    except (ValueError,InvalidOperation): return None


def tax_readiness(evidence):
    """Only immutable purchase basis, never provider fee-tax or current catalog.

    An explicit validated zero is evidence of zero, not a fallback. No new tax
    ingestion authority or admin-entered tax override is introduced here.
    """
    if evidence is None: return {'status':'UNKNOWN','tax_amount':None,'blockers':['PURCHASE_EVIDENCE_MISSING']}
    if getattr(evidence,'event_type','BOOKING_PURCHASE_RECORDED') not in {'BOOKING_PURCHASE_RECORDED','MEMBERSHIP_PURCHASE_RECORDED'}:
        return {'status':'INVALID','tax_amount':None,'blockers':['NOT_PURCHASE_TAX_EVIDENCE']}
    if digest(evidence.payload)!=evidence.payload_hash or evidence.evidence_status!='VERIFIED_SOURCE':
        return {'status':'INVALID','tax_amount':None,'blockers':['PURCHASE_EVIDENCE_INVALID']}
    basis=evidence.payload.get('transaction_basis') or {}
    tax=exact(basis.get('tax_amount'))
    blockers=[]
    if tax is None: blockers.append('TAX_EVIDENCE_MISSING' if basis.get('tax_amount') is None else 'TAX_EVIDENCE_INVALID')
    if basis.get('tax_status') in {'SOURCE_NOT_SUPPORTED','UNKNOWN'} and tax is not None:
        blockers.append('TAX_EVIDENCE_CONFLICT')
    price,discount=exact(basis.get('price_amount')),exact(basis.get('discount_amount'))
    if price is None: blockers.append('PRICE_EVIDENCE_MISSING')
    if discount is None: blockers.append('DISCOUNT_EVIDENCE_MISSING')
    if basis.get('currency')!='INR': blockers.append('CURRENCY_EVIDENCE_INVALID')
    representation=basis.get('price_representation')
    if representation not in {'GROSS_BEFORE_DISCOUNT','ALREADY_DISCOUNTED'}: blockers.append('PRICE_REPRESENTATION_MISSING')
    if price is not None and discount is not None:
        paid=price-discount if representation=='GROSS_BEFORE_DISCOUNT' else price
        if paid<0 or tax is not None and tax>paid: blockers.append('BASIS_DOES_NOT_RECONCILE')
    status='UNKNOWN' if tax is None else 'CONFIRMED_ZERO' if tax==0 else 'CONFIRMED_NONZERO'
    if 'TAX_EVIDENCE_CONFLICT' in blockers or 'BASIS_DOES_NOT_RECONCILE' in blockers: status='INVALID'
    return {'status':status,'tax_amount':money(tax),'blockers':blockers,'evidence_id':evidence.id,
        'payload_hash':evidence.payload_hash,'basis':basis}


def activation(db):
    schema=inspect(db.connection())
    missing=[name for name in TABLES if not schema.has_table(name)]
    return {'gates':{key:getattr(settings,key) for key in GATES},'missing_tables':missing,
        'schema_ready':not missing,'activation_authorized':False,'can_activate_from_ui':False,
        'checks':['Migration deployment needs explicit approval','Tax and source evidence must reconcile',
            'Pinned settlement policies must be complete','Open corrections must be reviewed',
            'Workers and financial gates require separate deployment approval'],
        'notice':'Readiness is not activation approval. No endpoint changes gates, starts workers or sends money.'}


def paginate(db,query,limit,offset):
    total=db.scalar(select(func.count()).select_from(query.subquery()))
    return list(db.scalars(query.limit(limit).offset(offset))),total


def source_rows(db,mode,gym_id,limit,offset):
    query=select(PaymentCheckout).where(PaymentCheckout.mode==mode,PaymentCheckout.kind.in_(['BOOKING','CART','SINGLE_GYM','MULTI_GYM']))
    if gym_id:
        query=query.where((PaymentCheckout.id.in_(select(Booking.checkout_id).where(Booking.gym_id==gym_id))) |
            (PaymentCheckout.snapshot['gym_id'].as_integer()==gym_id))
    checkouts,total=paginate(db,query.order_by(PaymentCheckout.created_at.desc(),PaymentCheckout.id),limit,offset)
    items=[]
    for checkout in checkouts:
        evidence=list(db.scalars(select(SourceEvidence).where(SourceEvidence.checkout_id==checkout.id,
            SourceEvidence.mode==mode,SourceEvidence.event_type.in_(['BOOKING_PURCHASE_RECORDED','MEMBERSHIP_PURCHASE_RECORDED']))))
        bookings=list(db.scalars(select(Booking).where(Booking.checkout_id==checkout.id).order_by(Booking.id)))
        units=[b for b in bookings if not gym_id or b.gym_id==gym_id] if checkout.kind in {'BOOKING','CART'} else [None]
        if not units and not gym_id: units=[None]
        for booking in units:
            matches=[e for e in evidence if not booking or e.payload.get('booking_id')==booking.id]
            result=tax_readiness(matches[0] if len(matches)==1 else None)
            if len(matches)>1: result['blockers'].append('AMBIGUOUS_PURCHASE_EVIDENCE')
            gid=booking.gym_id if booking else checkout.snapshot.get('gym_id')
            source=matches[0] if len(matches)==1 else None
            binding=(source.payload.get('financial_configuration') or {}) if source else {}
            if checkout.kind!='MULTI_GYM' and binding.get('status')!='PINNED': result['blockers'].append('GYM_CONFIGURATION_BINDING_MISSING')
            items.append({'id':f'{checkout.id}:{booking.id if booking else "membership"}','checkout_id':checkout.id,
                'booking_id':booking.id if booking else None,'gym_id':gid,'category':checkout.kind,
                'booking_outcome':booking.attendance_status if booking else None,
                'payment_status':checkout.status,'purchase_amount':money(booking.total_price if booking else
                    (db.get(CheckoutFunding,checkout.id).total_amount if db.get(CheckoutFunding,checkout.id) else checkout.amount)),
                'configuration_version_id':binding.get('agreement_version_id'),'tax':result,
                'trace':{'source_evidence_ids':[e.id for e in matches],'checkout_id':checkout.id},
                'percentage_allocation_blocked':checkout.kind!='MULTI_GYM' and bool(result['blockers'])})
    return items,total


def allocation_rows(db,mode,gym_id,category,limit,offset,corrections=False):
    query=select(MarketplaceAllocation).where(MarketplaceAllocation.mode==mode)
    if gym_id: query=query.where(MarketplaceAllocation.gym_id==gym_id)
    if category: query=query.where(MarketplaceAllocation.category==category)
    if corrections: query=query.where(MarketplaceAllocation.entry_kind!='ORIGINAL')
    rows,total=paginate(db,query.order_by(MarketplaceAllocation.occurred_at.desc(),MarketplaceAllocation.id),limit,offset)
    items=[]
    for row in rows:
        differences=[]
        if digest(row.calculation_snapshot)!=row.calculation_hash: differences.append('SNAPSHOT_HASH_MISMATCH')
        if row.gym_gross_share+row.fitigo_gross_commission!=row.eligible_amount: differences.append('GROSS_CONSERVATION_DIFFERENCE')
        if row.wallet_amount+row.gateway_amount!=row.customer_funded_amount: differences.append('FUNDING_CONSERVATION_DIFFERENCE')
        if row.gateway_fee is not None and (row.gym_gateway_fee_share is None or row.fitigo_gateway_fee_share is None or row.gym_gateway_fee_share+row.fitigo_gateway_fee_share!=row.gateway_fee): differences.append('FEE_CONSERVATION_DIFFERENCE')
        from app.services.commercial_settlement import readiness
        agreement=db.get(FinancialAgreementVersion,row.agreement_version_id)
        settlement=readiness((agreement.terms.get('financial_settings') or {}).get('settlements') if agreement else None,row.category)
        from app.services.owner_payouts import financial_position
        availability=None
        if row.entry_kind=='ORIGINAL':
            try:
                position=financial_position(db,row)
                availability={'status':position['status'],'unreserved_net':money(position['remaining']),
                    'reserved_including_paid':money(position['reserved']),'available_at':position['available_at'].isoformat()}
            except AllocationBlocked as error:availability={'status':error.code,'reason':str(error)}
        items.append({'id':row.id,'category':row.category,'gym_id':row.gym_id,'entry_kind':row.entry_kind,
            'settlement_readiness':settlement,'payout_availability':availability,
            'gross_entitlement':money(row.gym_gross_share),'fitigo_gross_earnings':money(row.fitigo_gross_commission),
            'gym_fee':money(row.gym_gateway_fee_share),'fitigo_fee':money(row.fitigo_gateway_fee_share),
            'net_payable':money(row.gym_owner_net_entitlement),'fitigo_net_earnings':money(row.fitigo_net_commission),
            'customer_funded_basis':money(row.customer_funded_amount),'differences':differences,
            'trace':{'checkout_id':row.checkout_id,'source_evidence_id':row.source_evidence_id,
                'source_event_id':row.source_event_id,'agreement_version_id':row.agreement_version_id,
                'agreement_pin_id':row.agreement_pin_id,'calculation_hash':row.calculation_hash,
                'basis_evidence_id':row.calculation_snapshot.get('basis_evidence_id'),
                'fee_evidence_id':row.calculation_snapshot.get('fee_evidence_id'),
                'reversal_of_id':row.reversal_of_id,'adjustment_of_id':row.adjustment_of_id}})
    return items,total


def monthly_rows(db,mode,gym_id,limit,offset):
    from app.services.gym_visit_payouts import monthly_position,latest_month
    query=select(GymVisitPayout).where(GymVisitPayout.mode==mode)
    if gym_id: query=query.where(GymVisitPayout.gym_id==gym_id)
    rows,total=paginate(db,query.order_by(GymVisitPayout.allocation_period.desc(),GymVisitPayout.id),limit,offset)
    items=[]
    for row in rows:
        try:
            pos=monthly_position(db,row) if row.snapshot.get('method')=='MONTHLY_VERIFIED_VISIT_VOLUME' else {'gross':row.approved_amount,'net':None,'status':'LEGACY_REVIEW'}
            month=latest_month(db,mode,row.gym_id,row.allocation_period)
        except AllocationBlocked as error: pos={'gross':None,'net':None,'status':error.code};month=None
        differences=[]
        if month and sum((Decimal(v['gross_amount']) for v in month.snapshot['visits']),Decimal(0))!=month.gross_amount:
            differences.append('MONTHLY_VISIT_SUM_DIFFERENCE')
        items.append({'id':row.id,'gym_id':row.gym_id,'period':str(row.allocation_period),
            'gross_entitlement':money(pos['gross']),'net_payable':money(pos['net']),
            'gym_fee':money(pos.get('gym_fee')),'fitigo_fee':money(pos.get('fitigo_fee')),
            'fitigo_earnings':None,'status':pos['status'],'differences':differences,'trace':{'checkout_id':row.checkout_id,
                'membership_id':row.membership_id,'checkin_id':row.checkin_id,'daily_access_id':row.daily_access_id,
                'source_evidence_id':row.source_evidence_id,'agreement_version_id':row.agreement_version_id,
                'snapshot_hash':row.snapshot_hash,'monthly_calculation_id':month.id if month else None,
                'monthly_revision':month.revision if month else None}})
    return items,total


def fee_rows(db,mode,gym_id,limit,offset):
    query=select(PaymentCheckout).where(PaymentCheckout.mode==mode,PaymentCheckout.status=='PAID')
    if gym_id: query=query.where(PaymentCheckout.id.in_(select(Booking.checkout_id).where(Booking.gym_id==gym_id)) |
        PaymentCheckout.id.in_(select(GymVisitPayout.checkout_id).where(GymVisitPayout.gym_id==gym_id)) |
        (PaymentCheckout.snapshot['gym_id'].as_integer()==gym_id))
    rows,total=paginate(db,query.order_by(PaymentCheckout.created_at.desc(),PaymentCheckout.id),limit,offset)
    items=[]
    for checkout in rows:
        evidence=list(db.scalars(select(SourceEvidence).where(SourceEvidence.checkout_id==checkout.id,
            SourceEvidence.mode==mode,SourceEvidence.event_type.in_(['PAYMENT_CAPTURED','PAYMENT_DETAILS_VERIFIED']))))
        amounts=set();differences=[];ids=[]
        for source in evidence:
            data=source.payload
            if digest(data)!=source.payload_hash: differences.append('FEE_EVIDENCE_INTEGRITY');continue
            if data.get('provider_payment_id')!=checkout.gateway_payment_id or data.get('verification_status')!='VERIFIED' or data.get('verification_source')!='AUTHENTICATED_PROVIDER_FETCH': continue
            fee=exact(data.get('fee_amount'));tax=exact(data.get('fee_tax_amount'))
            if fee is None: continue
            if data.get('fee_basis')=='EXCLUDING_TAX':
                if tax is None: continue
                fee+=tax
            elif data.get('fee_basis')!='INCLUDING_TAX': continue
            elif tax is not None and tax>fee: differences.append('FEE_TAX_EXCEEDS_FEE');continue
            amounts.add(fee);ids.append(source.id)
        if len(amounts)>1: differences.append('CONFLICTING_PROVIDER_FEES')
        actual=next(iter(amounts)) if len(amounts)==1 else Decimal(0) if checkout.amount==0 and not amounts else None
        allocated=list(db.scalars(select(MarketplaceAllocation).where(MarketplaceAllocation.checkout_id==checkout.id)))
        allocated_fee=sum((r.gateway_fee or Decimal(0) for r in allocated),Decimal(0))
        if any(digest(r.calculation_snapshot)!=r.calculation_hash for r in allocated):differences.append('ALLOCATION_INTEGRITY_MISMATCH')
        budget=db.scalar(select(MembershipVisitFee).where(MembershipVisitFee.checkout_id==checkout.id))
        if budget:
            if digest(budget.snapshot)!=budget.snapshot_hash: differences.append('FEE_BUDGET_HASH_MISMATCH')
            parts=sum((Decimal(v['fee_amount']) for v in budget.snapshot['visits']),Decimal(0))
            if parts!=budget.actual_fee or any(Decimal(v['gym_fee'])+Decimal(v['fitigo_fee'])!=Decimal(v['fee_amount']) for v in budget.snapshot['visits']): differences.append('MEMBERSHIP_FEE_CONSERVATION_DIFFERENCE')
            allocated_fee+=budget.actual_fee
        remaining=None if actual is None else actual-allocated_fee
        if checkout.amount==0 and actual not in (None,Decimal(0)):differences.append('WALLET_ONLY_PROVIDER_FEE_CONFLICT')
        if remaining is not None and remaining<0: differences.append('OVERATTRIBUTED_PROVIDER_FEE')
        items.append({'id':checkout.id,'scope':'WHOLE_CHECKOUT_NOT_GYM_PRORATED','gateway_funded':money(checkout.amount),
            'actual_provider_fee':money(actual),'attributed_fee':money(allocated_fee),'unattributed_fee':money(remaining),
            'differences':differences,'status':'UNKNOWN' if actual is None else 'DIFFERENCE' if differences else 'RECONCILED' if remaining==0 else 'PENDING_ATTRIBUTION',
            'trace':{'checkout_id':checkout.id,'provider_payment_id':checkout.gateway_payment_id,'fee_evidence_ids':ids,
                'allocation_ids':[r.id for r in allocated],'membership_fee_budget_id':budget.id if budget else None}})
    return items,total


def collection_rows(db,mode,gym_id,limit,offset):
    query=select(PaymentCheckout).where(PaymentCheckout.mode==mode,PaymentCheckout.status=='PAID')
    # Cross-gym Multi-Gym collections cannot be attributed to an individual gym.
    if gym_id: query=query.where(PaymentCheckout.id.in_(select(Booking.checkout_id).where(Booking.gym_id==gym_id)) |
        (PaymentCheckout.snapshot['gym_id'].as_integer()==gym_id))
    rows,total=paginate(db,query.order_by(PaymentCheckout.created_at.desc(),PaymentCheckout.id),limit,offset)
    items=[]
    for checkout in rows:
        funding=db.get(CheckoutFunding,checkout.id)
        attempts=list(db.scalars(select(PaymentAttempt).where(PaymentAttempt.checkout_id==checkout.id,
            PaymentAttempt.status.in_(['SUCCESS','PARTIALLY_REFUNDED','REFUNDED']))))
        verified=checkout.amount==0 or len(attempts)==1 and attempts[0].external_id==checkout.gateway_payment_id and attempts[0].amount==checkout.amount and attempts[0].refunded_amount==0
        if funding and (funding.mode!=mode or funding.gateway_amount!=checkout.amount or funding.total_amount!=funding.wallet_amount+funding.gateway_amount): verified=False
        if funding and funding.wallet_amount:
            from app.models.wallet import WalletTransaction
            debit=db.get(WalletTransaction,funding.wallet_transaction_id)
            verified=verified and funding.state=='DEBITED' and debit is not None and debit.amount==funding.wallet_amount and debit.direction=='OUT' and debit.checkout_id==checkout.id
        total_amount=funding.total_amount if funding else checkout.amount
        allocations=list(db.scalars(select(MarketplaceAllocation).where(MarketplaceAllocation.checkout_id==checkout.id)))
        assigned=sum((r.customer_funded_amount for r in allocations),Decimal(0))
        if any(digest(r.calculation_snapshot)!=r.calculation_hash for r in allocations):verified=False
        items.append({'id':checkout.id,'category':checkout.kind,'scope':'WHOLE_CHECKOUT_NOT_GYM_PRORATED',
            'customer_consideration':money(total_amount) if verified else None,'gateway_collection':money(checkout.amount) if verified else None,
            'wallet_funded':money(funding.wallet_amount if funding else Decimal(0)) if verified else None,
            'unallocated_collection':money(total_amount if checkout.kind=='MULTI_GYM' else total_amount-assigned) if verified else None,
            'fitigo_earnings':None,'status':'COLLECTION_VERIFIED' if verified else 'COLLECTION_REVIEW',
            'trace':{'checkout_id':checkout.id,'funding_id':funding.checkout_id if funding else None,
                'payment_attempt_ids':[a.id for a in attempts],'allocation_ids':[r.id for r in allocations]}})
    return items,total


def balance_rows(db,mode,gym_id,limit,offset):
    query=select(OwnerPayout).where(OwnerPayout.mode==mode)
    if gym_id:query=query.where(OwnerPayout.gym_id==gym_id)
    rows,total=paginate(db,query.order_by(OwnerPayout.created_at.desc(),OwnerPayout.id),limit,offset)
    items=[]
    for row in rows:
        claims=list(db.scalars(select(OwnerPayoutItem).where(OwnerPayoutItem.payout_id==row.id)))
        items.append({'id':row.id,'gym_id':row.gym_id,'category':row.category,'status':row.status,
            'differences':[] if sum((i.amount for i in claims),Decimal(0))==row.entitlement_amount and row.amount+row.deduction_amount==row.entitlement_amount else ['PAYOUT_CLAIMS_DO_NOT_RECONCILE'],
            'reserved_entitlement':money(row.entitlement_amount if row.status not in {'PAID','REVERSED'} else Decimal(0)),
            'approved_not_paid':money(row.amount if row.status in {'APPROVED','PROCESSING'} else Decimal(0)),
            'actual_paid':money(row.amount if row.status=='PAID' else Decimal(0)),
            'pending_approval':money(row.amount if row.status=='PENDING_APPROVAL' else Decimal(0)),
            'deductions':money(row.deduction_amount),'trace':{'payout_id':row.id,'payment_reference':row.payment_reference,
                'items':[{'allocation_id':i.allocation_id,'visit_payout_id':i.visit_payout_id,'amount':money(i.amount)} for i in claims]}})
    return items,total


def report(db,*,mode,view,gym_id=None,limit=20,offset=0):
    from fastapi import HTTPException
    if mode not in {'test','live'}:raise HTTPException(422,'Explicit environment required.')
    controls=activation(db)
    base={'mode':mode,'view':view,'read_only':True,'controls':controls,
        'totals_scope':'CURRENT_PAGE_ONLY','notice':'Unknown is not zero. Collection, entitlement and cash settlement are distinct. No GET creates financial records.'}
    if controls['missing_tables']: return {**base,'available':False,'items':[],'total':0,'page_totals':{}}
    if view=='sources':items,total=source_rows(db,mode,gym_id,limit,offset)
    elif view in {'individual','single_gym','no_show','corrections'}:
        category={'individual':'ATTENDED_BOOKING','single_gym':'SINGLE_GYM','no_show':'NO_SHOW'}.get(view)
        items,total=allocation_rows(db,mode,gym_id,category,limit,offset,corrections=view=='corrections')
    elif view=='multi_gym':items,total=monthly_rows(db,mode,gym_id,limit,offset)
    elif view=='fees':items,total=fee_rows(db,mode,gym_id,limit,offset)
    elif view=='collections':items,total=collection_rows(db,mode,gym_id,limit,offset)
    elif view=='balances':items,total=balance_rows(db,mode,gym_id,limit,offset)
    else: raise HTTPException(422,'Unknown reconciliation view.')
    fields={'gross_entitlement','net_payable','gym_fee','fitigo_fee','fitigo_gross_earnings','fitigo_net_earnings',
        'actual_provider_fee','attributed_fee','unattributed_fee','customer_consideration','gateway_collection','wallet_funded',
        'unallocated_collection','reserved_entitlement','approved_not_paid','actual_paid','pending_approval','deductions'}
    totals={}
    for key in fields:
        values=[r[key] for r in items if key in r]
        if values:totals[key]=None if any(v is None for v in values) else money(sum((Decimal(v) for v in values),Decimal(0)))
    extra={}
    if view=='corrections':
        query=select(GymMonthlyCalculation).where(GymMonthlyCalculation.mode==mode)
        if gym_id:query=query.where(GymMonthlyCalculation.gym_id==gym_id)
        months,month_total=paginate(db,query.order_by(GymMonthlyCalculation.created_at.desc(),GymMonthlyCalculation.id),limit,offset)
        extra={'monthly_history_total':month_total,'monthly_history':[{'id':r.id,'gym_id':r.gym_id,'period':str(r.period),
            'revision':r.revision,'gross_amount':money(r.gross_amount),'source_evidence_id':r.source_evidence_id,
            'actor_id':r.actor_id,'snapshot_hash':r.snapshot_hash,'integrity_valid':digest(r.snapshot)==r.snapshot_hash,
            'previous_calculation_id':r.snapshot.get('previous_calculation_id'),
            'notice':'Historical revision; do not add versions together.'} for r in months]}
    return {**base,'available':True,'items':items,'total':total,'page_totals':totals,**extra}