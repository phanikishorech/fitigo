"""One lifetime transfer of the existing MULTI_GYM entitlement, without a purchase."""
from datetime import timedelta
from uuid import uuid4
from fastapi import HTTPException
from jose import jwt, JWTError
from sqlalchemy import select, or_
from app.core.config import settings
from app.core.time import utcnow, as_ist, stored_instant
from app.models.auth import User, Role, UserRole
from app.models.membership import UserMembership, MembershipPause
from app.models.customer_policy import MembershipTransfer
from app.models.access import CustomerDailyAccess, AccessQrToken, AccessPauseDay
from app.services.membership_pause_service import membership_status
from app.services.policy_schema import available


def transfer_record(db, membership_id, lock=False):
    if not available(db): return None
    query = select(MembershipTransfer).where(MembershipTransfer.membership_id == membership_id)
    return db.scalar(query.with_for_update().execution_options(populate_existing=True) if lock else query)


def eligibility(db, membership, viewer_id):
    history = transfer_record(db, membership.id)
    state = membership_status(db, membership)
    reason = None
    if not available(db): reason = 'Transfer is unavailable until the policy migration is deployed.'
    elif membership.user_id != viewer_id: reason = 'You no longer own this membership.'
    elif membership.membership_type != 'MULTI_GYM': reason = 'Single-Gym memberships cannot be transferred.'
    elif history: reason = 'This membership has already been transferred once and cannot be transferred again.'
    elif state != 'ACTIVE': reason = 'Only an active, unpaused, paid and unexpired Multi-Gym membership can be transferred.'
    return {'eligible': reason is None, 'reason': reason, 'cancel_allowed': False,
        'status': 'TRANSFERRED' if history and history.original_user_id == viewer_id else state,
        'history': None if not history else {'reference': history.id, 'status': history.status,
            'direction': 'SENT' if history.original_user_id == viewer_id else 'RECEIVED',
            'transferred_at': as_ist(history.created_at), 'start_at': as_ist(history.start_at), 'end_at': as_ist(history.end_at)},
        'remaining_valid_until': as_ist(membership.end_at)}


def visible(db, membership_id, user_id):
    m = db.get(UserMembership, membership_id)
    history = transfer_record(db, membership_id) if m else None
    if not m or (m.user_id != user_id and (not history or history.original_user_id != user_id)):
        raise HTTPException(404, 'Membership not found')
    return m


def recipient(db, email, original_id, *, lock=False):
    query = select(User).where(User.email == email.lower(), User.is_email_verified.is_(True), User.status == 'ACTIVE')
    if lock: query = query.with_for_update().execution_options(populate_existing=True)
    user = db.scalar(query)
    if not user or not db.scalar(select(UserRole.id).join(Role).where(UserRole.user_id == user.id, Role.name.in_(['CUSTOMER', 'USER']))):
        raise HTTPException(400, 'No eligible customer with that verified email was found.')
    if user.id == original_id: raise HTTPException(400, 'You cannot transfer a membership to yourself.')
    now = stored_instant(utcnow())
    # Follow existing purchase overlap rule, including future and paused active plans.
    overlap = select(UserMembership.id).where(UserMembership.user_id == user.id,
        UserMembership.status == 'ACTIVE', UserMembership.payment_status == 'PAID', UserMembership.end_at > now).limit(1)
    if db.scalar(overlap.with_for_update() if lock else overlap):
        raise HTTPException(409, 'The recipient already has a current or upcoming membership.')
    return user


def preview(db, membership_id, user_id, email):
    m = visible(db, membership_id, user_id)
    policy = eligibility(db, m, user_id)
    if not policy['eligible']: raise HTTPException(409, policy['reason'])
    other = recipient(db, str(email), user_id)
    now = utcnow()
    claims = {'purpose': 'membership-transfer', 'membership_id': m.id, 'owner_id': user_id,
        'recipient_id': other.id, 'recipient_version': other.token_version,
        'email': other.email, 'membership_end': stored_instant(m.end_at).isoformat(),
        'exp': now + timedelta(minutes=5)}
    token = jwt.encode(claims, settings.jwt_secret.get_secret_value(), algorithm=settings.jwt_algorithm)
    # Exact-match lookup only. No phone, address, full account record or global search.
    display = ' '.join(p for p in [other.first_name, (other.last_name[:1] + '.') if other.last_name else None] if p) or 'Verified FitiGo customer'
    return {'recipient_name': display, 'verified_email': other.email, 'confirmation_token': token,
        'valid_until': as_ist(m.end_at), 'expires_in_seconds': 300,
        'message': 'Permanent one-time transfer. You lose access; remaining dates, pause allowance and daily use are preserved.'}


