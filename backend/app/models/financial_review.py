"""Append-only review decisions, not financial adjustments or payment instructions."""
from datetime import datetime
from sqlalchemy import BigInteger,DateTime,ForeignKey,Integer,JSON,String,UniqueConstraint,event
from sqlalchemy.orm import Mapped,mapped_column
from app.database.base import Base


class FinancialReviewEvent(Base):
    __tablename__='financial_review_events'
    __table_args__=(UniqueConstraint('case_id','revision',name='uq_fin_review_revision'),
        UniqueConstraint('mode','request_key',name='uq_fin_review_request'),)
    id: Mapped[str]=mapped_column(String(36),primary_key=True)
    case_id: Mapped[str]=mapped_column(String(36),index=True)
    revision: Mapped[int]=mapped_column(Integer)
    mode: Mapped[str]=mapped_column(String(10))
    gym_id: Mapped[int]=mapped_column(BigInteger,ForeignKey('gyms.id'))
    checkout_id: Mapped[str]=mapped_column(String(36),ForeignKey('payment_checkouts.id'))
    source_evidence_id: Mapped[str]=mapped_column(String(36),ForeignKey('financial_source_evidence.id'))
    kind: Mapped[str]=mapped_column(String(40))
    status: Mapped[str]=mapped_column(String(40))
    actor_id: Mapped[int]=mapped_column(BigInteger,ForeignKey('users.id'))
    reason: Mapped[str]=mapped_column(String(500))
    request_key: Mapped[str]=mapped_column(String(64))
    request_hash: Mapped[str]=mapped_column(String(64))
    snapshot: Mapped[dict]=mapped_column(JSON)
    snapshot_hash: Mapped[str]=mapped_column(String(64))
    created_at: Mapped[datetime]=mapped_column(DateTime)


@event.listens_for(FinancialReviewEvent,'before_update')
@event.listens_for(FinancialReviewEvent,'before_delete')
def immutable_review(mapper,connection,target):
    raise ValueError('Financial review history is append-only.')