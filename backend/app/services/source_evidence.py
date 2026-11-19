"""Atomic source snapshots; callers own commit/rollback and source row locks."""
import hashlib
import json
from datetime import date, datetime
from decimal import Decimal
from uuid import uuid4
from fastapi import HTTPException
from sqlalchemy import inspect, select
from app.core.config import settings
from app.core.time import utcnow, stored_instant, as_ist
from app.models.source_evidence import SourceEvidence, SourceOutbox, GymOwnerEvidence
from app.models.payment_checkout import PaymentCheckout
from app.models.gym import Gym


def enabled(db):
    if not settings.source_evidence_enabled: return False
    if not all(inspect(db.connection()).has_table(t) for t in
               ('financial_source_evidence', 'financial_source_outbox', 'gym_owner_evidence')):
        raise HTTPException(503, 'Source evidence migration f68a92dc1480 is required; mutation not committed.')
    return True


def json_value(value):
    if isinstance(value, datetime): return as_ist(value).isoformat()
    if isinstance(value, (date, Decimal)): return str(value)
    raise TypeError('Unsupported evidence value')


def snapshot(db, event_type, source_type, source_id, *, checkout=None, mode=None,
             occurred_at=None, payload=None, amount=None, currency=None, discriminator='', gym_id=None,
             observe_owner=False):
    if not enabled(db): return None
    if amount is not None and (not isinstance(amount, Decimal) or not amount.is_finite() or amount < 0 or
                              amount > Decimal('9999999999.99') or amount != amount.quantize(Decimal('0.01'))):
        raise HTTPException(409, 'Invalid source evidence money; exact Decimal rupees required.')
    if checkout is not None:
        trusted = db.get(PaymentCheckout, checkout.id)
        if not trusted or trusted.mode not in {'test', 'live'} or (mode is not None and mode != trusted.mode):
            raise HTTPException(409, 'Cross-environment source evidence rejected.')
        mode = trusted.mode
    if mode is not None and mode not in {'test', 'live'}: raise HTTPException(409, 'Invalid source environment.')
    key = hashlib.sha256(f'{mode}:{event_type}:{source_type}:{source_id}:{discriminator}'.encode()).hexdigest()
    prior = db.scalar(select(SourceEvidence).where(SourceEvidence.idempotency_key == key).with_for_update())
    if prior:
        if prior.checkout_id != (checkout.id if checkout else None) or prior.amount != amount or prior.currency != currency:
            raise HTTPException(409, 'Source evidence identity conflicts with previous immutable evidence.')
        return prior
    now = stored_instant(utcnow())
    data = dict(payload or {})
    contexts = {'BOOKING_PURCHASE_RECORDED':['BOOKING_PURCHASE'], 'MEMBERSHIP_PURCHASE_RECORDED':['MEMBERSHIP_PURCHASE'],
        'BOOKING_VISITOR_ATTENDED':['BOOKING_ATTENDANCE'], 'BOOKING_NO_SHOW_CONFIRMED':['NO_SHOW'],
        'MEMBERSHIP_ACTIVATED':['MEMBERSHIP_ACTIVATION'], 'MULTI_GYM_VISIT_VERIFIED':['MULTI_GYM_VISIT']}
    data.update(agreement_selection_contexts=contexts.get(event_type, []), agreement_binding_status='AWAITING_POLICY_RESOLUTION')
    data.update(evidence_version=1, environment_source='PAYMENT_CHECKOUT' if checkout else
        'LINKED_WALLET_ACCOUNT' if mode else 'UNAVAILABLE', posting_enabled=False)
    owner = None
    if gym_id and observe_owner:
        gym = db.scalar(select(Gym).where(Gym.id == gym_id).with_for_update().execution_options(populate_existing=True))
        if not gym: raise HTTPException(409, 'Source gym unavailable.')
        owner = gym.owner_user_id
    data.update(gym_id=gym_id, owner_id_at_event=owner,
        ownership_basis='LOCKED_SOURCE_MUTATION' if owner else 'UNAVAILABLE',
        financial_beneficiary_id=None, beneficiary_status='AWAITING_POLICY_RESOLUTION')
    normalized = json.loads(json.dumps(data, default=json_value, sort_keys=True))
    encoded = json.dumps(normalized, sort_keys=True, separators=(',', ':'))
    row = SourceEvidence(id=str(uuid4()), idempotency_key=key, event_type=event_type,
        source_type=source_type, source_id=str(source_id), checkout_id=checkout.id if checkout else None,
        mode=mode, evidence_status='ENVIRONMENT_UNAVAILABLE' if mode is None else
        'EVENT_TIME_UNAVAILABLE' if occurred_at is None else 'SOURCE_DATA_MISSING' if
        event_type in {'MULTI_GYM_VISIT_VERIFIED','MEMBERSHIP_ADMITTED'} and not data.get('valid_from') else 'VERIFIED_SOURCE',
        occurred_at=stored_instant(occurred_at) if occurred_at else None, created_at=now,
        amount=amount, currency=currency, payload=normalized, payload_hash=hashlib.sha256(encoded.encode()).hexdigest())
    db.add(row); db.flush()
    if owner:
        db.add(GymOwnerEvidence(id=str(uuid4()), evidence_id=row.id, gym_id=gym_id,
            owner_user_id=owner, observed_at=now, basis='LOCKED_SOURCE_MUTATION'))
    if mode:
        db.add(SourceOutbox(id=str(uuid4()), evidence_id=row.id, idempotency_key=key,
            event_type=event_type, source_id=str(source_id), mode=mode, occurred_at=row.occurred_at,
            created_at=now, status='PENDING', retry_count=0, available_at=now,
            binding_status='AWAITING_POLICY_RESOLUTION'))
    db.flush()
    return row


