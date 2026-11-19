"""Append-only, source-backed booking corrections. No customer balance writes."""
from decimal import Decimal
from uuid import uuid4
from sqlalchemy import select
from app.core.config import settings
from app.core.time import stored_instant, utcnow
from app.models.auth import User
from app.models.booking import Booking
from app.models.gym import Gym
from app.models.payment_checkout import PaymentCheckout
from app.models.source_evidence import SourceEvidence, SourceOutbox
from app.models.marketplace_allocation import MarketplaceAllocation
from app.services.marketplace_allocations import digest, verified_payload, fee_for_checkout
from app.services.marketplace_calculation import block, distribute_fee, equal_units, split_actual_fee

MONEY = ('price_amount','discount_amount','tax_amount','eligible_amount','customer_funded_amount',
    'wallet_amount','gateway_amount','gateway_fee','gym_gateway_fee_share','fitigo_gateway_fee_share',
    'gym_gross_share','fitigo_gross_commission','gym_owner_net_entitlement','fitigo_net_commission')


def locked_original(db, identifier):
    if not settings.marketplace_allocations_enabled: block('PROCESSING_DISABLED','Allocation processing is disabled.')
    original=db.get(MarketplaceAllocation,identifier)
    if not original or original.entry_kind!='ORIGINAL':block('SOURCE_DATA_MISSING','An original allocation is required.')
    if original.mode=='live' and not settings.marketplace_live_allocations_enabled:
        block('LIVE_PROCESSING_DISABLED','Live allocation processing is disabled.')
    if digest(original.calculation_snapshot)!=original.calculation_hash:block('RECONCILIATION_REQUIRED','Original calculation integrity mismatch.')
    db.scalar(select(User).where(User.id==original.customer_id).with_for_update())
    db.scalar(select(Gym).where(Gym.id==original.gym_id).with_for_update())
    if original.booking_id:db.scalar(select(Booking).where(Booking.id==original.booking_id).with_for_update())
    checkout=db.scalar(select(PaymentCheckout).where(PaymentCheckout.id==original.checkout_id).with_for_update().execution_options(populate_existing=True))
    if not checkout or checkout.mode!=original.mode:block('ENVIRONMENT_MISMATCH','Allocation checkout environment mismatch.')
    original=db.scalar(select(MarketplaceAllocation).where(MarketplaceAllocation.id==identifier).with_for_update())
    from app.models.owner_payout import OwnerPayout,OwnerPayoutItem
    if db.scalar(select(OwnerPayoutItem.id).join(OwnerPayout).where(OwnerPayoutItem.allocation_id==identifier,
        OwnerPayout.status!='REVERSED').with_for_update().limit(1)):
        block('PAYOUT_RESERVATION_REVIEW','Reserved/paid entitlement requires coordinated payout correction before allocation adjustment.')
    return original,checkout


def correction_event(db,event_id,original,kinds):
    event=db.scalar(select(SourceOutbox).where(SourceOutbox.id==event_id).with_for_update())
    source=db.get(SourceEvidence,event.evidence_id) if event else None
    if not source or event.mode!=original.mode or source.mode!=event.mode or source.checkout_id!=original.checkout_id or source.event_type!=event.event_type or source.source_id!=event.source_id or event.event_type not in kinds:
        block('SOURCE_DATA_MISMATCH','Correction event is not from the original transaction/environment.')
    verified_payload(source)
    return event,source


def values_from(original):
    return {c.name:getattr(original,c.name) for c in MarketplaceAllocation.__table__.columns if c.name not in
        {'id','idempotency_key','original_unit_key','created_at','calculation_snapshot','calculation_hash'}}


def reverse_cancelled(db,allocation_id,cancellation_event_id):
    with db.begin_nested():
        original,checkout=locked_original(db,allocation_id)
        if original.calculation_snapshot['policy'].get('cancellation_reversal')!='FULL_ORIGINAL_ALLOCATION':
            block('POLICY_MISSING','Cancellation reversal policy is not approved in the original agreement.')
        event,source=correction_event(db,cancellation_event_id,original,{'BOOKING_CANCELLED'})
        if not original.booking_id or source.payload.get('booking_id')!=original.booking_id or db.get(Booking,original.booking_id).status!='CANCELLED':
            block('SOURCE_NOT_ELIGIBLE','Matching cancelled booking evidence is required.')
        if source.occurred_at is None or source.evidence_status!='VERIFIED_SOURCE':
            block('SOURCE_DATA_MISSING','Confirmed cancellation occurrence time is required.')
        existing=db.scalar(select(MarketplaceAllocation).where(MarketplaceAllocation.reversal_of_id==original.id))
        if existing:return existing
        # Until payout workflow exists no paid claim can be adjusted here. Fee
        # corrections must be reversed with their own evidence, not silently lost.
        if db.scalar(select(MarketplaceAllocation.id).where(MarketplaceAllocation.adjustment_of_id==original.id).limit(1)):
            block('RECONCILIATION_REQUIRED','Allocation has adjustments; coordinated reversal is required.')
        values=values_from(original)
        for key in MONEY:values[key]=-values[key] if values[key] is not None else None
        snapshot={'original_allocation_id':original.id,'original_calculation_hash':original.calculation_hash,
            'cancellation_source_hash':source.payload_hash,'policy':original.calculation_snapshot['policy'],
            'statutory_reporting_enabled':False}
        values.update(source_event_id=event.id,source_evidence_id=source.id,source_type=source.source_type,source_record_id=source.source_id,
            allocation_key='reversal:'+original.id,entry_kind='REVERSAL',reversal_of_id=original.id,
            occurred_at=source.occurred_at)
        row=MarketplaceAllocation(id=str(uuid4()),idempotency_key=digest({'reverse':original.id}),
            created_at=stored_instant(utcnow()),calculation_snapshot=snapshot,calculation_hash=digest(snapshot),**values)
        db.add(row);db.flush();return row


