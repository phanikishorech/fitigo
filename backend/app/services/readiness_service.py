"""Read-only local readiness observations, not production certification or probes."""
from sqlalchemy import inspect, select, func
from app.core.config import settings
from app.services import account_delivery
from app.models.operations import PhotoDeletion
from app.models.notification_delivery import NotificationDelivery


def readiness(db):
    checks = []
    def add(code, status, message): checks.append({'code': code, 'status': status, 'message': message})
    try:
        settings.validate_security()
        add('SIGNING_CONFIGURATION', 'PASS', 'Signing configuration passes local validation; no secret values are exposed.')
    except RuntimeError:
        add('SIGNING_CONFIGURATION', 'BLOCKED', 'Signing configuration failed validation.')
    required = {
        'operation_audits': {'id', 'actor_id', 'action', 'context', 'reason_code', 'created_at'},
        'photo_deletions': {'id', 'image_id', 'gym_id', 'storage_root', 'fingerprint', 'status', 'error_code'},
        'notification_preferences': {'user_id', 'operational_email'},
        'notification_deliveries': {'id', 'event_id', 'user_id', 'kind', 'category', 'resource_id', 'email_status', 'attempts', 'claim_id', 'read_at', 'recipient_hash', 'next_attempt_at', 'claimed_at', 'accepted_at', 'error_code', 'created_at'},
        'support_tickets': {'id', 'user_id', 'request_key', 'status', 'version'},
        'support_messages': {'id', 'ticket_id', 'author_id', 'request_key', 'body'},
    }
    inspector = inspect(db.connection())
    tables = set(inspector.get_table_names())
    valid = {}
    for table, columns in required.items():
        valid[table] = table in tables and columns <= {c['name'] for c in inspector.get_columns(table)}
    missing = [name for name, exists in valid.items() if not exists]
    add('WORKFLOW_SCHEMA', 'BLOCKED' if missing else 'PASS',
        'Missing or incomplete workflow tables: ' + ', '.join(missing) if missing else 'Required workflow columns are present. This is not a full schema-drift audit.')
    add('OPERATIONAL_WORKFLOWS', 'PASS' if settings.operational_workflows_enabled else 'DISABLED', 'Operational audit/photo workflow deployment switch.')
    support_ready = settings.operational_workflows_enabled and valid['support_tickets'] and valid['support_messages'] and valid['operation_audits']
    add('SUPPORT_REQUESTS', ('PASS' if support_ready else 'BLOCKED') if settings.support_workflows_enabled else 'DISABLED',
        'Support requires its schema and operational audit; no requests are created by this check.')
    add('NOTIFICATION_INBOX', 'PASS' if settings.notification_workflows_enabled else 'DISABLED', 'In-app notification deployment switch.')
    ready = settings.notification_workflows_enabled and settings.notification_email_enabled and account_delivery.email_ready()
    add('EMAIL_WORKER_CONFIGURATION', 'CONFIGURED_NOT_VERIFIED' if ready else 'DISABLED',
        'Configuration only. No SMTP connection or email was sent; configuration does not prove recipient delivery.')
    add('ACCOUNT_EMAIL_CONFIGURATION', 'CONFIGURED_NOT_VERIFIED' if account_delivery.email_ready() else 'DISABLED', 'OTP/invitation/reset transport configuration only; no message was sent.')
    add('SMS_CONFIGURATION', 'CONFIGURED_NOT_VERIFIED' if account_delivery.sms_ready() else 'DISABLED', 'SMS configuration only; no provider request was made.')
    add('WORKER_SCHEDULING', 'MANUAL_CHECK', 'No scheduler heartbeat exists. Verify the deployed scheduler and last worker run separately.')
    add('MEDIA_PERMISSIONS', 'MANUAL_CHECK', 'Verify media directory ownership, backup and restore externally. This endpoint does not inspect files or ACLs.')
    add('BACKUP_RECOVERY', 'MANUAL_CHECK', 'Perform an approved database and media restore rehearsal. Historical backup records are not proof of current recovery.')
    add('EXTERNAL_ACCEPTANCE', 'MANUAL_CHECK', 'Authorized inbox/handset delivery, provider sandbox and physical scanner acceptance remain separate.')
    counts = {}
    if valid['notification_deliveries']:
        counts['notification_email'] = {}
        allowed = {'NOT_REQUESTED', 'QUEUED', 'WAITING', 'DISPATCHING', 'ACCEPTED', 'UNKNOWN', 'SUPPRESSED', 'FAILED'}
        for state, count in db.execute(select(NotificationDelivery.email_status, func.count()).group_by(NotificationDelivery.email_status)):
            key = state if state in allowed else 'UNRECOGNIZED'
            counts['notification_email'][key] = counts['notification_email'].get(key, 0) + count
    if valid['photo_deletions']:
        counts['photo_cleanup'] = {}
        for state, count in db.execute(select(PhotoDeletion.status, func.count()).group_by(PhotoDeletion.status)):
            key = state if state in {'PENDING', 'COMPLETE', 'BLOCKED'} else 'UNRECOGNIZED'
            counts['photo_cleanup'][key] = counts['photo_cleanup'].get(key, 0) + count
    return {'checks': checks, 'queue_counts': counts, 'production_certified': False,
            'financial_workflows': {'refund_initiation': False, 'gateway_rescheduling': False, 'gateway_wallet_spending': False, 'gateway_offers': False},
            'message': 'Read-only observations. PASS is limited to the named local check, not a release approval.'}