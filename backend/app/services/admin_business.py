"""Read-only marketplace presentation. No new prices, allocations or financial writes."""
from datetime import timedelta
from decimal import Decimal
from sqlalchemy import select,func,case,exists,or_,inspect
from fastapi import HTTPException
from app.core.time import utcnow,as_ist,ist_today,ist_day_bounds
from app.core.config import settings
from app.core.reporting_range import reporting_range
from app.models.auth import User,Role,UserRole
from app.models.gym import Gym
from app.models.membership import UserMembership,MembershipPause
from app.models.booking import Booking
from app.models.access import Checkin,AccessQrToken
from app.models.payment_checkout import PaymentCheckout
from app.models.checkout_funding import CheckoutFunding
from app.models.wallet import WalletAccount,WalletTransaction
from app.services.admin_financial_service import AdminFinancialService,amount
from app.services.admin_financial_queries import visits,paid_checkouts,booking_values


def membership_state():
    now=utcnow().replace(tzinfo=None)
    paused=exists(select(MembershipPause.id).where(MembershipPause.membership_id==UserMembership.id,
        MembershipPause.start_date<=ist_today(),MembershipPause.end_date>=ist_today()))
    return case((UserMembership.status=='CANCELLED','CANCELLED'),
        (UserMembership.payment_status!='PAID','UNPAID'),(UserMembership.end_at<=now,'EXPIRED'),
        (or_(UserMembership.status=='PAUSED',paused),'PAUSED'),(UserMembership.start_at>now,'UPCOMING'),
        (UserMembership.status=='ACTIVE','ACTIVE'),else_=UserMembership.status)


def memberships(db,*,q='',status=None,kind=None,gym_id=None,user_id=None,mode=None,limit=20,offset=0):
    state=membership_state()
    query=select(UserMembership,User,Gym.name.label('gym_name'),state.label('display_status'),PaymentCheckout.mode).join(User,User.id==UserMembership.user_id).outerjoin(Gym,Gym.id==UserMembership.gym_id).outerjoin(PaymentCheckout,PaymentCheckout.id==UserMembership.gateway_checkout_id)
    if q:
        match=q.strip()
        query=query.where(or_(User.first_name.contains(match,autoescape=True),User.last_name.contains(match,autoescape=True),User.email.contains(match,autoescape=True),Gym.name.contains(match,autoescape=True)))
    if status:query=query.where(state==status)
    if kind:query=query.where(UserMembership.membership_type==kind)
    if gym_id:query=query.where(UserMembership.gym_id==gym_id)
    if user_id:query=query.where(UserMembership.user_id==user_id)
    if mode:query=query.where(PaymentCheckout.mode==mode)
    total=db.scalar(select(func.count()).select_from(query.subquery()))
    rows=db.execute(query.order_by(UserMembership.created_at.desc(),UserMembership.id.desc()).limit(limit).offset(offset)).all()
    return {'total':total,'items':[{'id':m.id,'customer_id':u.id,'customer_name':' '.join(v for v in (u.first_name,u.last_name) if v) or f'Customer #{u.id}',
        'email':u.email,'gym_id':m.gym_id,'gym_name':name,'kind':m.membership_type,'status':display,'payment_status':m.payment_status,
        'purchased_at':as_ist(m.created_at).isoformat(),'valid_from':as_ist(m.start_at).isoformat(),'valid_until':as_ist(m.end_at).isoformat(),
        'purchase_amount':amount(m.paid_amount),'mode':environment} for m,u,name,display,environment in rows]}


def customer_activity(db,user_id):
    if not db.get(User,user_id):raise HTTPException(404,'User not found')
    account=db.scalar(select(WalletAccount).where(WalletAccount.user_id==user_id))
    balance=None
    if account:
        signed=case((WalletTransaction.direction=='IN',WalletTransaction.amount),else_=-WalletTransaction.amount)
        net=db.scalar(select(func.coalesce(func.sum(signed),0)).where(WalletTransaction.account_id==account.id,WalletTransaction.currency==account.currency))
        if net==account.balance:balance=amount(net)
    rows=db.scalars(select(Booking).where(Booking.user_id==user_id).order_by(Booking.created_at.desc(),Booking.id.desc()).limit(20))
    return {'wallet_balance':balance if account else '0.00','wallet_mode':account.payment_mode if account else None,
        'memberships':memberships(db,user_id=user_id),'bookings':[{'id':b.id,'date':str(b.slot_date),'status':b.status,'gym_id':b.gym_id,'amount':amount(b.total_price)} for b in rows]}


