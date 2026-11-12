from fastapi import APIRouter, Depends, Query, Response, HTTPException
from sqlalchemy.orm import Session
from app.core.dependencies import require_role
from app.database.session import get_db
from app.models.auth import User
from app.services.owner_member_service import OwnerMemberService

router=APIRouter()
owner=require_role({'GYM_OWNER'})
from pydantic import BaseModel, Field, ConfigDict
from app.services.gym_service import GymService
from app.services.photo_service import PhotoService
from app.models.operations import PhotoDeletion
from app.models.gym import Gym
from sqlalchemy import select
from app.core.config import settings


class ImageOrderRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    image_ids: list[int] = Field(max_length=1000)


@router.delete('/gyms/{gym_id}/images/{image_id}')
def delete_image(gym_id:int,image_id:int,db:Session=Depends(get_db),user:User=Depends(owner)):
    return PhotoService(db).remove(user.id,gym_id,image_id)


@router.get('/gyms/{gym_id}/image-deletions')
def deletion_jobs(gym_id:int,response:Response,db:Session=Depends(get_db),user:User=Depends(owner)):
    response.headers['Cache-Control']='no-store'
    service=PhotoService(db)
    # A read endpoint must not acquire mutation locks or require a writable DB
    # transaction; ownership is still checked before any job data is returned.
    if not db.scalar(select(Gym.id).where(Gym.id==gym_id,Gym.owner_user_id==user.id)):
        raise HTTPException(404,'Gym not found')
    if not settings.operational_workflows_enabled: return {'enabled':False,'items':[]}
    jobs=db.scalars(select(PhotoDeletion).where(PhotoDeletion.gym_id==gym_id,PhotoDeletion.status!='COMPLETE')
                    .order_by(PhotoDeletion.id).limit(100))
    return {'enabled':True,'items':[service.present(job) for job in jobs]}


@router.post('/gyms/{gym_id}/image-deletions/{job_id}/retry')
def retry_deletion(gym_id:int,job_id:int,db:Session=Depends(get_db),user:User=Depends(owner)):
    return PhotoService(db).process(job_id,user.id,gym_id)


@router.put('/gyms/{gym_id}/images/order')
def reorder_images(gym_id:int,payload:ImageOrderRequest,db:Session=Depends(get_db),user:User=Depends(owner)):
    return GymService(db).reorder_images(owner_user_id=user.id,gym_id=gym_id,image_ids=payload.image_ids)


@router.get('/gyms/{gym_id}/members')
def directory(gym_id:int,response:Response,q:str=Query('',max_length=100),limit:int=Query(20,ge=1,le=100),
              offset:int=Query(0,ge=0),db:Session=Depends(get_db),user:User=Depends(owner)):
    response.headers['Cache-Control']='no-store'
    return OwnerMemberService(db,user.id,gym_id).directory(q.strip(),limit,offset)


@router.get('/gyms/{gym_id}/members/{user_id}')
def history(gym_id:int,user_id:int,response:Response,limit:int=Query(20,ge=1,le=100),offset:int=Query(0,ge=0),
            db:Session=Depends(get_db),user:User=Depends(owner)):
    response.headers['Cache-Control']='no-store'
    return OwnerMemberService(db,user.id,gym_id).history(user_id,limit,offset)