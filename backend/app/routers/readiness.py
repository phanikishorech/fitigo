from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session
from app.database.session import get_db
from app.core.dependencies import require_role
from app.services.readiness_service import readiness

router = APIRouter()


@router.get('/admin/readiness')
def report(response: Response, db: Session = Depends(get_db), user=Depends(require_role({'ADMIN', 'SUPER_ADMIN'}))):
    response.headers['Cache-Control'] = 'no-store'
    return readiness(db)