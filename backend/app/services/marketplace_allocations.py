"""Source-derived commercial allocation adapter. No calls from analytics GETs.

Trusted internal entry point: accepts an outbox ID only. Callers own commit; no
provider calls, customer mutations, historical backfill or real payout initiation.
"""
import hashlib
import json
from datetime import datetime
from decimal import Decimal
from uuid import uuid4
from sqlalchemy import select
from app.core.config import settings
from app.core.time import as_ist, stored_instant, utcnow
from app.models.auth import User
from app.models.gym import Gym
from app.models.booking import Booking
from app.models.membership import UserMembership
from app.models.payment_checkout import PaymentCheckout, PaymentAttempt
from app.models.checkout_funding import CheckoutFunding, BookingFunding
from app.models.wallet import WalletTransaction
from app.models.access import Checkin, AccessQrToken
from app.models.customer_policy import BookingCancellation
from app.models.source_evidence import SourceEvidence, SourceOutbox, GymOwnerEvidence
from app.models.marketplace_allocation import MarketplaceAllocation
from app.services.marketplace_calculation import calculate, policy_from_terms, configured_shares, equal_units, distribute_fee, split_actual_fee, block
from app.services.financial_agreements import resolve, scope
from app.services.agreement_selection import pin_for_source
from app.schemas.marketplace_allocation import AllocationInput


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def verified_payload(row):
    if digest(row.payload) != row.payload_hash: block('RECONCILIATION_REQUIRED', 'Source evidence integrity mismatch.')
    return row.payload


def funding_for(db, checkout, booking=None):
    """Existing funding records remain authoritative, including wallet debit."""
    if checkout.status != 'PAID' or checkout.currency != 'INR': block('SOURCE_NOT_ELIGIBLE', 'Purchase is not successfully paid.')
    funded = db.get(CheckoutFunding, checkout.id)
    wallet = Decimal('0.00')
    gateway = checkout.amount
    total = checkout.amount
    if funded:
        if funded.mode != checkout.mode or funded.user_id != checkout.user_id or funded.currency != checkout.currency:
            block('ENVIRONMENT_MISMATCH', 'Funding source identity mismatch.')
        if funded.gateway_amount != checkout.amount or funded.total_amount != funded.wallet_amount + funded.gateway_amount:
            block('RECONCILIATION_REQUIRED', 'Funding components do not reconcile.')
        wallet, gateway, total = funded.wallet_amount, funded.gateway_amount, funded.total_amount
        if wallet:
            debit = db.get(WalletTransaction, funded.wallet_transaction_id)
            if funded.state != 'DEBITED' or not debit or debit.checkout_id != checkout.id or debit.user_id != checkout.user_id or debit.direction != 'OUT' or debit.amount != wallet or debit.currency != 'INR':
                block('SOURCE_DATA_MISSING', 'Verified wallet debit is required.')
    if gateway:
        attempts = list(db.scalars(select(PaymentAttempt).where(PaymentAttempt.checkout_id == checkout.id).with_for_update().execution_options(populate_existing=True)))
        collected = [a for a in attempts if a.status in {'SUCCESS','REFUNDED','PARTIALLY_REFUNDED'}]
        if len(collected) != 1 or collected[0].external_id != checkout.gateway_payment_id or collected[0].amount != gateway or collected[0].currency != 'INR' or collected[0].refunded_amount:
            block('RECONCILIATION_REQUIRED', 'Gateway collection is refunded, ambiguous or mismatched.')
    if booking:
        if funded:
            line = db.get(BookingFunding, booking.id)
            lines = list(db.scalars(select(BookingFunding).where(BookingFunding.checkout_id == checkout.id)))
            if not line or line.checkout_id != checkout.id or sum((r.total_amount for r in lines), Decimal(0)) != total or sum((r.gateway_amount for r in lines), Decimal(0)) != gateway or sum((r.wallet_amount for r in lines), Decimal(0)) != wallet:
                block('RECONCILIATION_REQUIRED', 'Booking funding lines do not reconcile.')
            wallet, gateway, total = line.wallet_amount, line.gateway_amount, line.total_amount
        elif checkout.kind == 'BOOKING':
            pass
        else:
            # Legacy multi-gym cart amount attribution cannot be guessed.
            block('SOURCE_DATA_MISSING', 'Cart requires explicit per-booking funding.')
        if total != booking.total_price: block('RECONCILIATION_REQUIRED', 'Booking price and funding disagree.')
    return wallet, gateway, total


