"""Read-only ledger aggregation; never calculates/posts new commission on GET."""
from datetime import timedelta
from decimal import Decimal
from sqlalchemy import select,func,inspect
from app.core.config import settings
from app.core.reporting_range import reporting_range
from app.core.time import ist_today,ist_day_bounds,as_ist
from app.models.marketplace_allocation import MarketplaceAllocation as Allocation
from app.models.gym_visit_payout import GymVisitPayout
from app.models.owner_payout import OwnerPayout,OwnerPayoutItem,OwnerPayoutAudit
from app.models.payment_checkout import PaymentCheckout
from app.models.source_evidence import SourceEvidence
from app.models.auth import User
from app.models.gym import Gym


def money(value):return format(value or Decimal(0),'.2f')


def filters(query,model,mode,gym_id,owner_id,category,gateway):
    query=query.where(model.mode==mode)
    if gym_id:query=query.where(model.gym_id==gym_id)
    if owner_id:query=query.where(model.owner_user_id==owner_id)
    if category:
        if model is GymVisitPayout:
            if category!='MULTI_GYM':query=query.where(False)
        else:query=query.where(model.category==category)
    if gateway:
        if gateway=='WALLET':
            if model is Allocation:query=query.where(Allocation.wallet_amount>0)
            else:query=query.where(PaymentCheckout.amount==0)
        else:query=query.where(PaymentCheckout.provider==gateway,PaymentCheckout.amount>0)
    return query


