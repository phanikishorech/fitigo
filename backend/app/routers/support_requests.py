from fastapi import APIRouter, Depends, Header, Query, Response
from sqlalchemy.orm import Session
from app.core.dependencies import get_current_user, require_role
from app.database.session import get_db
from app.models.auth import User
from app.schemas.support import SupportCreate, SupportReply, SupportStatusChange, TicketStatus
from app.services.support_service import SupportService


def no_store(response: Response): response.headers['Cache-Control'] = 'no-store'


router = APIRouter(prefix='/support', dependencies=[Depends(no_store)])
admin_router = APIRouter(prefix='/admin/support', dependencies=[Depends(no_store)])
administrator = require_role({'ADMIN', 'SUPER_ADMIN'})
request_key = Header(..., alias='Idempotency-Key', min_length=8, max_length=64, pattern=r'^[A-Za-z0-9_-]+$')


@router.get('/tickets')
def my_tickets(status: TicketStatus | None = None, q: str = Query('', max_length=100),
               limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0),
               db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return SupportService(db, user).list(status, q.strip(), limit, offset)


@router.post('/tickets')
def create_ticket(payload: SupportCreate, key: str = request_key,
                  db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return SupportService(db, user).create(payload, key)


@router.get('/tickets/{ticket_id}')
def my_ticket(ticket_id: int, limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0),
              db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return SupportService(db, user).detail(ticket_id, limit, offset)


@router.post('/tickets/{ticket_id}/messages')
def reply(ticket_id: int, payload: SupportReply, key: str = request_key,
          db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return SupportService(db, user).reply(ticket_id, payload, key)


@admin_router.get('/tickets')
def all_tickets(status: TicketStatus | None = None, q: str = Query('', max_length=100),
                limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0),
                db: Session = Depends(get_db), user: User = Depends(administrator)):
    return SupportService(db, user, admin=True).list(status, q.strip(), limit, offset)


@admin_router.get('/tickets/{ticket_id}')
def admin_ticket(ticket_id: int, limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0),
                 db: Session = Depends(get_db), user: User = Depends(administrator)):
    return SupportService(db, user, admin=True).detail(ticket_id, limit, offset)


@admin_router.post('/tickets/{ticket_id}/messages')
def admin_reply(ticket_id: int, payload: SupportReply, key: str = request_key,
                db: Session = Depends(get_db), user: User = Depends(administrator)):
    return SupportService(db, user, admin=True).reply(ticket_id, payload, key)


@admin_router.patch('/tickets/{ticket_id}/status')
def admin_status(ticket_id: int, payload: SupportStatusChange,
                 db: Session = Depends(get_db), user: User = Depends(administrator)):
    return SupportService(db, user, admin=True).change_status(ticket_id, payload)