def fee_for_checkout(db, checkout):
    rows = list(db.scalars(select(SourceEvidence).where(SourceEvidence.checkout_id == checkout.id,
        SourceEvidence.event_type.in_(['PAYMENT_CAPTURED','PAYMENT_DETAILS_VERIFIED'])).order_by(SourceEvidence.created_at, SourceEvidence.id).with_for_update()))
    candidates = {}
    for row in rows:
        data = verified_payload(row)
        if row.mode != checkout.mode: block('ENVIRONMENT_MISMATCH', 'Provider fee evidence is cross-environment.')
        if data.get('provider_payment_id') != checkout.gateway_payment_id: continue
        value = data.get('fee_amount')
        if value is None: continue
        if data.get('verification_status') != 'VERIFIED' or data.get('verification_source') != 'AUTHENTICATED_PROVIDER_FETCH': continue
        if data.get('fee_basis')=='INCLUDING_TAX' and data.get('fee_tax_amount') is not None and Decimal(data['fee_tax_amount'])>Decimal(value):
            block('RECONCILIATION_REQUIRED','Included fee tax exceeds actual total provider fee.')
        fee = Decimal(value)
        basis = data.get('fee_basis')
        if basis == 'EXCLUDING_TAX':
            if data.get('fee_tax_amount') is None: continue
            fee += Decimal(data['fee_tax_amount'])
        elif basis != 'INCLUDING_TAX': continue
        from app.services.marketplace_calculation import exact_amount
        exact_amount(fee)
        candidates[fee] = row.id
    if len(candidates) > 1: block('RECONCILIATION_REQUIRED', 'Provider fee observations disagree; explicit correction required.')
    return next(iter(candidates.items())) if candidates else (None, None)


def source_basis(db, checkout, source_type, source_id, total, policy):
    """No synthetic zero discounts/taxes. Producers must preserve explicit facts.

    Current Phase 3 evidence may not contain this payload: that is a deliberate
    source-data block, not permission for an Admin request to supply made-up money.
    """
    event_type = 'BOOKING_PURCHASE_RECORDED' if source_type == 'BOOKING' else 'MEMBERSHIP_PURCHASE_RECORDED'
    rows = list(db.scalars(select(SourceEvidence).where(SourceEvidence.checkout_id == checkout.id,
        SourceEvidence.event_type == event_type)))
    matching = []
    for row in rows:
        data = verified_payload(row)
        if row.mode != checkout.mode: block('ENVIRONMENT_MISMATCH', 'Price evidence environment mismatch.')
        if source_type == 'BOOKING' and data.get('booking_id') != source_id: continue
        basis = data.get('transaction_basis')
        if basis is not None: matching.append((row, basis))
    if len(matching) != 1: block('SOURCE_DATA_MISSING', 'One immutable purchase discount/tax basis is required.')
    row, basis = matching[0]
    from app.services.financial_readiness import tax_readiness
    readiness = tax_readiness(row)
    if readiness['blockers']:
        block('SOURCE_DATA_MISSING','Purchase basis is not ready: '+', '.join(readiness['blockers']))
    if basis.get('price_representation') != policy.price_representation or basis.get('currency') != 'INR':
        block('POLICY_SOURCE_CONFLICT', 'Source price representation disagrees with agreement.')
    try:
        from app.schemas.accounting_policy import Money
        from pydantic import TypeAdapter
        money = TypeAdapter(Money)
        values = {key: money.validate_python(basis[key]) for key in ('price_amount','discount_amount','tax_amount')}
    except (KeyError, ValueError, TypeError): block('SOURCE_DATA_MISSING', 'Explicit Decimal discount/tax facts are required.')
    paid = values['price_amount'] - (values['discount_amount'] if policy.price_representation == 'GROSS_BEFORE_DISCOUNT' else 0)
    if paid != total: block('RECONCILIATION_REQUIRED', 'Immutable purchase basis differs from funded amount.')
    return row.id, values


def allocate_event(db, event_id):
    # A caller catching a blocked event must not accidentally commit a new pin or
    # some of a group's allocations. Source locks/outer transaction remain theirs.
    with db.begin_nested():
        return _allocate_event(db, event_id)


