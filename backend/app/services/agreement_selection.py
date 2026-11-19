"""Dormant source-backed selection/pinning API for future backend workers.

No HTTP mutation endpoint and no hooks into purchase/access/payment flows in Phase 2.
Never accepts a browser environment, arbitrary timestamp or historical owner ID.
"""
import hashlib
import json
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import inspect, select
from app.core.time import as_ist, stored_instant
from app.models.financial_agreement import FinancialAgreementPin, FinancialAgreementScope, FinancialAgreementVersion
from app.models.payment_checkout import PaymentCheckout
from app.models.booking import Booking
from app.models.membership import UserMembership
from app.models.access import Checkin, AccessQrToken, CustomerDailyAccess
from app.models.customer_policy import MembershipTransfer
from app.schemas.accounting_policy import AccountingPolicy, ALLOWED_INSTANTS
from app.services.financial_agreements import resolve


def fail(code, reason):
    raise HTTPException(409, detail={'code': code, 'message': reason})


def pin_commercial_evidence(db, evidence, *, context, source_key):
    """Reuse immutable pins for the commercial source boundary, not statutory policy."""
    from app.services.marketplace_calculation import block
    from app.services.marketplace_allocations import verified_payload, digest
    data = verified_payload(evidence)
    binding = data.get('financial_configuration') or {}
    if binding.get('status') != 'PINNED': block('GYM_CONFIGURATION_MISSING', 'Original source has no applicable gym configuration.')
    checkout = db.scalar(select(PaymentCheckout).where(PaymentCheckout.id == evidence.checkout_id).with_for_update())
    row = db.get(FinancialAgreementVersion, binding.get('agreement_version_id'))
    parent = db.get(FinancialAgreementScope, row.scope_id) if row else None
    if not checkout or not parent or parent.gym_id != data.get('gym_id') or binding.get('gym_id')!=parent.gym_id or binding.get('mode')!=evidence.mode or parent.mode != evidence.mode or checkout.mode != evidence.mode:
        block('ENVIRONMENT_MISMATCH', 'Pinned gym/environment identity mismatch.')
    if binding.get('terms_hash') != digest(row.terms) or binding.get('agreement_version') != row.version:
        block('RECONCILIATION_REQUIRED', 'Original configuration integrity mismatch.')
    from datetime import datetime
    try: instant = datetime.fromisoformat(binding['selected_at'])
    except (KeyError, ValueError, TypeError): block('SOURCE_DATA_MISSING', 'Original selection instant missing.')
    expected = evidence.occurred_at
    if context != 'MULTI_GYM_VISIT' and expected != checkout.created_at:
        block('SOURCE_DATA_MISMATCH', 'Purchase snapshot does not match checkout creation.')
    if instant != expected or instant < row.effective_from or (row.effective_to and instant >= row.effective_to):
        block('POLICY_SOURCE_CONFLICT', 'Configuration selection does not match the original source boundary.')
    previous = db.scalar(select(FinancialAgreementPin).where(FinancialAgreementPin.checkout_id == checkout.id,
        FinancialAgreementPin.context == context, FinancialAgreementPin.source_key == source_key).with_for_update())
    if previous:
        if previous.agreement_version_id != row.id or digest(previous.evidence) != previous.evidence_hash:
            block('RECONCILIATION_REQUIRED', 'Existing immutable pin conflicts with source.')
        return previous
    details = {'source_evidence_id': evidence.id, 'source_payload_hash': evidence.payload_hash,
        'financial_configuration': binding, 'settings': row.terms['financial_settings'],
        'selection_instant': 'CHECKIN' if context == 'MULTI_GYM_VISIT' else 'CHECKOUT_CREATED'}
    pin = FinancialAgreementPin(checkout_id=checkout.id, mode=checkout.mode, context=context, source_key=source_key,
        agreement_version_id=row.id, selection_policy_version_id=row.id, selected_at=instant,
        evidence=details, evidence_hash=digest(details))
    db.add(pin); db.flush(); return pin