def report(db,*,mode,date_from=None,date_to=None,gym_id=None,owner_user_id=None,category=None,gateway=None,limit=25,offset=0):
    if mode not in {'test','live'}:
        from fastapi import HTTPException
        raise HTTPException(422,'Explicit test/live environment required.')
    first,last=reporting_range(date_from,date_to) or (ist_today()-timedelta(days=29),ist_today())
    start=ist_day_bounds(first)[0];end=ist_day_bounds(last+timedelta(days=1))[0]
    base={'mode':mode,'date_from':str(first),'date_to':str(last),'currency':'INR','statutory_reporting_enabled':False,
        'processing_enabled':settings.marketplace_allocations_enabled,'live_processing_enabled':settings.marketplace_live_allocations_enabled,
        'owners':[{'id':u.id,'name':' '.join(v for v in (u.first_name,u.last_name) if v) or f'User #{u.id}'} for u in db.scalars(
            select(User).where(User.id.in_(select(Gym.owner_user_id))).order_by(User.id))]}
    tables=('marketplace_allocations','gym_visit_payouts','owner_payouts','financial_source_evidence')
    if not all(inspect(db.connection()).has_table(t) for t in tables):
        return {**base,'available':False,'reason':'Marketplace migrations through c91dc50f4713 are not deployed. Unknown is not zero.'}
    historical_ids=set(db.scalars(select(Allocation.owner_user_id).where(Allocation.mode==mode))) | set(db.scalars(select(GymVisitPayout.owner_user_id).where(GymVisitPayout.mode==mode)))
    known_ids={r['id'] for r in base['owners']}
    for user in db.scalars(select(User).where(User.id.in_(historical_ids-known_ids)).order_by(User.id)):
        base['owners'].append({'id':user.id,'name':' '.join(v for v in (user.first_name,user.last_name) if v) or f'User #{user.id}'})
    query=filters(select(Allocation).join(PaymentCheckout,PaymentCheckout.id==Allocation.checkout_id),Allocation,mode,gym_id,owner_user_id,category,gateway)
    roots=list(db.scalars(query.where(Allocation.entry_kind=='ORIGINAL',Allocation.occurred_at>=start,Allocation.occurred_at<end)))
    root_ids=[r.id for r in roots]
    # Cohort report: original eligible service dates plus all corrections to those
    # roots as of now, regardless of correction arrival date. Avoid orphaned deltas.
    changes=list(db.scalars(select(Allocation).where(Allocation.mode==mode,
        (Allocation.reversal_of_id.in_(root_ids))|(Allocation.adjustment_of_id.in_(root_ids))))) if root_ids else []
    entries=roots+changes
    claims=list(db.execute(select(OwnerPayoutItem,OwnerPayout).join(OwnerPayout).where(
        OwnerPayoutItem.allocation_id.in_(root_ids),OwnerPayout.mode==mode)).all()) if root_ids else []
    totals={key:Decimal(0) for key in ('attended_commission','no_show_commission','single_gym_commission','gym_gross_share',
        'allocated_gateway_fees','gym_gateway_fee_share','fitigo_gateway_fee_share','known_owner_entitlement','fitigo_net_commission')}
    for entry in entries:
        key={'ATTENDED_BOOKING':'attended_commission','NO_SHOW':'no_show_commission','SINGLE_GYM':'single_gym_commission'}.get(entry.category)
        if key:totals[key]+=entry.fitigo_gross_commission
        totals['gym_gross_share']+=entry.gym_gross_share
        for key,column in (('allocated_gateway_fees','gateway_fee'),('gym_gateway_fee_share','gym_gateway_fee_share'),('fitigo_gateway_fee_share','fitigo_gateway_fee_share')):
            totals[key]+=getattr(entry,column) or Decimal(0)
    detail=[];unknown_fee=0;owner_paid=Decimal(0);reserved=Decimal(0);pending_payout=Decimal(0)
    for root in roots:
        adjustments=[r for r in changes if r.adjustment_of_id==root.id]
        reversed_row=any(r.reversal_of_id==root.id for r in changes)
        fee_known=root.gateway_fee is not None or any(r.entry_kind=='FEE_ADJUSTMENT' for r in adjustments)
        net=Decimal(0) if reversed_row else root.gym_gross_share-sum((r.gym_gateway_fee_share or Decimal(0) for r in [root,*adjustments]),Decimal(0)) if fee_known else None
        fitigo_net=Decimal(0) if reversed_row else root.fitigo_gross_commission-sum((r.fitigo_gateway_fee_share or Decimal(0) for r in [root,*adjustments]),Decimal(0)) if fee_known else None
        if net is None:unknown_fee+=1
        else:totals['known_owner_entitlement']+=net;totals['fitigo_net_commission']+=fitigo_net
        linked=[(item,payout) for item,payout in claims if item.allocation_id==root.id and payout.status!='REVERSED']
        paid=sum((item.amount for item,payout in linked if payout.status=='PAID'),Decimal(0))
        held=sum((item.amount for item,payout in linked if payout.status!='PAID'),Decimal(0))
        owner_paid+=paid;reserved+=held
        if net is not None:pending_payout+=net-paid
        customer=db.get(User,root.customer_id);gym=db.get(Gym,root.gym_id);owner=db.get(User,root.owner_user_id)
        state='REVERSED' if reversed_row else 'PAID' if linked and paid>= (net if net is not None else root.gym_gross_share) else linked[-1][1].status if linked else 'FEE_PENDING' if not fee_known else 'ACCRUED'
        availability_reason=None
        if state in {'ACCRUED','FEE_PENDING'}:
            from app.services.owner_payouts import financial_position
            from app.services.marketplace_calculation import AllocationBlocked
            try:state=financial_position(db,root)['status']
            except AllocationBlocked as error:availability_reason=error.code
        detail.append({'id':root.id,'transaction_reference':root.transaction_reference,'customer_id':root.customer_id,
            'customer_name':' '.join(v for v in (customer.first_name,customer.last_name) if v) if customer else None,
            'gym_id':root.gym_id,'gym_name':gym.name if gym else None,'owner_user_id':root.owner_user_id,
            'owner_name':' '.join(v for v in (owner.first_name,owner.last_name) if v) if owner else None,
            'category':root.category,'booking_id':root.booking_id,'membership_id':root.membership_id,'visitor_index':root.visitor_index,
            'eligible_amount':money(root.eligible_amount),'agreement_version_id':root.agreement_version_id,'agreement_version':root.agreement_version,
            'gym_gross_share':money(root.gym_gross_share),'fitigo_gross_commission':money(root.fitigo_gross_commission),
            'gateway_fee':money(sum((r.gateway_fee or Decimal(0) for r in [root,*adjustments]),Decimal(0))) if fee_known else None,
            'gym_gateway_fee_share':money(sum((r.gym_gateway_fee_share or Decimal(0) for r in [root,*adjustments]),Decimal(0))) if fee_known else None,
            'fitigo_gateway_fee_share':money(sum((r.fitigo_gateway_fee_share or Decimal(0) for r in [root,*adjustments]),Decimal(0))) if fee_known else None,
            'owner_net':money(net) if net is not None else None,'payout_status':state,'availability_reason':availability_reason,
            'payment_references':[p.payment_reference for _,p in linked if p.payment_reference],
            'occurred_at':as_ist(root.occurred_at).isoformat(),'entry_ids':[r.id for r in [root,*adjustments,*[r for r in changes if r.reversal_of_id==root.id]]],'reversed':reversed_row})
    visit_query=filters(select(GymVisitPayout).join(PaymentCheckout,PaymentCheckout.id==GymVisitPayout.checkout_id),GymVisitPayout,mode,gym_id,owner_user_id,category,gateway)
    visits=list(db.scalars(visit_query.where(GymVisitPayout.service_date>=first,GymVisitPayout.service_date<=last).order_by(GymVisitPayout.allocation_period,GymVisitPayout.id)))
    from app.services.gym_visit_payouts import monthly_position
    positions={r.id:monthly_position(db,r) if r.snapshot.get('method')=='MONTHLY_VERIFIED_VISIT_VOLUME' else
        {'gross':r.approved_amount,'net':r.approved_amount if r.fee_status=='WALLET_ONLY_NO_GATEWAY_FEE' else None,
            'status':r.status} for r in visits}
    visit_total=sum((p['gross'] or Decimal(0) for p in positions.values()),Decimal(0))
    visit_net=sum((p['net'] or Decimal(0) for p in positions.values()),Decimal(0))
    gross_pending=any(p['gross'] is None for p in positions.values())
    net_pending=any(p['net'] is None for p in positions.values())
    visit_claims=list(db.execute(select(OwnerPayoutItem,OwnerPayout).join(OwnerPayout).where(
        OwnerPayoutItem.visit_payout_id.in_([r.id for r in visits]),OwnerPayout.mode==mode,OwnerPayout.status!='REVERSED')).all()) if visits else []
    visit_paid=sum((item.amount for item,payout in visit_claims if payout.status=='PAID'),Decimal(0))
    reserved+=sum((item.amount for item,payout in visit_claims if payout.status!='PAID'),Decimal(0))
    monthly={}
    for r in visits:
        key=(str(r.allocation_period),r.gym_id,r.owner_user_id)
        item=monthly.setdefault(key,{'period':key[0],'gym_id':r.gym_id,'owner_user_id':r.owner_user_id,'visits':0,'amount':Decimal(0),'fee_status':r.fee_status})
        position=positions[r.id]
        item['visits']+=int(position['status']!='INVALIDATED')
        item['amount']+=position['gross'] or Decimal(0)
        item['pending']=item.get('pending',False) or position['gross'] is None
        if position['net'] is None:item['fee_status']='PENDING'
    # Actual money sent has its own payment-date scope; do not prorate bank cash
    # across gateway/category filtered allocation items without evidence.
    payout_query=select(OwnerPayout).where(OwnerPayout.mode==mode)
    if gym_id:payout_query=payout_query.where(OwnerPayout.gym_id==gym_id)
    if owner_user_id:payout_query=payout_query.where(OwnerPayout.owner_user_id==owner_user_id)
    if category:payout_query=payout_query.where(OwnerPayout.category==category)
    payout_ids=payout_query.with_only_columns(OwnerPayout.id)
    actual_audit=list(db.scalars(select(OwnerPayoutAudit).where(OwnerPayoutAudit.payout_id.in_(payout_ids),
        OwnerPayoutAudit.to_status.in_(['PAID','REVERSED']),OwnerPayoutAudit.actual_reference.is_not(None))))
    paid_cash=returned_cash=Decimal(0)
    from datetime import datetime
    from app.core.time import stored_instant
    for audit in actual_audit:
        actual_at=stored_instant(datetime.fromisoformat(audit.evidence['paid_at']))
        if start<=actual_at<end:
            if audit.to_status=='PAID':paid_cash+=Decimal(audit.evidence['amount'])
            elif audit.from_status=='PAID':returned_cash+=Decimal(audit.evidence['amount'])
    # Source-confirmed customer collections remain distinct from marketplace revenue.
    collections=select(SourceEvidence).join(PaymentCheckout,PaymentCheckout.id==SourceEvidence.checkout_id).where(
        SourceEvidence.mode==mode,SourceEvidence.event_type=='PAYMENT_CAPTURED',SourceEvidence.occurred_at>=start,SourceEvidence.occurred_at<end)
    if gateway in {'RAZORPAY','CASHFREE'}:collections=collections.where(PaymentCheckout.provider==gateway)
    cash_rows=list(db.scalars(collections)) if not gym_id and not owner_user_id and not category and gateway!='WALLET' else None
    undated_query=select(func.count(SourceEvidence.id)).join(PaymentCheckout,PaymentCheckout.id==SourceEvidence.checkout_id).where(SourceEvidence.mode==mode,SourceEvidence.event_type=='PAYMENT_CAPTURED',SourceEvidence.occurred_at.is_(None))
    if gateway in {'RAZORPAY','CASHFREE'}:undated_query=undated_query.where(PaymentCheckout.provider==gateway)
    undated=db.scalar(undated_query) if cash_rows is not None else None
    multi_collection_query=select(SourceEvidence).join(PaymentCheckout,PaymentCheckout.id==SourceEvidence.checkout_id).where(
        SourceEvidence.mode==mode,SourceEvidence.event_type=='PAYMENT_CAPTURED',PaymentCheckout.kind=='MULTI_GYM',
        SourceEvidence.occurred_at>=start,SourceEvidence.occurred_at<end)
    if gateway in {'RAZORPAY','CASHFREE'}:multi_collection_query=multi_collection_query.where(PaymentCheckout.provider==gateway)
    multi_collections=list(db.scalars(multi_collection_query)) if not gym_id and not owner_user_id and gateway!='WALLET' and category in (None,'MULTI_GYM') else None
    from app.services.admin_financial_service import AdminFinancialService
    wallet=AdminFinancialService(db).wallet_report(start,end,mode,gym_id,gateway)
    detail.sort(key=lambda r:(r['occurred_at'],r['id']),reverse=True)
    return {**base,'available':True,'totals':{**{key:money(v) for key,v in totals.items()},
        'known_allocated_gateway_fees':money(totals['allocated_gateway_fees']),
        'allocated_gateway_fees':money(totals['allocated_gateway_fees']) if not unknown_fee else None,
        'gym_gateway_fee_share':money(totals['gym_gateway_fee_share']) if not unknown_fee else None,
        'fitigo_gateway_fee_share':money(totals['fitigo_gateway_fee_share']) if not unknown_fee else None,
        'fitigo_net_commission':money(totals['fitigo_net_commission']) if not unknown_fee else None,
        'total_owner_payable':money(totals['known_owner_entitlement']+visit_net-owner_paid-visit_paid) if not unknown_fee and not net_pending else None,
        'pending_owner_payouts':money(pending_payout+visit_net-visit_paid) if not unknown_fee and not net_pending else None,
        'reserved_owner_entitlement':money(reserved),'cohort_settled_entitlement':money(owner_paid+visit_paid),
        'actual_payouts_made':money(paid_cash) if not gateway else None,
        'actual_payout_returns':money(returned_cash) if not gateway else None,
        'multi_gym_visit_payout':None if gross_pending else money(visit_total),'multi_gym_fitigo_earnings':None,
        'multi_gym_dated_collections':money(sum((r.amount or Decimal(0) for r in multi_collections),Decimal(0))) if multi_collections is not None else None,
        'dated_customer_collections':money(sum((r.amount or Decimal(0) for r in cash_rows),Decimal(0))) if cash_rows is not None else None,
        'wallet_liability':wallet.get('outstanding') if not owner_user_id and not category else None},
        'fee_pending_count':unknown_fee,'visit_fee_pending_count':sum(p['net'] is None for p in positions.values()),
        'undated_capture_count':undated,'items':detail[offset:offset+limit],'total':len(detail),
        'visit_total':len(visits),'visit_items':[{'id':r.id,'membership_id':r.membership_id,'customer_id':r.customer_id,
            'gym_id':r.gym_id,'owner_user_id':r.owner_user_id,'checkin_id':r.checkin_id,'daily_access_id':r.daily_access_id,
            'agreement_version_id':r.agreement_version_id,'service_date':str(r.service_date),'allocation_period':str(r.allocation_period),
            'approved_amount':money(positions[r.id]['gross']) if positions[r.id]['gross'] is not None else None,
            'net_amount':money(positions[r.id]['net']) if positions[r.id]['net'] is not None else None,
            'configured_amount':None if r.applied_cap is None else money(r.configured_amount),'status':positions[r.id]['status'],'fee_status':r.fee_status}
            for r in visits[offset:offset+limit]],
        'monthly_visits':[{**item,'amount':None if item.get('pending') else money(item['amount'])} for item in monthly.values()],
        'definitions':{'basis':'Allocation cohort by source service/activation date; corrections included as of now. No GET posts allocations.',
            'fees':'Only fees allocated to the selected source units, not all provider fees. Unknown fee net totals stay unavailable.',
            'payouts':'Actual payout cash uses payment date; cohort payable deducts settled entitlement including approved deductions.',
            'multi_gym':'Visit entitlement only. Earnings and unused-value treatment remain unapproved. Fee distribution blocks payout release.',
            'collections':'Capture evidence with known occurrence dates only; undated captures are excluded. Scoped provider cash is not guessed.'}}