def _allocate_event(db, event_id):
    if not settings.marketplace_allocations_enabled: block('PROCESSING_DISABLED', 'Marketplace allocation processing is not enabled.')
    event = db.get(SourceOutbox, event_id)
    if not event: block('SOURCE_DATA_MISSING', 'Outbox event not found.')
    if event.mode == 'live' and not settings.marketplace_live_allocations_enabled:
        block('LIVE_PROCESSING_DISABLED', 'Live allocation requires separate deployment approval.')
    source = db.get(SourceEvidence, event.evidence_id)
    if not source or source.mode != event.mode or source.event_type != event.event_type or source.source_id != event.source_id or source.occurred_at != event.occurred_at:
        block('ENVIRONMENT_MISMATCH', 'Outbox/source identity mismatch.')
    data = verified_payload(source)
    checkout = db.get(PaymentCheckout, source.checkout_id) if source.checkout_id else None
    if not checkout or checkout.mode != event.mode: block('SOURCE_DATA_MISSING', 'Trusted purchase checkout is required.')
    category = {'BOOKING_VISITOR_ATTENDED':'ATTENDED_BOOKING', 'BOOKING_NO_SHOW_CONFIRMED':'NO_SHOW',
                'MEMBERSHIP_ACTIVATED':'SINGLE_GYM'}.get(event.event_type)
    if category is None: block('UNSUPPORTED_EVENT', 'This source event has no percentage allocation adapter.')
    gym_id = data.get('gym_id')
    # Same order as cancellation/scanner; no paid entitlement may race cancellation.
    db.scalar(select(User).where(User.id == checkout.user_id).with_for_update())
    db.scalar(select(Gym).where(Gym.id == gym_id).with_for_update())
    booking = member = None
    if category != 'SINGLE_GYM':
        booking = db.scalar(select(Booking).where(Booking.id == data.get('booking_id')).with_for_update().execution_options(populate_existing=True))
        if not booking or booking.checkout_id != checkout.id or booking.gym_id != gym_id:
            block('SOURCE_DATA_MISMATCH', 'Booking and source event disagree.')
        if booking.user_id!=checkout.user_id or booking.currency!=checkout.currency:
            block('SOURCE_DATA_MISMATCH','Booking purchaser/currency differs from checkout.')
    else:
        member = db.scalar(select(UserMembership).where(UserMembership.id == data.get('membership_id')).with_for_update().execution_options(populate_existing=True))
        if not member or member.gateway_checkout_id != checkout.id or member.membership_type != 'SINGLE_GYM' or member.gym_id != gym_id:
            block('SOURCE_DATA_MISMATCH', 'Single-Gym source identity mismatch.')
    checkout = db.scalar(select(PaymentCheckout).where(PaymentCheckout.id == checkout.id).with_for_update().execution_options(populate_existing=True))
    event = db.scalar(select(SourceOutbox).where(SourceOutbox.id == event_id).with_for_update().execution_options(populate_existing=True))
    # One immutable unit per source event; original retries do not recalculate.
    prior = list(db.scalars(select(MarketplaceAllocation).where(MarketplaceAllocation.source_event_id == event.id,
        MarketplaceAllocation.entry_kind == 'ORIGINAL').with_for_update()))
    if prior: return prior
    if source.evidence_status != 'VERIFIED_SOURCE' or not source.occurred_at:
        block('SOURCE_DATA_MISSING', 'Complete source occurrence evidence is required.')
    owner = db.scalar(select(GymOwnerEvidence).where(GymOwnerEvidence.evidence_id == source.id))
    if not owner or owner.gym_id != gym_id or owner.owner_user_id != data.get('owner_id_at_event'):
        block('OWNER_EVIDENCE_MISSING', 'Immutable owner evidence is required; current owner is not a substitute.')
    if booking:
        if booking.status != 'CONFIRMED' or db.scalar(select(BookingCancellation.id).where(BookingCancellation.booking_id == booking.id)):
            block('SOURCE_NOT_ELIGIBLE', 'Cancelled or unconfirmed booking cannot allocate.')
        context = 'BOOKING_ATTENDANCE' if category == 'ATTENDED_BOOKING' else 'NO_SHOW'
        scan = None
        if category == 'ATTENDED_BOOKING':
            scan = db.get(Checkin, data.get('checkin_id'))
            if not scan or scan.status != 'SUCCESS' or scan.booking_id != booking.id or scan.gym_id != gym_id or scan.user_id != booking.user_id or scan.visitor_index != data.get('visitor_index') or scan.checkin_time != source.occurred_at:
                block('SOURCE_DATA_MISMATCH', 'Visitor evidence does not match a successful check-in.')
            if source.source_type!='CHECKIN' or source.source_id!=str(scan.id) or data.get('qr_token_id')!=scan.qr_token_id:
                block('SOURCE_DATA_MISMATCH','Check-in source identity or token reference differs.')
            token=db.get(AccessQrToken,scan.qr_token_id)
            if not token or not token.valid_from or not token.expires_at or not token.valid_from<=scan.checkin_time<token.expires_at or token.booking_id!=booking.id or token.visitor_index!=scan.visitor_index or scan.access_source!='BOOKING_ACCESS':
                block('SOURCE_DATA_MISSING','Successful admission requires its matching immutable QR window and visitor.')
            indices = [scan.visitor_index]
        else:
            if data.get('scope') != 'WHOLE_BOOKING' or booking.attendance_status != 'NO_SHOW' or data.get('confirmation_status') != 'AUTHORIZED_CLOSED_WINDOW':
                block('POLICY_MISSING', 'Only explicitly confirmed whole-booking no-shows are supported.')
            if db.scalar(select(Checkin.id).where(Checkin.booking_id == booking.id, Checkin.status == 'SUCCESS').limit(1)):
                block('PARTIAL_ATTENDANCE_REVIEW', 'Partial-group no-show policy requires approved visitor confirmations.')
            try: closed_at=stored_instant(datetime.fromisoformat(data['admission_end']))
            except (KeyError,TypeError,ValueError): block('SOURCE_DATA_MISSING','Confirmed admission-window end is required.')
            if closed_at > source.occurred_at or booking.attendance_marked_at != source.occurred_at or data.get('visitor_indices') != list(range(booking.quantity)):
                block('SOURCE_DATA_MISMATCH','No-show confirmation is outside the approved closed-window scope.')
            indices = list(range(booking.quantity))
        if any(type(i) is not int or not 0 <= i < booking.quantity for i in indices): block('SOURCE_DATA_MISMATCH', 'Invalid visitor index.')
    else:
        if member.payment_status != 'PAID' or member.status != 'ACTIVE': block('SOURCE_NOT_ELIGIBLE', 'Membership purchase is not active/paid.')
        if member.user_id!=checkout.user_id or member.currency!=checkout.currency or member.start_at!=source.occurred_at or data.get('original_purchaser_id')!=checkout.user_id:
            block('SOURCE_DATA_MISMATCH','Single-Gym activation identity/time differs from purchase.')
        if checkout.kind!='SINGLE_GYM' or checkout.snapshot.get('gym_id')!=gym_id:
            block('SOURCE_DATA_MISMATCH','Purchased Single-Gym identity differs from activation.')
        context, indices, scan = 'MEMBERSHIP_ACTIVATION', [None], None
    scope(db, checkout.mode, None, lock=True)
    purchase_kind = 'BOOKING_PURCHASE_RECORDED' if booking else 'MEMBERSHIP_PURCHASE_RECORDED'
    purchases = list(db.scalars(select(SourceEvidence).where(SourceEvidence.checkout_id == checkout.id,
        SourceEvidence.event_type == purchase_kind)))
    purchases = [r for r in purchases if not booking or verified_payload(r).get('booking_id') == booking.id]
    modern = len(purchases) == 1 and 'financial_configuration' in purchases[0].payload
    if modern:
        from app.services.agreement_selection import pin_commercial_evidence
        pin = pin_commercial_evidence(db, purchases[0], context='BOOKING_PURCHASE' if booking else 'MEMBERSHIP_PURCHASE',
            source_key=f'booking:{booking.id}' if booking else 'checkout:'+checkout.id)
    else:
        # Old evidence is not upgraded into new settings. Existing legacy contracts
        # retain their explicit source-selection rules and immutable pins.
        if 'financial_configuration_bindings' in checkout.snapshot:
            block('SOURCE_DATA_MISSING','New checkout purchase evidence is missing; no legacy fallback is permitted.')
        governing = resolve(db, checkout.mode, gym_id, as_ist(source.occurred_at), lock=True)
        if not governing: block('AGREEMENT_MISSING', 'No effective agreement at source occurrence.')
        if 'financial_settings' in governing.terms:
            block('SOURCE_DATA_MISSING', 'Checkout configuration snapshot missing; historical backfill forbidden.')
        pin = pin_for_source(db, checkout_id=checkout.id, context=context, selection_policy_version_id=governing.id,
            **({'booking_id':booking.id} if booking else {}), **({'checkin_id':scan.id} if scan else {}))
    from app.models.financial_agreement import FinancialAgreementVersion
    agreement = db.get(FinancialAgreementVersion, pin.agreement_version_id)
    policy = policy_from_terms(agreement.terms)
    revenue, fee_sharing = configured_shares(agreement.terms, category)
    prior_checkout_allocations=list(db.scalars(select(MarketplaceAllocation).where(MarketplaceAllocation.checkout_id==checkout.id,
        MarketplaceAllocation.entry_kind=='ORIGINAL').with_for_update()))
    partition_keys=('fee_residual','visitor_residual','price_representation','fee_distribution')
    if any(any(row.calculation_snapshot['policy'][key] != getattr(policy,key) for key in partition_keys) for row in prior_checkout_allocations):
        block('POLICY_SOURCE_CONFLICT','A checkout cannot mix amount/fee partition policies across agreements.')
    wallet, gateway, total = funding_for(db, checkout, booking)
    if member and member.paid_amount != total: block('RECONCILIATION_REQUIRED', 'Membership price and funding disagree.')
    basis_id, basis = source_basis(db, checkout, 'BOOKING' if booking else 'MEMBERSHIP', booking.id if booking else member.id, total, policy)
    fee, fee_id = fee_for_checkout(db, checkout)
    checkout_actual_fee=str(fee) if fee is not None else None
    if fee is not None and any(row.calculation_snapshot.get('fee_evidence_id') is not None and
        row.calculation_snapshot.get('fee_evidence_id')!=fee_id for row in prior_checkout_allocations):
        # Multiple observations of the same fee can have different evidence IDs;
        # compare the preserved original checkout fee, not one visitor's fee.
        if any(row.calculation_snapshot.get('checkout_actual_fee') not in (None,str(fee)) for row in prior_checkout_allocations):
            block('RECONCILIATION_REQUIRED','Actual checkout fee changed after an allocation; explicit adjustment review required.')
    count = booking.quantity if booking else 1
    # Partition all purchased places, not the currently admitted subset.
    tax_units=equal_units(basis['tax_amount'],count,policy.visitor_residual)
    discount_units=equal_units(basis['discount_amount'],count,policy.visitor_residual)
    eligible_units=equal_units(total-basis['tax_amount'],count,policy.visitor_residual)
    paid_units=tuple(eligible_units[i]+tax_units[i] for i in range(count))
    price_units=tuple(paid_units[i]+(discount_units[i] if policy.price_representation=='GROSS_BEFORE_DISCOUNT' else 0) for i in range(count))
    amounts={'price_amount':price_units,'discount_amount':discount_units,'tax_amount':tax_units}
    gateway_units = distribute_fee(gateway, list(paid_units))
    wallet_units = tuple(paid_units[i]-gateway_units[i] for i in range(count))
    line_ids=[booking.id if booking else member.id]
    line_weights=[gateway]
    position=0
    gym_fee=fitigo_fee=None
    if fee is not None and not modern:gym_fee,fitigo_fee=split_actual_fee(fee,policy.fee_residual)
    if booking and checkout.kind == 'CART':
        lines = list(db.scalars(select(BookingFunding).where(BookingFunding.checkout_id == checkout.id).order_by(BookingFunding.booking_id)))
        line_ids=[r.booking_id for r in lines];line_weights=[r.gateway_amount for r in lines]
        position=line_ids.index(booking.id)
        if fee is not None and not modern:
            gym_fee=distribute_fee(gym_fee,[r.gateway_amount for r in lines])[position]
            fitigo_fee=distribute_fee(fitigo_fee,[r.gateway_amount for r in lines])[position]
            fee=gym_fee+fitigo_fee
    if modern and fee is not None:
        fee = distribute_fee(fee, line_weights)[position]
        gym_fee, fitigo_fee = split_actual_fee(fee, policy.fee_residual, fee_sharing.gym_percent)
    gym_fee_units=distribute_fee(gym_fee,list(gateway_units)) if gym_fee is not None and gateway else (equal_units(gym_fee,count,policy.visitor_residual) if gym_fee is not None else [None]*count)
    fitigo_fee_units=distribute_fee(fitigo_fee,list(gateway_units)) if fitigo_fee is not None and gateway else (equal_units(fitigo_fee,count,policy.visitor_residual) if fitigo_fee is not None else [None]*count)
    fee_units=[gym_fee_units[i]+fitigo_fee_units[i] if fee is not None else None for i in range(count)]
    rows = []
    for index in indices:
        i = index if index is not None else 0
        values = AllocationInput(category=category, **{key:parts[i] for key,parts in amounts.items()},
            wallet_amount=wallet_units[i],gateway_amount=gateway_units[i],actual_gateway_fee=fee_units[i],
            fee_basis='INCLUDING_TAX' if fee is not None else 'UNAVAILABLE',fee_evidence_reference=fee_id)
        result = calculate(agreement.terms, values, transaction_fee_partition=(gym_fee_units[i],fitigo_fee_units[i]) if fee is not None else None)
        allocation_key = f'visitor:{i}' if booking else f'membership:{member.id}'
        original_key=hashlib.sha256(f'{checkout.mode}:{"booking:"+str(booking.id)+":"+str(i) if booking else "membership:"+str(member.id)}'.encode()).hexdigest()
        if db.scalar(select(MarketplaceAllocation.id).where(MarketplaceAllocation.original_unit_key==original_key).with_for_update()):
            block('DUPLICATE_SOURCE_UNIT', 'This purchased visitor/membership already has an original allocation.')
        snapshot = {'input':values.model_dump(mode='json'), 'result':result.model_dump(mode='json'),
            'policy':policy.model_dump(mode='json'),'basis_evidence_id':basis_id,'fee_evidence_id':fee_id,
            'commercial_shares':{'revenue':revenue.model_dump(mode='json'),'gateway_fee':fee_sharing.model_dump(mode='json')},
            'configuration_terms':agreement.terms, 'configuration_hash':digest(agreement.terms),
            'source_payload_hash':source.payload_hash,'agreement_pin_id':pin.id,'checkout_actual_fee':checkout_actual_fee,
            'transaction_fee_partition':[str(gym_fee_units[i]),str(fitigo_fee_units[i])] if fee is not None else None,
            'fee_context':{'line_ids':line_ids,'line_weights':[str(v) for v in line_weights],
                'line_index':position,'unit_weights':[str(v) for v in gateway_units],'unit_index':i,
                'wallet_fee_residual':policy.visitor_residual}}
        row = MarketplaceAllocation(id=str(uuid4()),source_event_id=event.id,source_evidence_id=source.id,
            source_type=source.source_type,source_record_id=source.source_id,allocation_key=allocation_key,
            idempotency_key=hashlib.sha256(f'{event.id}:{allocation_key}'.encode()).hexdigest(),
            original_unit_key=original_key,
            checkout_id=checkout.id,transaction_reference=checkout.gateway_payment_id or checkout.id,mode=checkout.mode,
            category=category,gym_id=gym_id,owner_user_id=owner.owner_user_id,owner_evidence_id=owner.id,
            customer_id=checkout.user_id,booking_id=booking.id if booking else None,membership_id=member.id if member else None,
            visitor_index=index,agreement_pin_id=pin.id,agreement_version_id=agreement.id,agreement_version=agreement.version,
            price_amount=values.price_amount,discount_amount=values.discount_amount,tax_amount=values.tax_amount,
            **{key:getattr(result,key) for key in ('eligible_amount','customer_funded_amount','wallet_amount','gateway_amount',
                'gateway_fee','gym_gateway_fee_share','fitigo_gateway_fee_share','gym_gross_share','fitigo_gross_commission',
                'gym_owner_net_entitlement','fitigo_net_commission','fee_status')},currency='INR',
            calculation_status=result.payout_readiness,posting_status='POSTED',entry_kind='ORIGINAL',
            occurred_at=source.occurred_at,created_at=stored_instant(utcnow()),calculation_snapshot=snapshot,calculation_hash=digest(snapshot))
        db.add(row);rows.append(row)
    db.flush()
    return rows