def confirm(db, membership_id, user_id, token, key):
    if not available(db): raise HTTPException(409, 'Transfer is unavailable until the policy migration is deployed.')
    try:
        claims = jwt.decode(token, settings.jwt_secret.get_secret_value(), algorithms=[settings.jwt_algorithm], options={'verify_exp': False})
        # Use the same injectable absolute clock as preview and membership eligibility.
        if type(claims.get('exp')) is not int or utcnow().timestamp() >= claims['exp']:
            raise JWTError('Expired confirmation')
        if claims.get('purpose') != 'membership-transfer' or claims.get('owner_id') != user_id or claims.get('membership_id') != membership_id or type(claims.get('recipient_id')) is not int:
            raise JWTError('Invalid confirmation')
    except JWTError:
        raise HTTPException(400, 'Transfer confirmation expired or is invalid. Look up the recipient again.') from None
    try:
        # Consistent user ordering prevents reciprocal-transfer deadlocks and serializes scans/purchases.
        users = list(db.scalars(select(User).where(User.id.in_([user_id, claims['recipient_id']])).order_by(User.id)
                               .with_for_update().execution_options(populate_existing=True)))
        owner = next((u for u in users if u.id == user_id), None)
        if not owner or owner.status != 'ACTIVE': raise HTTPException(403, 'Account unavailable')
        m = db.scalar(select(UserMembership).where(UserMembership.id == membership_id).with_for_update().execution_options(populate_existing=True))
        if not m: raise HTTPException(404, 'Membership not found')
        history = transfer_record(db, m.id, lock=True)
        if history:
            if history.original_user_id == user_id and history.recipient_user_id == claims['recipient_id'] and history.request_key == key:
                db.rollback()
                return {'status': 'COMPLETED', 'reference': history.id, 'membership_id': m.id}
            raise HTTPException(409, 'This membership has already been transferred once.')
        policy = eligibility(db, m, user_id)
        if not policy['eligible']: raise HTTPException(409, policy['reason'])
        if claims.get('membership_end') != stored_instant(m.end_at).isoformat():
            raise HTTPException(409, 'Membership validity changed. Review the transfer again.')
        other = recipient(db, claims['email'], user_id, lock=True)
        if other.id != claims['recipient_id'] or other.token_version != claims['recipient_version']:
            raise HTTPException(409, 'Recipient account changed. Review the recipient again.')
        if m.checkout_key and db.scalar(select(UserMembership.id).where(UserMembership.user_id == other.id,
            UserMembership.checkout_key == m.checkout_key).limit(1)):
            raise HTTPException(409, 'A purchase-reference conflict requires support review.')
        # Legacy account-scoped pause flags have no membership history to migrate safely.
        if db.scalar(select(AccessPauseDay.id).where(AccessPauseDay.user_id == user_id,
            AccessPauseDay.access_date >= as_ist(utcnow()).date()).limit(1)):
            raise HTTPException(409, 'Legacy account pauses must be resolved before transferring.')
        now = stored_instant(utcnow())
        from app.services.access_service import AccessService
        today = as_ist(utcnow()).date()
        access = AccessService(db)
        consumed = bool(access._used_access(user_id=user_id, access_date=today, lock=True) or access._legacy_visit(user_id=user_id, access_date=today))
        history = MembershipTransfer(id=str(uuid4()), membership_id=m.id, original_user_id=user_id,
            recipient_user_id=other.id, actor_id=user_id, request_key=key, status='COMPLETED',
            consumed_access_date=today if consumed else None,
            start_at=m.start_at, end_at=m.end_at, original_end_at=m.original_end_at or m.end_at, created_at=now)
        db.add(history)
        daily = list(db.scalars(select(CustomerDailyAccess).where(CustomerDailyAccess.membership_id == m.id)
                               .with_for_update().execution_options(populate_existing=True)))
        ids = [d.id for d in daily]
        for qr in db.scalars(select(AccessQrToken).where(AccessQrToken.daily_access_id.in_(ids), AccessQrToken.status == 'ACTIVE').with_for_update()):
            qr.status = 'REVOKED'
        for day in daily:
            if day.status != 'USED': day.status = 'REVOKED'
        if membership_status(db, m, utcnow()) != 'ACTIVE' or utcnow().timestamp() >= claims['exp']:
            raise HTTPException(409, 'Membership eligibility or confirmation expired. No transfer was applied.')
        m.user_id = other.id
        from app.services.notification_workflow import publish
        publish(db, user_id, 'MEMBERSHIP_TRANSFERRED', m.id)
        publish(db, other.id, 'MEMBERSHIP_RECEIVED', m.id)
        db.flush()
        from app.services.source_evidence import membership_event
        membership_event(db, m, 'MEMBERSHIP_TRANSFERRED', history.id, history.created_at,
            extra={'transfer_id':history.id, 'original_holder_id':history.original_user_id,
                'recipient_holder_id':history.recipient_user_id, 'actor_id':history.actor_id})
        db.commit()
        return {'status': 'COMPLETED', 'reference': history.id, 'membership_id': m.id}
    except Exception:
        db.rollback(); raise


def used_membership_day(db, membership_id, day, lock=False):
    if available(db):
        transferred_use = select(MembershipTransfer.id).where(MembershipTransfer.membership_id == membership_id,
            MembershipTransfer.consumed_access_date == day)
        if db.scalar(transferred_use.with_for_update() if lock else transferred_use): return True
    query = select(CustomerDailyAccess.id).where(CustomerDailyAccess.membership_id == membership_id,
        CustomerDailyAccess.access_date == day, CustomerDailyAccess.status == 'USED').limit(1)
    return db.scalar(query.with_for_update() if lock else query) is not None