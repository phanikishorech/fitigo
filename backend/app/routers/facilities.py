from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.repositories.gym_repository import GymRepository
from app.schemas.gym import GymFacilityResponse


router = APIRouter(prefix="/facilities")


@router.get("", response_model=list[GymFacilityResponse])
def list_facilities(db: Session = Depends(get_db)):
    repo = GymRepository(db)
    facs = repo.list_facilities()
    return [GymFacilityResponse(id=f.id, name=f.name, description=f.description, icon=f.icon) for f in facs]
