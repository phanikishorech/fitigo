from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.dependencies import require_role
from app.core.roles import ROLE_GYM_STAFF, ROLE_GYM_OWNER
from app.models.gym import Gym
from app.database.session import get_db
from app.models.auth import User
from app.schemas.access import (
    ValidateCheckinFailureResponse,
    ValidateCheckinRequest,
    ValidateCheckinSuccessResponse,
)
from app.services.access_service import AccessService
from app.services.staff_service import StaffService


router = APIRouter(prefix="/checkins")


@router.post("/validate", response_model=ValidateCheckinSuccessResponse | ValidateCheckinFailureResponse)
def validate_checkin(
    payload: ValidateCheckinRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role({ROLE_GYM_STAFF, ROLE_GYM_OWNER})),
):
    # Ensure staff is assigned to this gym (for MVP where gym_id comes from request)
    svc_staff = StaffService(db)
    gym = db.get(Gym, payload.gym_id)
    if not (gym and gym.owner_user_id == current_user.id) and int(payload.gym_id) not in set(svc_staff.staff_gym_ids(staff_user_id=current_user.id)):
        # keep consistent with other staff endpoints
        return ValidateCheckinFailureResponse(success=False, status="GYM_NOT_ALLOWED", message="Gym not found")

    svc = AccessService(db)
    try:
        res = svc.validate_checkin(gym_id=int(payload.gym_id), qr_token=payload.qr_token, scanned_by=current_user.id)
        return ValidateCheckinSuccessResponse(**res)
    except Exception as e:
        # Convert FastAPI HTTPException to structured errors
        from fastapi import HTTPException

        if isinstance(e, HTTPException):
            code = getattr(e, "status_code", 400)
            if code >= 500:
                # Operational failures are not QR rejections and must use the
                # central safe-error handler rather than echoing detail as 200.
                raise
            msg = getattr(e, "detail", "Invalid")
            if isinstance(msg, dict) and msg.get("code") and msg.get("message"):
                return ValidateCheckinFailureResponse(success=False, status=msg["code"], message=msg["message"])
            if isinstance(msg, dict) and msg.get("code") == "MEMBERSHIP_PAUSED":
                return ValidateCheckinFailureResponse(success=False, status="MEMBERSHIP_PAUSED", message="This membership is paused. Access resumes after the pause period.")
            if code == 409:
                return ValidateCheckinFailureResponse(success=False, status="QR_ALREADY_USED", message=str(msg))
            if "only at" in str(msg):
                return ValidateCheckinFailureResponse(success=False, status="WRONG_GYM", message=str(msg))
            if "already been used" in str(msg):
                return ValidateCheckinFailureResponse(success=False, status="DAILY_ACCESS_ALREADY_USED", message=str(msg))
            return ValidateCheckinFailureResponse(success=False, status="INVALID_QR", message=str(msg))
        raise