def source_identity(db, *, checkout_id=None, wallet_transaction_id=None):
    from app.models.wallet import WalletAccount, WalletTransaction
    checkout = db.get(PaymentCheckout, checkout_id) if checkout_id else None
    if checkout_id and not checkout: raise HTTPException(409, 'Source checkout is missing.')
    mode = checkout.mode if checkout else None
    if wallet_transaction_id:
        movement = db.get(WalletTransaction, wallet_transaction_id)
        if not movement: raise HTTPException(409, 'Source wallet movement is missing.')
        account = db.get(WalletAccount, movement.account_id)
        if not account or account.user_id != movement.user_id or (checkout and checkout.user_id != movement.user_id):
            raise HTTPException(409, 'Wallet evidence ownership mismatch.')
        if account and account.payment_mode:
            if mode and account.payment_mode != mode: raise HTTPException(409, 'Cross-environment wallet evidence rejected.')
            mode = account.payment_mode
    return checkout, mode


def checkout_created(db, checkout):
    """New purchase boundary only; never called to backfill a resumed checkout."""
    from app.models.booking import Booking
    from app.models.slot import GymSlot
    from app.models.checkout_funding import BookingFunding
    from app.services.gym_financial_settings import binding_at
    from app.services.checkout_funding import get
    from datetime import datetime, timedelta
    from app.core.time import IST
    recorded = enabled(db)
    funded = get(db, checkout)
    total = funded.total_amount if funded else checkout.amount
    bindings = {}
    if checkout.kind in {'BOOKING','CART'}:
        db.flush()
        for booking in db.scalars(select(Booking).where(Booking.checkout_id==checkout.id).order_by(Booking.gym_id,Booking.id)):
            slot=db.get(GymSlot,booking.gym_slot_id)
            start=datetime.combine(booking.slot_date,slot.start_time,tzinfo=IST) if slot else None
            end=datetime.combine(booking.slot_date,slot.end_time,tzinfo=IST) if slot else None
            if end and end<=start:end+=timedelta(days=1)
            binding = binding_at(db, checkout.mode, booking.gym_id, checkout.created_at)
            bindings[str(booking.id)] = binding
            line = db.get(BookingFunding, booking.id) if funded else None
            # This pricing path multiplies unit price by quantity; there is no
            # discount calculation. Tax is NOT evidenced by today's booking model.
            gross = Decimal(str(booking.unit_price)) * booking.quantity
            discount = Decimal('0.00') if gross == booking.total_price else None
            basis = {'price_amount': gross, 'discount_amount': discount, 'tax_amount': None,
                'purchase_amount': booking.total_price, 'price_representation': 'GROSS_BEFORE_DISCOUNT',
                'currency': booking.currency, 'tax_status': 'SOURCE_NOT_SUPPORTED', 'basis_source': 'BOOKING_PRICE'}
            if not recorded: continue
            snapshot(db,'BOOKING_PURCHASE_RECORDED','BOOKING_CHECKOUT',f'{checkout.id}:{booking.id}',
                checkout=checkout,occurred_at=checkout.created_at,gym_id=booking.gym_id,observe_owner=True,
                payload={'booking_id':booking.id,'original_purchaser_id':checkout.user_id,
                    'financial_configuration':binding, 'transaction_basis':basis, 'transaction_type':'INDIVIDUAL',
                    'purchase_source':'BOOKING', 'mode':checkout.mode,
                    'wallet_amount':line.wallet_amount if line else Decimal('0.00') if not funded else None,
                    'gateway_amount':line.gateway_amount if line else booking.total_price if not funded else None,
                    'scheduled_service_start':start,'scheduled_service_end':end,'service_date':booking.slot_date,
                    'quantity':booking.quantity,'purchase_state':'INITIATED_NOT_CAPTURED'})
    elif checkout.kind in {'SINGLE_GYM','MULTI_GYM'}:
        terms = checkout.snapshot
        gym_id = terms.get('gym_id') if checkout.kind == 'SINGLE_GYM' else None
        binding = binding_at(db, checkout.mode, gym_id, checkout.created_at) if gym_id else {'status':'PIN_AT_ADMISSION'}
        bindings['membership'] = binding
        gross = terms.get('base_price') if checkout.kind == 'MULTI_GYM' else terms.get('final_price')
        discount = terms.get('discount_amount') if checkout.kind == 'MULTI_GYM' else '0.00'
        basis = {'price_amount':gross, 'discount_amount':discount, 'tax_amount':terms.get('tax_amount'),
            'purchase_amount':str(total), 'price_representation':'GROSS_BEFORE_DISCOUNT', 'currency':checkout.currency,
            'tax_status':'EVIDENCED' if terms.get('tax_amount') is not None else 'SOURCE_NOT_SUPPORTED',
            'basis_source':'ACCEPTED_MEMBERSHIP_PRICE_SNAPSHOT'}
        if recorded: snapshot(db,'MEMBERSHIP_PURCHASE_RECORDED','CHECKOUT',checkout.id,checkout=checkout,
            occurred_at=checkout.created_at,gym_id=checkout.snapshot.get('gym_id') if checkout.kind=='SINGLE_GYM' else None,
            observe_owner=True,payload={'original_purchaser_id':checkout.user_id,'membership_type':checkout.kind,
                'financial_configuration':binding, 'transaction_basis':basis, 'transaction_type':checkout.kind,
                'purchase_source':'CHECKOUT', 'plan_id':terms.get('id'), 'mode':checkout.mode,
                'wallet_amount':funded.wallet_amount if funded else Decimal('0.00'), 'gateway_amount':checkout.amount,
                'purchase_state':'INITIATED_NOT_CAPTURED'})
    if bindings:
        checkout.snapshot = {**checkout.snapshot, 'financial_configuration_bindings':bindings}


