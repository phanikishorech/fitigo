from datetime import date
from typing import Literal
from fastapi import APIRouter,Depends,Query,Response
from sqlalchemy.orm import Session
from app.core.dependencies import require_role
from app.database.session import get_db
from app.models.auth import User
from app.services import admin_business as service

router=APIRouter(prefix='/business')
admin=require_role({'ADMIN','SUPER_ADMIN'})


@router.get('/summary')
def summary(response:Response,date_from:date|None=None,date_to:date|None=None,mode:Literal['test','live']|None=None,
            gym_id:int|None=Query(None,gt=0),db:Session=Depends(get_db),user:User=Depends(admin)):
    response.headers['Cache-Control']='no-store'
    return service.summary(db,date_from=date_from,date_to=date_to,mode=mode,gym_id=gym_id)


@router.get('/memberships')
def memberships(response:Response,q:str=Query('',max_length=100),status:Literal['ACTIVE','EXPIRED','PAUSED','CANCELLED','UPCOMING','UNPAID']|None=None,
                kind:Literal['SINGLE_GYM','MULTI_GYM']|None=None,gym_id:int|None=Query(None,gt=0),user_id:int|None=Query(None,gt=0),
                mode:Literal['test','live']|None=None,limit:int=Query(20,ge=1,le=100),offset:int=Query(0,ge=0),
                db:Session=Depends(get_db),user:User=Depends(admin)):
    response.headers['Cache-Control']='no-store'
    return service.memberships(db,q=q,status=status,kind=kind,gym_id=gym_id,user_id=user_id,mode=mode,limit=limit,offset=offset)


@router.get('/customers/{user_id}')
def customer(user_id:int,response:Response,db:Session=Depends(get_db),user:User=Depends(admin)):
    response.headers['Cache-Control']='no-store'
    return service.customer_activity(db,user_id)


@router.get('/bookings/{booking_id}/attendance')
def attendance(booking_id:int,response:Response,db:Session=Depends(get_db),user:User=Depends(admin)):
    response.headers['Cache-Control']='no-store'
    return service.booking_attendance(db,booking_id)