def select_for_source(db, *, checkout_id, context, selection_policy_version_id, booking_id=None, checkin_id=None, lock=False):
    if context not in ALLOWED_INSTANTS: fail('UNSUPPORTED', 'Unknown selection context.')
    if context not in {'BOOKING_PURCHASE', 'BOOKING_ATTENDANCE', 'NO_SHOW'} and booking_id is not None:
        fail('RECONCILIATION_REQUIRED', 'Membership context cannot select a booking.')
    checkout = db.get(PaymentCheckout, checkout_id)
    if not checkout or checkout.mode not in {'test', 'live'}: fail('SOURCE_DATA_MISSING', 'Trusted checkout/environment missing.')
    policy_query = select(FinancialAgreementVersion).where(FinancialAgreementVersion.id == selection_policy_version_id)
    policy_row = db.scalar(policy_query.with_for_update().execution_options(populate_existing=True) if lock else policy_query)
    if not policy_row or policy_row.action != 'AGREEMENT': fail('POLICY_MISSING', 'Explicit selection policy version required.')
    policy_scope = db.get(FinancialAgreementScope, policy_row.scope_id)
    if policy_scope.mode != checkout.mode: fail('RECONCILIATION_REQUIRED', 'Cross-environment policy rejected.')
    raw = policy_row.terms.get('policy_contract')
    if not raw: fail('POLICY_MISSING', 'Legacy agreement has no selection policy.')
    try: policy = AccountingPolicy.model_validate(raw)
    except ValidationError: fail('UNSUPPORTED', 'Invalid or unsupported policy contract.')
    rule = getattr(policy.selection, context)
    if rule.instant is None or rule.approval.status != 'APPROVED': fail('POLICY_MISSING', 'Selection instant is unset or awaiting explicit approval.')
    times = {'CHECKOUT_CREATED': checkout.created_at}
    gym_id = None
    source_key = 'checkout:' + checkout.id
    holder = checkout.user_id
    membership_id = None
    occurred = checkout.created_at
    evidence = {'checkout_id': checkout.id, 'mode': checkout.mode, 'original_purchaser_id': checkout.user_id,
        'gym_owner_id_at_event': None, 'financial_beneficiary_id': None,
        'ownership_status': 'SOURCE_DATA_MISSING',
        'ownership_reason': 'No immutable historical owner/beneficiary snapshot exists; current gym owner is not substituted.'}
    if context != 'BOOKING_ATTENDANCE' and context != 'MULTI_GYM_VISIT' and checkin_id is not None:
        fail('RECONCILIATION_REQUIRED', 'This context does not accept check-in evidence.')
    if context.startswith('BOOKING') or context == 'NO_SHOW':
        booking = db.get(Booking, booking_id) if booking_id else None
        if not booking or booking.checkout_id != checkout.id or booking.user_id != checkout.user_id:
            fail('SOURCE_DATA_MISSING', 'Booking must belong to the checkout and purchaser.')
        if checkout.kind not in {'BOOKING', 'CART'}: fail('RECONCILIATION_REQUIRED', 'Purchase kind mismatch.')
        gym_id = booking.gym_id
        evidence['booking_id'] = booking.id
        source_key = 'booking:' + str(booking.id)
        # Scheduled start is mutable through rescheduling: unsupported until an
        # immutable scheduled-service snapshot exists, even though current slot is known.
        if context == 'NO_SHOW':
            if booking.status != 'CONFIRMED' or booking.attendance_status != 'NO_SHOW' or not booking.attendance_marked_at:
                fail('SOURCE_DATA_MISSING', 'Confirmed no-show evidence missing.')
            if db.scalar(select(Checkin.id).where(Checkin.booking_id == booking.id, Checkin.status == 'SUCCESS').limit(1)):
                fail('RECONCILIATION_REQUIRED', 'No-show conflicts with attendance.')
            times['NO_SHOW_CONFIRMED'] = booking.attendance_marked_at
            occurred = booking.attendance_marked_at
        elif context == 'BOOKING_ATTENDANCE':
            if booking.status != 'CONFIRMED' or booking.attendance_status == 'NO_SHOW': fail('SOURCE_DATA_MISSING', 'Booking not eligible.')
    elif context == 'MEMBERSHIP_PURCHASE':
        if booking_id is not None or checkout.kind not in {'SINGLE_GYM', 'MULTI_GYM'}:
            fail('SOURCE_DATA_MISSING', 'Membership purchase checkout required.')
        # Purchase selection precedes activation. It must not require or create
        # an entitlement, and its identity stays the checkout after fulfillment.
        gym_id = (checkout.snapshot or {}).get('gym_id') if checkout.kind == 'SINGLE_GYM' else None
        if checkout.kind == 'SINGLE_GYM' and (type(gym_id) is not int or gym_id <= 0):
            fail('SOURCE_DATA_MISSING', 'Immutable purchase gym snapshot is missing.')
    else:
        if booking_id is not None: fail('RECONCILIATION_REQUIRED', 'Membership context cannot select a booking.')
        member = db.scalar(select(UserMembership).where(UserMembership.gateway_checkout_id == checkout.id))
        if not member or checkout.kind not in {'SINGLE_GYM', 'MULTI_GYM'}: fail('SOURCE_DATA_MISSING', 'Fulfilled membership required.')
        membership_id, gym_id, holder = member.id, member.gym_id, member.user_id
        if member.user_id != checkout.user_id:
            transfer = db.scalar(select(MembershipTransfer).where(MembershipTransfer.membership_id == member.id,
                MembershipTransfer.original_user_id == checkout.user_id, MembershipTransfer.recipient_user_id == member.user_id,
                MembershipTransfer.status == 'COMPLETED'))
            if not transfer: fail('RECONCILIATION_REQUIRED', 'Membership owner changed without transfer evidence.')
            evidence['transfer_id'] = transfer.id
        times['MEMBERSHIP_ACTIVATED'] = member.start_at
        evidence['membership_id'] = member.id
        source_key = 'membership:' + str(member.id)
        occurred = member.start_at
        if context == 'MULTI_GYM_VISIT' and member.membership_type != 'MULTI_GYM': fail('SOURCE_DATA_MISSING', 'Multi-Gym membership required.')
        if context == 'MEMBERSHIP_RECOGNITION': fail('SOURCE_DATA_MISSING', 'No recognition period source exists in Phase 2.')
    if context in {'BOOKING_ATTENDANCE', 'MULTI_GYM_VISIT'}:
        scan = db.get(Checkin, checkin_id) if checkin_id else None
        if not scan or scan.status != 'SUCCESS': fail('SOURCE_DATA_MISSING', 'Successful backend check-in required.')
        token = db.get(AccessQrToken, scan.qr_token_id)
        if not token or not token.valid_from or not token.expires_at:
            fail('SOURCE_DATA_MISSING', 'Immutable admission window evidence is incomplete; do not backfill from current time.')
        if not token.valid_from <= scan.checkin_time < token.expires_at: fail('RECONCILIATION_REQUIRED', 'Check-in outside evidence window.')
        if context == 'BOOKING_ATTENDANCE':
            if scan.booking_id != booking.id or scan.gym_id != gym_id or scan.user_id != checkout.user_id or token.booking_id != booking.id or scan.access_source != 'BOOKING_ACCESS' or scan.visitor_index is None or not 0 <= scan.visitor_index < booking.quantity or token.visitor_index != scan.visitor_index:
                fail('RECONCILIATION_REQUIRED', 'Booking visitor evidence mismatch.')
            source_key += ':visitor:' + str(scan.visitor_index)
        else:
            daily = db.get(CustomerDailyAccess, scan.daily_access_id) if scan.daily_access_id else None
            if not daily or scan.membership_id != membership_id or daily.membership_id != membership_id or token.daily_access_id != daily.id or daily.user_id != scan.user_id or daily.used_gym_id != scan.gym_id or scan.access_source != 'MEMBERSHIP_ACCESS':
                fail('RECONCILIATION_REQUIRED', 'Membership visit evidence mismatch.')
            gym_id = scan.gym_id
            evidence['holder_at_visit_id'] = scan.user_id
            source_key += ':daily:' + str(daily.id)
        times['CHECKIN'] = scan.checkin_time
        evidence['checkin_id'] = scan.id
        occurred = scan.checkin_time
    if policy_scope.gym_id is not None and policy_scope.gym_id != gym_id: fail('RECONCILIATION_REQUIRED', 'Selection policy belongs to another gym.')
    if not policy_row.effective_from <= occurred or (policy_row.effective_to and occurred >= policy_row.effective_to):
        fail('POLICY_MISSING', 'Selection policy was not effective at the source event.')
    # Explicit pinned governing policy must itself be the effective policy for the
    # context event; do not choose a later policy to reinterpret past transactions.
    governing = resolve(db, checkout.mode, gym_id, as_ist(occurred), lock=lock)
    if not governing or governing.id != policy_row.id: fail('POLICY_MISSING', 'Selection policy is not the effective governing version at source event time.')
    at = times.get(rule.instant)
    if at is None: fail('SOURCE_DATA_MISSING', f'{rule.instant} has no approved immutable source timestamp.')
    selected = resolve(db, checkout.mode, gym_id, as_ist(at), lock=lock)
    if not selected: fail('POLICY_MISSING', 'No effective agreement at the approved source instant.')
    evidence.update(gym_id=gym_id, current_holder_id=holder, context=context,
        selection_instant=rule.instant, selection_approval_reference=rule.approval.reference,
        selected_at=stored_instant(at).isoformat(), source_occurred_at=stored_instant(occurred).isoformat(),
        agreement_version=selected.version, policy_contract_version=2)
    return {'checkout_id': checkout.id, 'mode': checkout.mode, 'context': context, 'source_key': source_key,
        'agreement_version_id': selected.id, 'selection_policy_version_id': policy_row.id,
        'selected_at': stored_instant(at), 'evidence': evidence, 'posting_eligible': False,
        'blockers': ['CALCULATION_NOT_IMPLEMENTED', 'OWNERSHIP_EVIDENCE_MISSING']}