def booking_identity(db, booking):
    from app.models.booking import Payment
    from app.models.wallet import WalletTransaction
    if booking.checkout_id: return source_identity(db, checkout_id=booking.checkout_id)
    payment = db.scalar(select(Payment).where(Payment.booking_id == booking.id))
    reference = payment.external_ref if payment and payment.provider == 'WALLET' else ''
    if reference and reference.startswith('WALLET_TXN:') and reference[11:].isdigit():
        identifier = int(reference[11:])
        debit = db.get(WalletTransaction, identifier)
        if not debit or debit.user_id != booking.user_id or debit.direction != 'OUT' or debit.currency != booking.currency:
            raise HTTPException(409, 'Booking wallet source mismatch.')
        return source_identity(db, wallet_transaction_id=identifier)
    return None, None


def membership_event(db, member, kind, source, at, *, extra=None, fresh_activation=False):
    if not enabled(db): return
    from app.models.customer_policy import MembershipTransfer
    checkout, mode = source_identity(db, checkout_id=member.gateway_checkout_id, wallet_transaction_id=member.wallet_transaction_id)
    transfer = db.scalar(select(MembershipTransfer).where(MembershipTransfer.membership_id == member.id))
    original = checkout.user_id if checkout else transfer.original_user_id if transfer else member.user_id
    prior = db.scalar(select(SourceEvidence).where(SourceEvidence.event_type == 'MEMBERSHIP_ACTIVATED',
        SourceEvidence.source_id == str(member.id)).limit(1))
    snapshot(db, kind, 'MEMBERSHIP' if fresh_activation else kind, source, checkout=checkout, mode=mode,
        occurred_at=at, gym_id=member.gym_id, observe_owner=fresh_activation,
        payload={'membership_id':member.id, 'original_purchaser_id':original, 'holder_id_at_event':member.user_id,
            'transfer_id':transfer.id if transfer else None, 'start_at':member.start_at, 'end_at':member.end_at,
            'original_end_at':member.original_end_at, 'membership_type':member.membership_type,
            'activation_evidence_id':prior.id if prior else None, 'historical_owner_id':prior.payload.get('owner_id_at_event') if prior else None,
            'wallet_transaction_id':member.wallet_transaction_id, **(extra or {})})


