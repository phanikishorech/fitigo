"""Safe runtime capabilities, not editable deployment configuration."""
from fastapi import APIRouter, Depends, Response
from app.core.dependencies import get_current_user, require_role
from app.core.config import settings
from app.services.payment_providers import configured

router=APIRouter()
from app.routers.support import router as support_router
router.include_router(support_router,prefix='/meta')


def capabilities():
    from app.services.membership_wallet_service import wallet_enabled
    from app.services.account_delivery import email_ready, sms_ready
    return {'payment':{'enabled':configured(),'provider':settings.gateway_name if configured() else None,
                       'mode':settings.gateway_mode,'wallet_test_credit':wallet_enabled()},
        'scanner':'OWNED_OR_ASSIGNED_GYMS', 'gateway_rescheduling':False,'refund_initiation':False,
        'notification_preferences':settings.notification_workflows_enabled,'global_settings_editable':False,
        'notification_email_worker_enabled':settings.notification_workflows_enabled and settings.notification_email_enabled,
        'support_requests':settings.support_workflows_enabled and settings.operational_workflows_enabled,
        'photo_deletion':settings.operational_workflows_enabled,'photo_reordering':True,
        'operational_audit_enabled':settings.operational_workflows_enabled,
        'account_delivery':{'email':email_ready(),'sms':sms_ready()},
        'audit_coverage':['GYM_REVIEW','MEMBERSHIP_PLAN'] + (['ACCOUNT','BOOKING','STAFF','PHOTO'] if settings.operational_workflows_enabled else [])
            + (['SUPPORT'] if settings.support_workflows_enabled and settings.operational_workflows_enabled else []),
        'limitations':{'refunds':'Cancellation does not initiate a refund. Provider-confirmed refund status is reconciled separately.',
            'rescheduling':'Gateway and class rescheduling are unavailable pending payment-adjustment and reservation policies.',
            'notifications':('In-app notifications and read state are enabled. Operational email is opt-in; a separately enabled worker records acceptance, not delivery.'
                if settings.notification_workflows_enabled else 'Notification inbox/preferences remain disabled until their migration and deployment flag are enabled.'),
            'photos':('Photo removal uses durable cleanup jobs. Pending/blocked cleanup is reported and can be retried.' if settings.operational_workflows_enabled
                      else 'Photo deletion and expanded audit are disabled until the operational migration and deployment flag are enabled.')}}


@router.get('/meta/workflows')
def workflows(response:Response,user=Depends(get_current_user)):
    response.headers['Cache-Control']='no-store'
    return capabilities()


@router.get('/admin/settings')
def admin_settings(response:Response,user=Depends(require_role({'ADMIN','SUPER_ADMIN'}))):
    response.headers['Cache-Control']='no-store'
    return capabilities()