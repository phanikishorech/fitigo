from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user
from app.database.session import get_db
from app.models.auth import User
from app.repositories.user_repository import UserRepository
from app.schemas.user import UserMeResponse


router = APIRouter(prefix="/users")


@router.get("/me", response_model=UserMeResponse)
def me(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    # db dependency ensures DB configured; current_user also loads from DB.
    return UserMeResponse(
        id=current_user.id,
        first_name=current_user.first_name,
        last_name=current_user.last_name,
        email=current_user.email,
        phone=current_user.phone,
        status=current_user.status,
        created_at=current_user.created_at,
    )


@router.get("/me/roles", response_model=list[str])
def my_roles(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    repo = UserRepository(db)
    return repo.get_role_names(current_user.id)
