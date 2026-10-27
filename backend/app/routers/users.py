from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user
from app.database.session import get_db
from app.models.auth import User, RefreshToken, PasswordResetToken
from app.repositories.user_repository import UserRepository
from app.schemas.user import UserMeResponse, UserProfileUpdate
from app.core.security import verify_password
from app.services.password_service import PasswordService, now


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
        is_email_verified=current_user.is_email_verified,
        is_phone_verified=current_user.is_phone_verified,
    )


@router.patch('/me')
def update_me(payload: UserProfileUpdate, response: Response, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    response.headers['Cache-Control'] = 'no-store'
    uid, version = current_user.id, current_user.token_version
    PasswordService(db).throttle(f'profile-edit:{uid}', 10, 900)
    user = db.scalar(select(User).where(User.id == uid).with_for_update().execution_options(populate_existing=True))
    if not user or user.status != 'ACTIVE' or user.token_version != version:
        raise HTTPException(401, 'Session expired. Sign in again.')
    email, phone = str(payload.email).lower(), payload.phone
    contact_changed = email != user.email or phone != user.phone
    if contact_changed and (not payload.current_password or not verify_password(payload.current_password, user.password_hash)):
        raise HTTPException(400, 'Your current password is incorrect.')
    user.first_name, user.last_name = payload.first_name, payload.last_name or None
    if email != user.email:
        user.email, user.is_email_verified = email, False
    if phone != user.phone:
        user.phone, user.is_phone_verified = phone, False
    try:
        if contact_changed:
            user.token_version += 1
            db.execute(update(RefreshToken).where(RefreshToken.user_id == uid, RefreshToken.revoked_at.is_(None)).values(revoked_at=now()))
            db.execute(update(PasswordResetToken).where(PasswordResetToken.user_id == uid, PasswordResetToken.used_at.is_(None)).values(used_at=now()))
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, 'Those contact details are unavailable. Use different contact details.') from None
    return {'user': me(user, db).model_dump(mode='json'), 'reauthenticate': contact_changed}


@router.get("/me/roles", response_model=list[str])
def my_roles(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    repo = UserRepository(db)
    return repo.get_role_names(current_user.id)
