"""Read-only view of existing event sources; explicitly not a global audit log."""
from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import select, union_all, literal, func
from sqlalchemy.orm import Session
from app.core.dependencies import require_role
from app.database.session import get_db
from app.models.gym import GymStatusHistory
from app.models.platform_membership import PlatformMembershipAudit
from app.core.time import as_ist
from app.core.config import settings
from app.models.operations import OperationAudit
from app.services.operation_audit import ACTIONS, REASONS, ENUMS, VALUES, NUMBERS, FLAGS, DATES

router=APIRouter()


@router.get('/audit-logs')
def audit(response:Response,limit:int=Query(20,ge=1,le=100),offset:int=Query(0,ge=0),db:Session=Depends(get_db),
          user=Depends(require_role({'ADMIN','SUPER_ADMIN'}))):
    response.headers['Cache-Control']='no-store'
    # Never return unstructured reason/details fields: legacy metadata may hold
    # secrets or personal data. Only known enum transitions are safe context.
    statements=[select(literal('GYM_REVIEW').label('source'),GymStatusHistory.id.label('id'),
        GymStatusHistory.changed_by_user_id.label('actor_id'),GymStatusHistory.gym_id.label('resource_id'),
        GymStatusHistory.created_at.label('at'),GymStatusHistory.old_status.label('old'),GymStatusHistory.new_status.label('new')),
        select(literal('MEMBERSHIP_PLAN'),PlatformMembershipAudit.id,PlatformMembershipAudit.actor_id,
        PlatformMembershipAudit.plan_id,PlatformMembershipAudit.created_at,literal(None),PlatformMembershipAudit.action)]
    if settings.operational_workflows_enabled:
        statements.append(select(OperationAudit.resource_type, OperationAudit.id, OperationAudit.actor_id,
            OperationAudit.resource_id, OperationAudit.created_at, OperationAudit.reason_code, OperationAudit.action))
    source=union_all(*statements).subquery()
    valid_status={'DRAFT','PENDING_APPROVAL','APPROVED','REJECTED','SUSPENDED','INACTIVE'}
    valid_action={'CREATE','UPDATE','OFFER_UPDATE','CREATE_PLAN','UPDATE_PLAN','UPDATE_OFFER','PLAN_CREATED','PLAN_UPDATED','OFFER_UPDATED'}
    items=[]
    for row in db.execute(select(source).order_by(source.c.at.desc(),source.c.source,source.c.id.desc()).limit(limit).offset(offset)).mappings():
        safe_context = {}
        if row['source'] not in {'GYM_REVIEW','MEMBERSHIP_PLAN'} and settings.operational_workflows_enabled:
            event = db.get(OperationAudit, row['id'])
            if event and isinstance(event.context, dict):
                for key, value in event.context.items():
                    if ((key in ENUMS and isinstance(value,str) and value in VALUES)
                            or (key in NUMBERS and type(value) is int and value > 0)
                            or (key in FLAGS and type(value) is bool)):
                        safe_context[key] = value
                    elif key in DATES and isinstance(value,str):
                        from datetime import date
                        try:
                            if len(value)==10 and date.fromisoformat(value).isoformat()==value: safe_context[key]=value
                        except ValueError: pass
            if row['old'] in REASONS: safe_context['reason'] = row['old']
        items.append({'id':f"{row['source']}:{row['id']}",'actor_id':row['actor_id'],'resource_type':row['source'],
            'resource_id':row['resource_id'],'timestamp':as_ist(row['at']),
            'action':('STATUS_CHANGE' if row['source']=='GYM_REVIEW' else row['new'] if row['new'] in valid_action or row['new'] in ACTIONS else 'PLAN_CHANGE'),
            'context':{'from':row['old'],'to':row['new']} if row['source']=='GYM_REVIEW' and row['old'] in valid_status and row['new'] in valid_status
                else safe_context})
    return {'items':items,'total':db.scalar(select(func.count()).select_from(source)),
            'coverage':['GYM_REVIEW','MEMBERSHIP_PLAN'] + (['ACCOUNT','BOOKING','STAFF','PHOTO'] if settings.operational_workflows_enabled else [])
                + (['SUPPORT'] if settings.support_workflows_enabled and settings.operational_workflows_enabled else []),
            'operational_audit_enabled':settings.operational_workflows_enabled,'complete_platform_history':False}