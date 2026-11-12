"""Private support threads. No attachment/payment credentials or cascade deletion."""
from datetime import datetime
from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, event
from sqlalchemy.orm import Mapped, mapped_column
from app.database.base import Base


class SupportTicket(Base):
    __tablename__ = 'support_tickets'
    __table_args__ = (UniqueConstraint('user_id', 'request_key', name='uq_support_ticket_request'),)
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey('users.id'), index=True)
    request_key: Mapped[str] = mapped_column(String(64))
    category: Mapped[str] = mapped_column(String(20))
    subject: Mapped[str] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(20), default='OPEN', index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class SupportMessage(Base):
    __tablename__ = 'support_messages'
    __table_args__ = (UniqueConstraint('ticket_id', 'author_id', 'request_key', name='uq_support_message_request'),)
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    ticket_id: Mapped[int] = mapped_column(BigInteger, ForeignKey('support_tickets.id'), index=True)
    author_id: Mapped[int] = mapped_column(BigInteger, ForeignKey('users.id'))
    author_kind: Mapped[str] = mapped_column(String(20))
    request_key: Mapped[str] = mapped_column(String(64))
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


@event.listens_for(SupportMessage, 'before_update')
@event.listens_for(SupportMessage, 'before_delete')
def preserve_conversation(mapper, connection, target):
    raise ValueError('Support messages are append-only through the application.')