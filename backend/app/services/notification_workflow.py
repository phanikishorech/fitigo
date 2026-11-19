"""Transactional inbox/outbox. No network calls in business transactions.

An uncertain send becomes UNKNOWN, never an automatic second message. Provider
acceptance is not delivery. Existing OTP/reset/invitation transports stay separate.
"""
from datetime import datetime, timedelta
import hashlib
import json
from uuid import uuid4
from fastapi import HTTPException
from sqlalchemy import select, func, or_, and_
from app.core.config import settings
from app.core.time import as_ist
from app.models.auth import User
from app.models.notification import NotificationEvent
from app.models.notification_delivery import NotificationDelivery, NotificationPreference
from app.services import account_delivery

TEMPLATES = {
    'BOOKING_CANCELLED': ('OPERATIONAL','Booking cancelled','Your booking was cancelled. Open its details to review any eligible FitiGo Wallet credit. No original-method refund is initiated.'),
    'MEMBERSHIP_TRANSFERRED': ('SECURITY','Membership transferred','Your one-time membership transfer is complete. You no longer have access through this membership.'),
    'MEMBERSHIP_RECEIVED': ('OPERATIONAL','Membership received','A Multi-Gym membership was transferred to you. Original validity and usage rules remain unchanged; it cannot be transferred again.'),
    'BOOKING_RESCHEDULED': ('OPERATIONAL','Booking rescheduled','Your direct booking was rescheduled. Review its updated details in FitiGo.'),
    'GYM_STATUS_CHANGED': ('OPERATIONAL','Gym review updated','Your gym review status changed. Sign in to review the current status.'),
    'STAFF_REMOVED': ('OPERATIONAL','Gym assignment removed','A gym staff assignment was removed. Sign in to review your current access.'),
    'PROFILE_UPDATED': ('SECURITY','Profile updated','Your account profile was updated. If this was not you, contact your administrator.'),
    'PASSWORD_CHANGED': ('SECURITY','Password changed','Your password was changed. Previous sessions have been revoked.'),
    'PASSWORD_RESET': ('SECURITY','Password reset','Your password was reset. Previous sessions have been revoked.'),
}


def stamp(): return datetime.utcnow().replace(microsecond=0)


def email_hash(address): return hashlib.sha256(address.strip().lower().encode()).hexdigest()


def require_enabled():
    if not settings.notification_workflows_enabled:
        raise HTTPException(409,'Notification preferences and read tracking require the notification migration and deployment switch.')


def publish(db, user_id, kind, resource_id):
    if not settings.notification_workflows_enabled: return
    if kind not in TEMPLATES or type(resource_id) is not int or resource_id<=0: raise ValueError('Unsupported notification')
    user=db.get(User,user_id)
    if not user: return
    category,_,_=TEMPLATES[kind]
    preference=db.get(NotificationPreference,user_id)
    opted=category=='SECURITY' or bool(preference and preference.operational_email)
    eligible=user.status=='ACTIVE' and user.is_email_verified and opted and settings.notification_email_enabled
    event=NotificationEvent(user_id=user_id,event_type=kind,status='RECORDED',payload_json=json.dumps({'resource_id':resource_id}))
    db.add(event);db.flush()
    db.add(NotificationDelivery(event_id=event.id,user_id=user_id,kind=kind,category=category,resource_id=resource_id,
        email_status='QUEUED' if eligible else 'NOT_REQUESTED',recipient_hash=email_hash(user.email) if eligible else None,
        next_attempt_at=stamp(),created_at=stamp()))


def preferences(db,user):
    enabled=settings.notification_workflows_enabled
    row=db.get(NotificationPreference,user.id) if enabled else None
    return {'enabled':enabled,'operational_email':bool(row and row.operational_email),
        'email_available':bool(enabled and settings.notification_email_enabled and account_delivery.email_ready() and user.is_email_verified),
        'security_messages_optional':False,'in_app_enabled':enabled,'sms_available':False,'push_available':False,
        'message':'Optional operational email is opt-in. Security notices cannot be disabled here. Email acceptance is not inbox delivery. Preference changes affect queued, not already dispatched messages.'}


def update_preferences(db,user_id,enabled):
    require_enabled()
    user=db.scalar(select(User).where(User.id==user_id).with_for_update().execution_options(populate_existing=True))
    if not user or user.status!='ACTIVE': raise HTTPException(403,'Account unavailable')
    if enabled and not preferences(db,user)['email_available']:
        raise HTTPException(409,'Operational email requires a verified email and an enabled, configured delivery channel.')
    row=db.get(NotificationPreference,user_id)
    if row is None: row=NotificationPreference(user_id=user_id);db.add(row)
    row.operational_email=enabled;row.updated_at=stamp()
    from app.services.operation_audit import record
    record(db,'NOTIFICATION_PREFERENCE_CHANGED',user_id,user_id,operational_email=enabled)
    db.commit()
    return preferences(db,user)