def pin_for_source(db, **source):
    """Caller-owned transaction. Dormant internal function, never called by GET/UI.

    Pins selection evidence, not financial eligibility; owner evidence remains
    explicitly missing. A future financial event must FK this pin and provide the
    separately verified ownership snapshot. No auto-commit, no amount calculation.
    """
    if not inspect(db.connection()).has_table('financial_agreement_pins'):
        fail('SOURCE_DATA_MISSING', 'Apply policy-pin migration before using the internal pin service.')
    checkout = db.scalar(select(PaymentCheckout).where(PaymentCheckout.id == source['checkout_id'])
        .with_for_update().execution_options(populate_existing=True))
    if not checkout: fail('SOURCE_DATA_MISSING', 'Checkout unavailable.')
    # Return a prior pin before re-reading mutable ownership/status. Its immutable
    # evidence is the historical contract; transfer or later policy changes cannot
    # rewrite it. Validate retry identity rather than assuming all context events
    # on a checkout are the same (cart visitors can have distinct pins).
    context = source['context']
    if context not in ALLOWED_INSTANTS: fail('UNSUPPORTED', 'Unknown selection context.')
    if context not in {'BOOKING_ATTENDANCE', 'MULTI_GYM_VISIT'} and source.get('checkin_id') is not None:
        fail('RECONCILIATION_REQUIRED', 'This context does not accept check-in evidence.')
    if context not in {'BOOKING_PURCHASE', 'BOOKING_ATTENDANCE', 'NO_SHOW'} and source.get('booking_id') is not None:
        fail('RECONCILIATION_REQUIRED', 'Membership context cannot select a booking.')
    identity = None
    if context in {'BOOKING_PURCHASE', 'NO_SHOW'} and source.get('booking_id'):
        identity = 'booking:' + str(source['booking_id'])
    elif context in {'BOOKING_ATTENDANCE', 'MULTI_GYM_VISIT'} and source.get('checkin_id'):
        scan = db.get(Checkin, source['checkin_id'])
        if scan:
            identity = f'booking:{scan.booking_id}:visitor:{scan.visitor_index}' if context == 'BOOKING_ATTENDANCE' else f'membership:{scan.membership_id}:daily:{scan.daily_access_id}'
            if context == 'BOOKING_ATTENDANCE' and scan.booking_id != source.get('booking_id'):
                fail('RECONCILIATION_REQUIRED', 'Retry booking and check-in disagree.')
    elif context == 'MEMBERSHIP_PURCHASE':
        identity = 'checkout:' + checkout.id
    else:
        member = db.scalar(select(UserMembership).where(UserMembership.gateway_checkout_id == checkout.id))
        if member: identity = 'membership:' + str(member.id)
    if identity:
        prior = db.scalar(select(FinancialAgreementPin).where(FinancialAgreementPin.checkout_id == checkout.id,
            FinancialAgreementPin.context == context, FinancialAgreementPin.source_key == identity).with_for_update())
        if prior:
            if prior.mode != checkout.mode:
                fail('RECONCILIATION_REQUIRED', 'Pinned environment disagrees with checkout; original pin preserved.')
            if prior.selection_policy_version_id != source['selection_policy_version_id']:
                fail('RECONCILIATION_REQUIRED', 'Retry cannot change the pinned governing policy.')
            return prior
    # Serialize against agreement edits without changing any business source row.
    db.scalar(select(FinancialAgreementScope).where(FinancialAgreementScope.mode == checkout.mode,
        FinancialAgreementScope.scope_key == 'DEFAULT').with_for_update())
    chosen = select_for_source(db, lock=True, **source)
    existing = db.scalar(select(FinancialAgreementPin).where(FinancialAgreementPin.checkout_id == checkout.id,
        FinancialAgreementPin.context == chosen['context'], FinancialAgreementPin.source_key == chosen['source_key']).with_for_update())
    if existing:
        if existing.selection_policy_version_id != chosen['selection_policy_version_id'] or existing.agreement_version_id != chosen['agreement_version_id']:
            fail('RECONCILIATION_REQUIRED', 'A different agreement is already pinned; it cannot be replaced.')
        return existing
    raw = json.dumps(chosen['evidence'], sort_keys=True, separators=(',', ':'))
    pin = FinancialAgreementPin(**{k: chosen[k] for k in ('checkout_id', 'mode', 'context', 'source_key',
        'agreement_version_id', 'selection_policy_version_id', 'selected_at', 'evidence')},
        evidence_hash=hashlib.sha256(raw.encode()).hexdigest())
    db.add(pin); db.flush()
    return pin