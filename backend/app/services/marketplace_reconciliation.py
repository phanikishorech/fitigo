"""Bounded review-only historical exception report. Never reprices or mutates."""
from sqlalchemy import select,func,inspect
from app.models.booking import Booking,Payment
from app.models.membership import UserMembership
from app.models.payment_checkout import PaymentCheckout,PaymentAttempt
from app.models.access import Checkin
from app.models.customer_policy import BookingCancellation
from app.models.financial_agreement import FinancialAgreementVersion
from app.models.source_evidence import SourceEvidence,SourceOutbox,GymOwnerEvidence
from app.models.marketplace_allocation import MarketplaceAllocation


def report(db,mode,limit=50,offset=0):
    inspector=inspect(db.connection())
    available={name:inspector.has_table(name) for name in ('marketplace_allocations','financial_source_evidence','financial_source_outbox','gym_owner_evidence')}
    rows=[]
    bookings=list(db.scalars(select(Booking).join(PaymentCheckout,PaymentCheckout.id==Booking.checkout_id)
        .where(PaymentCheckout.mode==mode).order_by(Booking.id).limit(limit).offset(offset)))
    members=list(db.scalars(select(UserMembership).join(PaymentCheckout,PaymentCheckout.id==UserMembership.gateway_checkout_id)
        .where(PaymentCheckout.mode==mode).order_by(UserMembership.id).limit(limit).offset(offset)))
    for kind,items in (('BOOKING',bookings),('MEMBERSHIP',members)):
        for item in items:
            checkout_id=item.checkout_id if kind=='BOOKING' else item.gateway_checkout_id
            checkout=db.get(PaymentCheckout,checkout_id)
            issues=[]
            allocations=[]
            if available['marketplace_allocations']:
                query=select(MarketplaceAllocation).where(MarketplaceAllocation.mode==mode,MarketplaceAllocation.entry_kind=='ORIGINAL')
                query=query.where(MarketplaceAllocation.booking_id==item.id) if kind=='BOOKING' else query.where(MarketplaceAllocation.membership_id==item.id)
                allocations=list(db.scalars(query))
            if not allocations:
                issues.append('AGREEMENT_NOT_PINNED')
                if kind=='BOOKING':
                    payment=db.scalar(select(Payment).where(Payment.booking_id==item.id))
                    if payment and payment.status=='PAID':issues.append('PAID_BOOKING_WITHOUT_ALLOCATION')
                elif item.payment_status=='PAID':issues.append('MEMBERSHIP_WITHOUT_ALLOCATION' if item.membership_type=='SINGLE_GYM' else 'MULTI_GYM_COLLECTION_UNALLOCATED_EARNINGS_POLICY')
            if kind=='BOOKING':
                scans=list(db.scalars(select(Checkin).where(Checkin.booking_id==item.id,Checkin.status=='SUCCESS')))
                if not scans and item.attendance_status!='NO_SHOW':issues.append('ATTENDANCE_EVIDENCE_MISSING')
                if scans and len(scans)<item.quantity:issues.append('PARTIAL_ATTENDANCE_REMAINING_VISITORS_UNRESOLVED')
                if item.status=='CANCELLED' and not db.scalar(select(BookingCancellation.id).where(BookingCancellation.booking_id==item.id)):
                    issues.append('CANCELLATION_CREDIT_EVIDENCE_MISSING')
            if available['financial_source_evidence']:
                evidence=list(db.scalars(select(SourceEvidence).where(SourceEvidence.checkout_id==checkout_id,SourceEvidence.mode==mode)))
                fee=any(row.payload.get('fee_amount') is not None for row in evidence)
                owner=False
                if available['gym_owner_evidence'] and evidence:
                    owner=db.scalar(select(GymOwnerEvidence.id).where(GymOwnerEvidence.evidence_id.in_([row.id for row in evidence])).limit(1)) is not None
                if not owner:issues.append('HISTORICAL_OWNER_EVIDENCE_MISSING')
                if not any('transaction_basis' in row.payload for row in evidence):issues.append('DISCOUNT_TAX_BASIS_EVIDENCE_MISSING')
            else:
                fee=False;issues.extend(['SOURCE_EVIDENCE_SCHEMA_NOT_DEPLOYED','HISTORICAL_OWNER_EVIDENCE_MISSING'])
            if checkout.amount>0 and not fee:issues.append('ACTUAL_GATEWAY_FEE_EVIDENCE_MISSING')
            if issues:rows.append({'source_type':kind,'source_id':item.id,'checkout_id':checkout_id,'mode':mode,'gym_id':item.gym_id,
                'customer_id':checkout.user_id,'issues':issues,'proposed_adjustment':None,'review_status':'REVIEW_ONLY'})
    inconsistent=0
    if available['financial_source_outbox'] and available['financial_source_evidence']:
        inconsistent=db.scalar(select(func.count(SourceOutbox.id)).join(SourceEvidence,SourceEvidence.id==SourceOutbox.evidence_id).where(
            SourceOutbox.mode==mode,((SourceOutbox.mode!=SourceEvidence.mode)|(SourceOutbox.source_id!=SourceEvidence.source_id)|(SourceOutbox.event_type!=SourceEvidence.event_type))))
    return {'mode':mode,'read_only':True,'historical_adjustments_enabled':False,'items':rows,'offset':offset,'limit_per_source_type':limit,
        'has_more':len(bookings)==limit or len(members)==limit,'inconsistent_source_events':inconsistent,
        'unclassified_environment_bookings':db.scalar(select(func.count(Booking.id)).where(Booking.checkout_id.is_(None))),
        'unclassified_environment_memberships':db.scalar(select(func.count(UserMembership.id)).where(UserMembership.gateway_checkout_id.is_(None))),
        'notice':'Review only. Missing environment is not assigned test/live. No historical agreement or adjustment is proposed automatically; unlinked counts are global.'}