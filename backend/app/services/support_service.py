"""Scoped support, optimistic concurrency, request idempotency and safe audit."""
from datetime import datetime
from fastapi import HTTPException
from sqlalchemy import select, func
from app.core.config import settings
from app.core.time import as_ist
from app.models.auth import User, UserRole, Role
from app.models.support import SupportTicket, SupportMessage
from app.services.operation_audit import record
from app.services.password_service import PasswordService


class SupportService:
    def __init__(self, db, actor, *, admin=False):
        self.db, self.actor_id, self.actor_version, self.admin = db, actor.id, actor.token_version, admin
        if not settings.support_workflows_enabled or not settings.operational_workflows_enabled:
            raise HTTPException(409, 'Support requests are not enabled in this deployment.')
        self.authorize()

    def authorize(self, lock=False):
        query = select(User).where(User.id == self.actor_id)
        if lock: query = query.with_for_update().execution_options(populate_existing=True)
        user = self.db.scalar(query)
        if not user or user.status != 'ACTIVE' or user.token_version != self.actor_version:
            raise HTTPException(401, 'Session expired. Sign in again.')
        if self.admin:
            role_query = select(UserRole.id).join(Role, Role.id == UserRole.role_id).where(
                UserRole.user_id == user.id, Role.name.in_(['ADMIN', 'SUPER_ADMIN']))
            if lock: role_query = role_query.with_for_update()
            if not self.db.scalar(role_query.limit(1)): raise HTTPException(403, 'Insufficient permissions')

    def ticket(self, ticket_id, lock=False):
        query = select(SupportTicket).where(SupportTicket.id == ticket_id)
        if not self.admin: query = query.where(SupportTicket.user_id == self.actor_id)
        if lock: query = query.with_for_update().execution_options(populate_existing=True)
        ticket = self.db.scalar(query)
        if not ticket: raise HTTPException(404, 'Support request not found')
        return ticket

    @staticmethod
    def present(ticket):
        return {'id': ticket.id, 'user_id': ticket.user_id, 'category': ticket.category, 'subject': ticket.subject,
                'status': ticket.status, 'version': ticket.version, 'created_at': as_ist(ticket.created_at),
                'updated_at': as_ist(ticket.updated_at)}

    def list(self, status, q, limit, offset):
        query = select(SupportTicket)
        if not self.admin: query = query.where(SupportTicket.user_id == self.actor_id)
        if status: query = query.where(SupportTicket.status == status)
        if q: query = query.where(SupportTicket.subject.contains(q, autoescape=True))
        total = self.db.scalar(select(func.count()).select_from(query.subquery()))
        rows = self.db.scalars(query.order_by(SupportTicket.updated_at.desc(), SupportTicket.id.desc()).limit(limit).offset(offset))
        return {'items': [self.present(t) for t in rows], 'total': total, 'limit': limit, 'offset': offset}

    def detail(self, ticket_id, limit, offset):
        ticket = self.ticket(ticket_id)
        query = select(SupportMessage).where(SupportMessage.ticket_id == ticket.id)
        messages = self.db.scalars(query.order_by(SupportMessage.id).limit(limit).offset(offset))
        return {**self.present(ticket), 'messages': [
            {'id': m.id, 'author_kind': m.author_kind, 'body': m.body, 'created_at': as_ist(m.created_at)} for m in messages],
            'message_total': self.db.scalar(select(func.count()).select_from(query.subquery())), 'limit': limit, 'offset': offset,
            'can_reply': ticket.status != 'RESOLVED', 'can_change_status': self.admin}

    def throttle(self):
        # Persistent fixed window; raw support text/subject never enters the key.
        PasswordService(self.db).throttle(f'support-write:{self.actor_id}', 30, 900)
        self.authorize(lock=True)

    def create(self, payload, key):
        self.throttle()
        try:
            existing = self.db.scalar(select(SupportTicket).where(SupportTicket.user_id == self.actor_id,
                SupportTicket.request_key == key).with_for_update())
            if existing:
                message = self.db.scalar(select(SupportMessage.body).where(SupportMessage.ticket_id == existing.id)
                                         .order_by(SupportMessage.id).limit(1))
                if (existing.subject, existing.category, message) != (payload.subject, payload.category, payload.body):
                    raise HTTPException(409, 'Idempotency key belongs to another support request.')
                result = self.present(existing); self.db.commit(); return result
            ticket = SupportTicket(user_id=self.actor_id, request_key=key, category=payload.category, subject=payload.subject)
            self.db.add(ticket); self.db.flush()
            self.db.add(SupportMessage(ticket_id=ticket.id, author_id=self.actor_id, author_kind='REQUESTER', request_key=key, body=payload.body))
            record(self.db, 'SUPPORT_CREATED', ticket.id, self.actor_id)
            self.db.commit()
            return self.present(ticket)
        except Exception:
            self.db.rollback(); raise

    def reply(self, ticket_id, payload, key):
        # Deny foreign identifiers before consuming quota or exposing ticket state.
        self.ticket(ticket_id)
        self.throttle()
        try:
            ticket = self.ticket(ticket_id, lock=True)
            existing = self.db.scalar(select(SupportMessage).where(SupportMessage.ticket_id == ticket.id,
                SupportMessage.author_id == self.actor_id, SupportMessage.request_key == key).with_for_update())
            kind = 'ADMIN' if self.admin else 'REQUESTER'
            if existing:
                if existing.body != payload.body or existing.author_kind != kind:
                    raise HTTPException(409, 'Idempotency key belongs to another message.')
                result = self.present(ticket); self.db.commit(); return result
            if ticket.version != payload.expected_version: raise HTTPException(409, 'Conversation changed. Refresh before replying.')
            if ticket.status == 'RESOLVED': raise HTTPException(409, 'Request is resolved. An administrator must reopen it before another reply.')
            self.db.add(SupportMessage(ticket_id=ticket.id, author_id=self.actor_id, author_kind=kind, request_key=key, body=payload.body))
            ticket.version += 1; ticket.updated_at = datetime.utcnow()
            record(self.db, 'SUPPORT_REPLIED', ticket.id, self.actor_id)
            self.db.commit()
            return self.present(ticket)
        except Exception:
            self.db.rollback(); raise

    def change_status(self, ticket_id, payload):
        if not self.admin: raise HTTPException(403, 'Administrator access required')
        self.throttle()
        try:
            ticket = self.ticket(ticket_id, lock=True)
            if ticket.version != payload.expected_version: raise HTTPException(409, 'Conversation changed. Refresh before changing its status.')
            if ticket.status != payload.status:
                old = ticket.status; ticket.status = payload.status; ticket.version += 1; ticket.updated_at = datetime.utcnow()
                record(self.db, 'SUPPORT_STATUS_CHANGED', ticket.id, self.actor_id, reason_code='ADMIN_REQUEST',
                       from_status=old, to_status=ticket.status)
            self.db.commit()
            return self.present(ticket)
        except Exception:
            self.db.rollback(); raise