def apply_late_fee(db,allocation_id,fee_event_id):
    with db.begin_nested():
        original,checkout=locked_original(db,allocation_id)
        if checkout.status!='PAID':block('SOURCE_NOT_ELIGIBLE','Refunded/unresolved purchase needs correction review before late fee posting.')
        if original.booking_id and db.get(Booking,original.booking_id).status!='CONFIRMED':
            block('SOURCE_NOT_ELIGIBLE','Cancelled booking requires coordinated reversal review.')
        event,source=correction_event(db,fee_event_id,original,{'PAYMENT_CAPTURED','PAYMENT_DETAILS_VERIFIED'})
        if original.gateway_fee is not None:block('RECONCILIATION_REQUIRED','Known fee corrections require explicit reversal/replacement review.')
        if db.scalar(select(MarketplaceAllocation.id).where(MarketplaceAllocation.reversal_of_id==original.id)):
            block('SOURCE_NOT_ELIGIBLE','Cannot charge a reversed allocation.')
        fee,fee_source_id=fee_for_checkout(db,checkout)
        if fee is None or fee_source_id!=source.id:block('SOURCE_DATA_MISSING','Matching unambiguous actual fee evidence is required.')
        prior=db.scalar(select(MarketplaceAllocation).where(MarketplaceAllocation.adjustment_of_id==original.id,
            MarketplaceAllocation.entry_kind=='FEE_ADJUSTMENT').with_for_update())
        if prior:
            if prior.calculation_snapshot['fee_total']!=str(fee):block('RECONCILIATION_REQUIRED','Late fee conflicts with prior adjustment.')
            return prior
        context=original.calculation_snapshot['fee_context'];policy=original.calculation_snapshot['policy']
        weights=[Decimal(v) for v in context['line_weights']]
        units=[Decimal(v) for v in context['unit_weights']]
        if policy.get('fee_partition_order') == 'LINE_THEN_CONFIGURED_PARTIES':
            line_fee=distribute_fee(fee,weights)[context['line_index']]
            percent=Decimal(original.calculation_snapshot['commercial_shares']['gateway_fee']['gym_percent'])
            gym,fitigo=split_actual_fee(line_fee,policy['fee_residual'],percent)
        else:
            gym,fitigo=split_actual_fee(fee,policy['fee_residual'])
        if sum(weights) and policy.get('fee_partition_order') != 'LINE_THEN_CONFIGURED_PARTIES':
            gym=distribute_fee(gym,weights)[context['line_index']]
            fitigo=distribute_fee(fitigo,weights)[context['line_index']]
        elif not sum(weights) and len(weights)!=1:block('RECONCILIATION_REQUIRED','No gateway weighting for a multi-line actual charge.')
        if sum(units):
            gym=distribute_fee(gym,units)[context['unit_index']]
            fitigo=distribute_fee(fitigo,units)[context['unit_index']]
        else:
            gym=equal_units(gym,len(units),context['wallet_fee_residual'])[context['unit_index']]
            fitigo=equal_units(fitigo,len(units),context['wallet_fee_residual'])[context['unit_index']]
        values=values_from(original)
        for key in MONEY:values[key]=Decimal('0.00')
        values.update(gateway_fee=gym+fitigo,gym_gateway_fee_share=gym,fitigo_gateway_fee_share=fitigo,
            gym_owner_net_entitlement=-gym,fitigo_net_commission=-fitigo,fee_status='VERIFIED',
            calculation_status='FEE_ADJUSTMENT',source_event_id=event.id,source_evidence_id=source.id,
            source_type=source.source_type,source_record_id=source.source_id,allocation_key='fee:'+original.id,
            entry_kind='FEE_ADJUSTMENT',adjustment_of_id=original.id,occurred_at=source.occurred_at or source.created_at)
        snapshot={'original_allocation_id':original.id,'original_calculation_hash':original.calculation_hash,
            'fee_source_hash':source.payload_hash,'fee_total':str(fee),'policy':policy,'statutory_reporting_enabled':False,
            'effective_date_basis':'PROVIDER_OCCURRED_AT' if source.occurred_at else 'OBSERVED_FEE_ADJUSTMENT_DATE'}
        row=MarketplaceAllocation(id=str(uuid4()),idempotency_key=digest({'first_fee':original.id}),
            created_at=stored_instant(utcnow()),calculation_snapshot=snapshot,calculation_hash=digest(snapshot),**values)
        db.add(row);db.flush();return row