def inbox(db,user_id,limit,offset,unread):
    if not settings.notification_workflows_enabled:
        return {'enabled':False,'items':[],'total':0,'unread_count':0,'limit':limit,'offset':offset}
    base=select(NotificationDelivery).where(NotificationDelivery.user_id==user_id)
    query=base.where(NotificationDelivery.read_at.is_(None)) if unread else base
    items=[]
    for row in db.scalars(query.order_by(NotificationDelivery.id.desc()).limit(limit).offset(offset)):
        category,title,body=TEMPLATES.get(row.kind,('OPERATIONAL','Account update','Sign in to review your account.'))
        items.append({'id':row.id,'title':title,'body':body,'category':category,'resource_id':row.resource_id,
            'created_at':as_ist(row.created_at),'read_at':as_ist(row.read_at) if row.read_at else None,
            'email_status':row.email_status,'error_code':row.error_code})
    return {'enabled':True,'items':items,'total':db.scalar(select(func.count()).select_from(query.subquery())),
        'unread_count':db.scalar(select(func.count()).select_from(base.where(NotificationDelivery.read_at.is_(None)).subquery())),
        'limit':limit,'offset':offset}


def mark_read(db,user_id,notification_id):
    require_enabled()
    row=db.scalar(select(NotificationDelivery).where(NotificationDelivery.id==notification_id,NotificationDelivery.user_id==user_id)
                  .with_for_update().execution_options(populate_existing=True))
    if not row: raise HTTPException(404,'Notification not found')
    if row.read_at is None: row.read_at=stamp()
    db.commit()
    return {'id':row.id,'read_at':as_ist(row.read_at)}


def due(db,limit):
    require_enabled()
    now=stamp()
    return list(db.scalars(select(NotificationDelivery.id).where(or_(
        and_(NotificationDelivery.email_status.in_(['QUEUED','WAITING']),NotificationDelivery.next_attempt_at<=now),
        and_(NotificationDelivery.email_status=='DISPATCHING',NotificationDelivery.claimed_at<now-timedelta(minutes=5)))
        ).order_by(NotificationDelivery.id).limit(limit)))


def dispatch(session_factory, notification_id):
    require_enabled()
    if not settings.notification_email_enabled: return 'DISABLED'
    claim=uuid4().hex
    with session_factory() as db:
        initial=db.get(NotificationDelivery,notification_id)
        if not initial: return 'NOT_FOUND'
        user=db.scalar(select(User).where(User.id==initial.user_id).with_for_update().execution_options(populate_existing=True))
        row=db.scalar(select(NotificationDelivery).where(NotificationDelivery.id==notification_id).with_for_update().execution_options(populate_existing=True))
        now=stamp()
        if row.email_status=='DISPATCHING':
            if row.claimed_at and row.claimed_at<now-timedelta(minutes=5):
                row.email_status='UNKNOWN';row.error_code='INTERRUPTED_SEND';db.commit()
            return row.email_status
        if row.email_status not in {'QUEUED','WAITING'} or row.next_attempt_at>now: return row.email_status
        preference=db.scalar(select(NotificationPreference).where(NotificationPreference.user_id==row.user_id)
                             .with_for_update().execution_options(populate_existing=True))
        eligible=(user and user.status=='ACTIVE' and user.is_email_verified and row.recipient_hash==email_hash(user.email)
                  and (row.category=='SECURITY' or bool(preference and preference.operational_email)))
        if not eligible:
            row.email_status='SUPPRESSED';row.error_code='RECIPIENT_OR_PREFERENCE_CHANGED';db.commit();return row.email_status
        if not account_delivery.email_ready():
            row.attempts+=1;row.error_code='CHANNEL_UNAVAILABLE'
            row.email_status='WAITING' if row.attempts<5 else 'FAILED'
            row.next_attempt_at=now+timedelta(seconds=min(3600,60*2**row.attempts))
            db.commit();return row.email_status
        if row.kind not in TEMPLATES:
            row.email_status='FAILED';row.error_code='UNSUPPORTED_TEMPLATE';db.commit();return row.email_status
        _,title,body=TEMPLATES[row.kind]
        address=user.email
        row.email_status='DISPATCHING';row.claim_id=claim;row.claimed_at=now;row.attempts+=1;row.error_code=None
        db.commit()  # Claim is durable before external I/O; another worker cannot resend.
    try:
        account_delivery.send_email(address,'FitiGo: '+title,body+'\n\nOpen FitiGo directly to review your account.')
        result,error='ACCEPTED',None
    except Exception:
        result,error='UNKNOWN','PROVIDER_ACCEPTANCE_UNCERTAIN'  # never expose transport diagnostics
    with session_factory() as db:
        row=db.scalar(select(NotificationDelivery).where(NotificationDelivery.id==notification_id).with_for_update().execution_options(populate_existing=True))
        if row.claim_id==claim and row.email_status in {'DISPATCHING','UNKNOWN'}:
            row.email_status=result;row.error_code=error
            if result=='ACCEPTED': row.accepted_at=stamp()
            db.commit()
        return row.email_status