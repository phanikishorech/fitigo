"""Explicit audit envelope. Never accept raw request dictionaries or free text."""
from app.core.config import settings
from app.models.operations import OperationAudit

REASONS = {'ADMIN_REQUEST', 'USER_REQUEST', 'SECURITY', 'POLICY_VIOLATION', 'DUPLICATE', 'CORRECTION', 'OTHER', 'AUTOMATED_CLEANUP'}
ACTIONS = {
    'SUPPORT_CREATED': 'SUPPORT', 'SUPPORT_REPLIED': 'SUPPORT', 'SUPPORT_STATUS_CHANGED': 'SUPPORT',
    'NOTIFICATION_PREFERENCE_CHANGED': 'USER',
    'USER_STATUS_CHANGED': 'USER', 'PROFILE_UPDATED': 'USER', 'PASSWORD_CHANGED': 'USER', 'PASSWORD_RESET': 'USER',
    'BOOKING_CANCELLED': 'BOOKING', 'BOOKING_RESCHEDULED': 'BOOKING', 'ATTENDANCE_RECORDED': 'BOOKING',
    'PAYMENT_STATUS_CHANGED': 'BOOKING', 'STAFF_REMOVED': 'GYM', 'STAFF_ASSIGNED': 'GYM',
    'PHOTO_ADDED': 'PHOTO', 'PHOTO_COVER_CHANGED': 'PHOTO', 'PHOTOS_REORDERED': 'GYM',
    'PHOTO_REMOVAL_REQUESTED': 'PHOTO', 'PHOTO_FILE_REMOVED': 'PHOTO',
}
ENUMS = {'from_status', 'to_status'}
VALUES = {'ACTIVE', 'INACTIVE', 'SUSPENDED', 'BANNED', 'CONFIRMED', 'PENDING_PAYMENT', 'CANCELLED', 'EXPIRED',
          'ATTENDED', 'NO_SHOW', 'PAID', 'INITIATED', 'FAILED', 'REFUNDED', 'OPEN', 'WAITING_USER', 'RESOLVED'}
NUMBERS = {'gym_id', 'user_id', 'from_slot_id', 'to_slot_id', 'image_count', 'job_id'}
FLAGS = {'contact_changed', 'operational_email'}
DATES = {'from_date', 'to_date'}


def record(db, action, resource_id, actor_id, *, reason_code='USER_REQUEST', **context):
    if not settings.operational_workflows_enabled:
        return  # Explicit deployment gate; disabled capability is reported to clients.
    if action not in ACTIONS or reason_code not in REASONS:
        raise ValueError('Invalid audit event code')
    safe = {}
    for key, value in context.items():
        valid = ((key in ENUMS and value in VALUES) or (key in NUMBERS and type(value) is int and value > 0)
                 or (key in FLAGS and type(value) is bool))
        if key in DATES:
            from datetime import date
            valid = type(value) is str and len(value) == 10 and date.fromisoformat(value).isoformat() == value
        if not valid: raise ValueError('Unsupported audit context; do not pass personal data or secrets')
        safe[key] = value
    db.add(OperationAudit(actor_id=actor_id, action=action, resource_type=ACTIONS[action], resource_id=resource_id,
                          reason_code=reason_code, context=safe))
    # No commit here: evidence and business mutation succeed or fail together.