def attendance(db, checkin, token, *, booking=None, membership=None, daily=None):
    if not enabled(db): return
    db.flush()
    db.refresh(checkin, ['checkin_time'])  # Pin the persisted timestamp precision.
    checkout, mode = booking_identity(db, booking) if booking else source_identity(db,
        checkout_id=membership.gateway_checkout_id, wallet_transaction_id=membership.wallet_transaction_id)
    from app.models.customer_policy import MembershipTransfer
    transfer = db.scalar(select(MembershipTransfer).where(MembershipTransfer.membership_id == membership.id)) if membership else None
    binding = None
    if membership and membership.membership_type == 'MULTI_GYM' and checkout:
        from app.services.gym_financial_settings import binding_at
        binding = binding_at(db, mode, checkin.gym_id, checkin.checkin_time)
    snapshot(db, 'BOOKING_VISITOR_ATTENDED' if booking else 'MULTI_GYM_VISIT_VERIFIED' if membership.membership_type=='MULTI_GYM' else 'MEMBERSHIP_ADMITTED',
        'CHECKIN', checkin.id, checkout=checkout, mode=mode, occurred_at=checkin.checkin_time,
        gym_id=checkin.gym_id, observe_owner=True,
        payload={'checkin_id':checkin.id, 'qr_token_id':token.id, 'valid_from':token.valid_from,
            **({'financial_configuration':binding} if binding is not None else {}),
            'expires_at':token.expires_at, 'admission_status':checkin.status, 'scanned_by':checkin.scanned_by,
            'customer_id':checkin.user_id, 'visitor_index':checkin.visitor_index, 'visitor_name':checkin.visitor_name,
            'booking_id':booking.id if booking else None, 'membership_id':membership.id if membership else None,
            'original_purchaser_id':checkout.user_id if checkout else transfer.original_user_id if transfer else checkin.user_id,
            'holder_id_at_event':checkin.user_id, 'transfer_id':transfer.id if transfer else None,
            'daily_access_id':daily.id if daily else None, 'access_consumption_status':daily.status if daily else token.status,
            'service_date':booking.slot_date if booking else daily.access_date})


def no_show(db, booking, actor_id):
    if not enabled(db): return
    from app.services.booking_access_service import BookingAccessService
    from app.models.access import Checkin
    start, end = BookingAccessService(db).window(booking)
    if as_ist(booking.attendance_marked_at) < end or db.scalar(select(Checkin.id).where(
        Checkin.booking_id == booking.id, Checkin.status == 'SUCCESS').limit(1)):
        raise HTTPException(409, 'No-show evidence requires closed admission window and no successful admissions.')
    checkout, mode = booking_identity(db, booking)
    snapshot(db, 'BOOKING_NO_SHOW_CONFIRMED', 'BOOKING', booking.id, checkout=checkout, mode=mode,
        occurred_at=booking.attendance_marked_at, gym_id=booking.gym_id, observe_owner=True,
        payload={'booking_id':booking.id, 'actor_id':actor_id, 'scope':'WHOLE_BOOKING',
            'visitor_indices':list(range(booking.quantity)), 'admission_start':start, 'admission_end':end,
            'confirmation_status':'AUTHORIZED_CLOSED_WINDOW', 'service_date':booking.slot_date})


