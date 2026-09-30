from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.dependencies import require_role
from app.core.roles import ROLE_GYM_STAFF
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
    current_user: User = Depends(require_role({ROLE_GYM_STAFF})),
):
    # Ensure staff is assigned to this gym (for MVP where gym_id comes from request)
    svc_staff = StaffService(db)
    if int(payload.gym_id) not in set(svc_staff.staff_gym_ids(staff_user_id=current_user.id)):
        # keep consistent with other staff endpoints
        return ValidateCheckinFailureResponse(success=False, status="GYM_NOT_ALLOWED", message="Gym not found")

    svc = AccessService(db)
    try:
        res = svc.validate_checkin(gym_id=int(payload.gym_id), qr_token=payload.qr_token)
        return ValidateCheckinSuccessResponse(**res)
    except Exception as e:
        # Convert FastAPI HTTPException to structured errors
        from fastapi import HTTPException

        if isinstance(e, HTTPException):
            code = getattr(e, "status_code", 400)
            msg = getattr(e, "detail", "Invalid")
            if code == 409:
                return ValidateCheckinFailureResponse(success=False, status="QR_ALREADY_USED", message=str(msg))
            if "only at" in str(msg):
                return ValidateCheckinFailureResponse(success=False, status="WRONG_GYM", message=str(msg))
            if "already been used" in str(msg):
                return ValidateCheckinFailureResponse(success=False, status="DAILY_ACCESS_ALREADY_USED", message=str(msg))
            return ValidateCheckinFailureResponse(success=False, status="INVALID_QR", message=str(msg))
        raise
