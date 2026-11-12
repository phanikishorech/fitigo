from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel, ConfigDict, StrictBool
from sqlalchemy.orm import Session
from app.core.dependencies import get_current_user, require_role
from app.database.session import get_db
from app.models.auth import User
from app.services import notification_workflow as service
from app.models.notification_delivery import NotificationDelivery
from app.core.config import settings
from app.core.time import as_ist
from sqlalchemy import select, func

router=APIRouter()


class PreferenceUpdate(BaseModel):
    model_config=ConfigDict(extra='forbid')
    operational_email: StrictBool


@router.get('/preferences')
def preferences(response:Response,db:Session=Depends(get_db),user:User=Depends(get_current_user)):
    response.headers['Cache-Control']='no-store'
    return service.preferences(db,user)


@router.patch('/preferences')
def update(payload:PreferenceUpdate,response:Response,db:Session=Depends(get_db),user:User=Depends(get_current_user)):
    response.headers['Cache-Control']='no-store'
    return service.update_preferences(db,user.id,payload.operational_email)


@router.get('/inbox')
def inbox(response:Response,limit:int=Query(20,ge=1,le=100),offset:int=Query(0,ge=0),unread:bool=False,
          db:Session=Depends(get_db),user:User=Depends(get_current_user)):
    response.headers['Cache-Control']='no-store'
    return service.inbox(db,user.id,limit,offset,unread)


@router.post('/inbox/{notification_id}/read')
def read(notification_id:int,response:Response,db:Session=Depends(get_db),user:User=Depends(get_current_user)):
    response.headers['Cache-Control']='no-store'
    return service.mark_read(db,user.id,notification_id)


@router.get('/delivery-status')
def delivery_status(response:Response,limit:int=Query(20,ge=1,le=100),offset:int=Query(0,ge=0),
                    db:Session=Depends(get_db),user:User=Depends(require_role({'ADMIN','SUPER_ADMIN'}))):
    response.headers['Cache-Control']='no-store'
    if not settings.notification_workflows_enabled:
        return {'enabled':False,'items':[],'total':0}
    rows=db.scalars(select(NotificationDelivery).where(NotificationDelivery.email_status.notin_(['NOT_REQUESTED']))
                    .order_by(NotificationDelivery.id.desc()).limit(limit).offset(offset))
    return {'enabled':True,'items':[{'id':row.id,'user_id':row.user_id,'kind':row.kind,'email_status':row.email_status,
        'attempts':row.attempts,'error_code':row.error_code,'created_at':as_ist(row.created_at),
        'accepted_at':as_ist(row.accepted_at) if row.accepted_at else None} for row in rows],
        'total':db.scalar(select(func.count(NotificationDelivery.id)).where(NotificationDelivery.email_status!='NOT_REQUESTED'))}