def invalidated_multi_gym_visit(db, checkin_id, actor_id, reason):
    """Record an authorized invalidation already performed by the source workflow.

    Does not change admission/access, does not adjust money, and never runs on GET.
    A separate explicit finalize_month correction consumes this immutable evidence.
    """
    from app.services.owner_payouts import authorize
    from app.models.access import Checkin
    from app.models.membership import UserMembership
    authorize(db,actor_id)
    if not enabled(db): raise HTTPException(409,'Source evidence processing is disabled.')
    if not isinstance(reason,str) or not 3<=len(reason.strip())<=500:
        raise HTTPException(422,'An explicit invalidation reason is required.')
    scan=db.get(Checkin,checkin_id)
    member=db.get(UserMembership,scan.membership_id) if scan and scan.membership_id else None
    if not scan or scan.status!='REJECTED' or not member or member.membership_type!='MULTI_GYM':
        raise HTTPException(409,'A source-invalidated Multi-Gym admission is required.')
    checkout=db.get(PaymentCheckout,member.gateway_checkout_id) if member.gateway_checkout_id else None
    original=db.scalar(select(SourceEvidence).where(SourceEvidence.event_type=='MULTI_GYM_VISIT_VERIFIED',
        SourceEvidence.source_id==str(scan.id)))
    if not checkout or not original or original.checkout_id!=checkout.id:
        raise HTTPException(409,'Original immutable admission and checkout evidence required.')
    return snapshot(db,'MULTI_GYM_VISIT_INVALIDATED','CHECKIN_INVALIDATION',scan.id,
        checkout=checkout,occurred_at=utcnow(),gym_id=scan.gym_id,
        payload={'checkin_id':scan.id,'actor_id':actor_id,'reason':reason.strip(),
            'original_evidence_id':original.id,'original_payload_hash':original.payload_hash})


def cancellation(db, booking, record):
    if not enabled(db): return
    checkout, mode = source_identity(db, checkout_id=booking.checkout_id, wallet_transaction_id=record.wallet_transaction_id)
    snapshot(db, 'BOOKING_CANCELLED', 'BOOKING_CANCELLATION', record.id, checkout=checkout, mode=mode,
        occurred_at=record.created_at, gym_id=booking.gym_id, observe_owner=True,
        amount=record.amount, currency=record.currency,
        payload={'booking_id':booking.id, 'cancellation_id':record.id, 'payment_id':record.payment_id,
            'wallet_credit_transaction_id':record.wallet_transaction_id, 'actor_id':record.actor_id,
            'scheduled_start':record.scheduled_start, 'deadline':record.deadline,
            'credit_status':'CREDITED' if record.wallet_transaction_id else 'NO_CREDIT', 'not_provider_refund':True})
    if record.wallet_transaction_id:
        snapshot(db, 'WALLET_CREDIT_CONFIRMED', 'WALLET_TRANSACTION', record.wallet_transaction_id,
            checkout=checkout, mode=mode, occurred_at=record.created_at, amount=record.amount, currency=record.currency,
            payload={'booking_id':booking.id, 'cancellation_id':record.id, 'wallet_transaction_id':record.wallet_transaction_id,
                'direction':'IN', 'not_provider_refund':True})


def operational_cancellation(db, booking, actor_id):
    """Existing admin override, without manufacturing a refund/wallet credit."""
    if not enabled(db): return
    checkout, mode = booking_identity(db, booking)
    snapshot(db, 'BOOKING_CANCELLED', 'BOOKING_ADMIN_CANCELLATION', booking.id,
        checkout=checkout, mode=mode, occurred_at=booking.cancelled_at,
        payload={'booking_id':booking.id, 'actor_id':actor_id, 'credit_status':'NO_CREDIT',
            'cancellation_basis':'ADMIN_OPERATIONAL_OVERRIDE', 'not_provider_refund':True},
        gym_id=booking.gym_id, observe_owner=True)