def booking_attendance(db,booking_id):
    booking=db.get(Booking,booking_id)
    if not booking:raise HTTPException(404,'Booking not found')
    checkout=db.get(PaymentCheckout,booking.checkout_id) if booking.checkout_id else None
    valid=visits(checkout.mode) if checkout else None
    count=db.scalar(select(func.count()).select_from(valid).where(valid.c.booking_id==booking.id)) if valid is not None else 0
    return {'completed_visitors':count,'purchased_visitors':booking.quantity,
        'no_show':booking.attendance_status=='NO_SHOW' and booking.attendance_marked_at is not None and count==0,
        'marked_at':as_ist(booking.attendance_marked_at).isoformat() if booking.attendance_marked_at else None}


def summary(db,*,date_from=None,date_to=None,mode=None,gym_id=None):
    mode=mode or settings.gateway_mode
    base=AdminFinancialService(db).report(date_from=date_from,date_to=date_to,mode=mode,gym_id=gym_id)
    from datetime import date
    first,last=date.fromisoformat(base['date_from']),date.fromisoformat(base['date_to'])
    start,end=ist_day_bounds(first)[0].replace(tzinfo=None),ist_day_bounds(last)[1].replace(tzinfo=None)
    admissions=visits(mode)
    # Operational no-show totals require the existing explicit mark timestamp.
    # A missed scan or elapsed booking alone is never a no-show.
    marked=select(func.count(Booking.id)).join(PaymentCheckout,PaymentCheckout.id==Booking.checkout_id).where(
        PaymentCheckout.mode==mode,Booking.status=='CONFIRMED',Booking.attendance_status=='NO_SHOW',
        Booking.attendance_marked_at.is_not(None),Booking.slot_date.between(first,last),
        ~exists(select(Checkin.id).where(Checkin.booking_id==Booking.id,Checkin.status=='SUCCESS')))
    if gym_id:marked=marked.where(Booking.gym_id==gym_id)
    base['bookings']['no_show']=db.scalar(marked) or 0
    from app.services.admin_financial_service import rate
    base['bookings']['no_show_rate']=rate(base['bookings']['no_show'],base['bookings']['attended']+base['bookings']['no_show'])
    query=select(admissions.c.event_at,admissions.c.category,UserMembership.membership_type,admissions.c.gym_id,admissions.c.user_id).join(Checkin,Checkin.id==admissions.c.visit_id).outerjoin(UserMembership,UserMembership.id==Checkin.membership_id).join(AccessQrToken,AccessQrToken.id==Checkin.qr_token_id).where(admissions.c.event_at>=start,admissions.c.event_at<end,admissions.c.event_at<AccessQrToken.expires_at)
    if gym_id:query=query.where(admissions.c.gym_id==gym_id)
    counts=dict(individual=0,single_gym=0,multi_gym=0)
    series={str(first+timedelta(days=i)):{'date':str(first+timedelta(days=i)),**counts,'individual_collections':'0.00','single_gym_collections':'0.00','multi_gym_collections':'0.00'} for i in range((last-first).days+1)}
    gym_visits={};customer_visits={}
    for at,category,kind,gid,customer_id in db.execute(query):
        key='individual' if category=='BOOKING' else 'single_gym' if kind=='SINGLE_GYM' else 'multi_gym'
        counts[key]+=1;series[str(as_ist(at).date())][key]+=1
        gym_visits[gid]=gym_visits.get(gid,0)+1
        customer_visits[customer_id]=customer_visits.get(customer_id,0)+1
    for gym in base['gyms']:gym['visits']=gym_visits.get(gym['id'],0)
    base['customers']['most_active']=[{'user_id':uid,'visits':count} for uid,count in sorted(customer_visits.items(),key=lambda item:(-item[1],item[0]))[:20]]
    # Capture time is evidence, not checkout creation/first provider observation.
    # Do not substitute those dates, and never collect again on an included visit.
    paid=paid_checkouts(db,mode)
    # A provider capture alone is not a fulfilled purchase. Reuse the existing
    # booking funding projection and membership ownership/transfer safeguards.
    from app.models.customer_policy import MembershipTransfer
    values=booking_values(db,mode)
    booked=exists(select(values.c.booking_id).where(values.c.checkout_id==paid.c.checkout_id))
    member=exists(select(UserMembership.id).where(UserMembership.gateway_checkout_id==paid.c.checkout_id,
        UserMembership.payment_status=='PAID',UserMembership.currency=='INR',
        UserMembership.paid_amount==paid.c.total,UserMembership.membership_type==paid.c.kind,
        or_(UserMembership.user_id==paid.c.user_id,exists(select(MembershipTransfer.id).where(
            MembershipTransfer.membership_id==UserMembership.id,MembershipTransfer.original_user_id==paid.c.user_id,
            MembershipTransfer.recipient_user_id==UserMembership.user_id,MembershipTransfer.status=='COMPLETED')))))
    purchases=list(db.execute(select(PaymentCheckout,paid.c.total,paid.c.wallet,paid.c.gateway).join(paid,paid.c.checkout_id==PaymentCheckout.id).where(
        or_(PaymentCheckout.kind.in_(['BOOKING','CART']) & booked,PaymentCheckout.kind.in_(['SINGLE_GYM','MULTI_GYM']) & member))))
    has_evidence=inspect(db.connection()).has_table('financial_source_evidence')
    from app.models.source_evidence import SourceEvidence
    from app.services.marketplace_allocations import digest
    # Batch supporting reads; retain identical evidence validation and unknown-date
    # behavior. Chunk IDs to bound SQL parameter lists, never query once per purchase.
    evidence_by_checkout={};gyms_by_checkout={};resolved_by_checkout={}
    ids=[row[0].id for row in purchases]
    for offset in range(0,len(ids),500):
        batch=ids[offset:offset+500]
        if has_evidence:
            for source in db.scalars(select(SourceEvidence).where(SourceEvidence.checkout_id.in_(batch),SourceEvidence.mode==mode,
                    SourceEvidence.event_type.in_(['PAYMENT_CAPTURED','PAYMENT_DETAILS_VERIFIED']))):
                evidence_by_checkout.setdefault(source.checkout_id,[]).append(source)
        if gym_id:
            for checkout_id,gid in db.execute(select(Booking.checkout_id,Booking.gym_id).where(Booking.checkout_id.in_(batch)).distinct()):
                gyms_by_checkout.setdefault(checkout_id,set()).add(gid)
        wallet_ids=[row[0].id for row in purchases[offset:offset+500] if not row[3]]
        if wallet_ids:
            resolved_by_checkout.update(db.execute(select(CheckoutFunding.checkout_id,CheckoutFunding.resolved_at).where(CheckoutFunding.checkout_id.in_(wallet_ids))).all())
    collections={key:Decimal(0) for key in counts};undated=0;unattributed=0
    exclusions=[];exclusion_reasons={};excluded_by_category={key:0 for key in collections}
    def exclude(checkout, reason):
        key='individual' if checkout.kind in {'BOOKING','CART'} else checkout.kind.lower()
        exclusions.append({'checkout_id':checkout.id,'category':key,'reason':reason})
        exclusion_reasons[reason]=exclusion_reasons.get(reason,0)+1
        excluded_by_category[key]+=1
    for checkout,total,wallet,gateway in purchases:
        if gym_id:
            if checkout.kind=='MULTI_GYM':continue # no invented cross-gym collection attribution
            if checkout.kind=='SINGLE_GYM' and checkout.snapshot.get('gym_id')!=gym_id:continue
            if checkout.kind in {'BOOKING','CART'}:
                gyms=gyms_by_checkout.get(checkout.id,set())
                if gym_id not in gyms:continue
                if gyms!={gym_id}:
                    unattributed+=1;exclude(checkout,'CROSS_GYM_COLLECTION_UNALLOCATED');continue
        timestamps=set()
        invalid_evidence=False
        if gateway and has_evidence:
            for source in evidence_by_checkout.get(checkout.id,[]):
                data=source.payload
                # An initial observation may lack capture time; later verified
                # details append that evidence without rewriting the first row.
                if source.occurred_at is None and source.evidence_status=='EVENT_TIME_UNAVAILABLE':
                    continue
                if (source.occurred_at and source.evidence_status=='VERIFIED_SOURCE' and source.amount==gateway
                        and source.currency==checkout.currency and isinstance(data,dict) and digest(data)==source.payload_hash
                        and data.get('verification_status')=='VERIFIED' and data.get('verification_source')=='AUTHENTICATED_PROVIDER_FETCH'
                        and data.get('provider_payment_id')==checkout.gateway_payment_id):
                    timestamps.add(source.occurred_at)
                else:invalid_evidence=True
        elif not gateway:
            resolved=resolved_by_checkout.get(checkout.id)
            if resolved:timestamps.add(resolved)
        if len(timestamps)!=1 or invalid_evidence:
            undated+=1
            exclude(checkout,'PAYMENT_EVIDENCE_INVALID' if invalid_evidence else
                'PAYMENT_DATE_CONFLICT' if len(timestamps)>1 else
                'PAYMENT_DATE_SCHEMA_MISSING' if gateway and not has_evidence else 'PAYMENT_DATE_MISSING')
            continue
        at=next(iter(timestamps))
        if not start<=at<end:continue
        key='individual' if checkout.kind in {'BOOKING','CART'} else checkout.kind.lower()
        collections[key]+=total
        day=str(as_ist(at).date());series[day][key+'_collections']=amount(Decimal(series[day][key+'_collections'])+total)
    incomplete=bool(undated or unattributed)
    owner=commission=None
    required={'marketplace_allocations','gym_visit_payouts','owner_payouts','financial_source_evidence','gym_monthly_calculations','membership_visit_fees'}
    missing_tables=sorted(required-set(inspect(db.connection()).get_table_names()))
    sharing_reason='ALLOCATION_SCHEMA_MISSING' if missing_tables else 'NO_RECORDED_ALLOCATIONS'
    if not missing_tables:
        from app.services.marketplace_reporting import report
        ledger=report(db,mode=mode,date_from=first,date_to=last,gym_id=gym_id)
        if ledger['available'] and (ledger['total'] or ledger['visit_total']):
            # Recorded earnings only, never infer a share from collections.
            owner=ledger['totals']['gym_gross_share']
            visit_gross=ledger['totals']['multi_gym_visit_payout']
            owner=amount(Decimal(owner)+Decimal(visit_gross)) if visit_gross is not None else None
            commission=ledger['totals']['fitigo_net_commission']
            sharing_reason='RECORDED_ALLOCATION_EVIDENCE_INCOMPLETE'
    sharing_availability={key:{'status':'RECORDED_SUBTOTAL' if value is not None else 'UNAVAILABLE',
        'reason':None if value is not None else sharing_reason,'missing_tables':missing_tables}
        for key,value in (('gym_gross_share',owner),('fitigo_commission',commission))}
    return {'date_from':base['date_from'],'date_to':base['date_to'],'mode':mode,'options':base['options'],
        'overall':{'visits':sum(counts.values()),'bookings':base['bookings']['total'],'users':base['platform']['total_users'],
            'gyms':db.scalar(select(func.count(Gym.id))),'active_memberships':sum(v['active'] for v in base['memberships']['categories'].values())},
        'visits':{**counts,'completed':sum(counts.values()),'upcoming':base['bookings']['upcoming'],'no_shows':base['bookings']['no_show'],'cancelled':base['bookings']['cancelled']},
        'collections':{'categories':{k:None if excluded_by_category[k] else amount(v) for k,v in collections.items()},
            'category_complete':{key:not count for key,count in excluded_by_category.items()},
            'excluded_by_category':excluded_by_category,'sharing_availability':sharing_availability,
            'total':None if incomplete else amount(sum(collections.values(),Decimal(0))),
            'known_dated_total':amount(sum(collections.values(),Decimal(0))),
            'known_dated_categories':{key:amount(value) for key,value in collections.items()},
            'exclusions':exclusions,'exclusion_reasons':exclusion_reasons,
            'undated_purchases':undated,'unattributed_purchases':unattributed,
            'gym_gross_share':owner,'fitigo_commission':commission,'complete':not incomplete},
        'wallet':base['wallet'],'bookings':base['bookings'],'memberships':base['memberships'],'customers':base['customers'],
        'gyms':base['gyms'],'series':list(series.values()),
        'definitions':{'collections':'Gross verified paid purchase consideration, counted once on confirmed payment date; includes wallet-funded purchases and later wallet-credited cancellations, excludes wallet top-ups and provider-refunded payments. Cancellation wallet credits are reported separately, not deducted here. This is not new gateway cash, net retained revenue or earnings. Missing dates are not guessed.',
            'earnings':'Recorded gym entitlement and FitiGo net commission only; may cover fewer transactions than collections. Multi-Gym collections are not FitiGo earnings.',
            'visits':'Successful matched check-ins within the QR validity window, deduplicated by purchased visitor or membership daily access.',
            'rates':'Cancellation rate: cancelled / scheduled bookings. No-show rate: authorized no-shows / (attended bookings + authorized no-shows).',
            'inventory':'Registered users, gyms, active memberships and unused wallet are current balances. Other measures follow the selected dates.'}}