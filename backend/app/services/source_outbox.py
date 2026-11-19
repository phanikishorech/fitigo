"""Leased, fenced, retryable handoff. No journal consumer exists in Phase 3."""
from datetime import timedelta
from uuid import uuid4
import hashlib
import json
from sqlalchemy import select, or_, and_
from app.core.time import utcnow, stored_instant
from app.models.source_evidence import SourceOutbox, SourceEvidence
from app.services.source_evidence import enabled


def claim(db, mode, *, now=None, lease_seconds=60):
    if mode not in {'test', 'live'}: raise ValueError('Worker environment must be explicit.')
    if not 1 <= lease_seconds <= 3600: raise ValueError('Invalid lease duration.')
    if not enabled(db): raise ValueError('Source evidence is not enabled.')
    at = stored_instant(now or utcnow())
    row = db.scalar(select(SourceOutbox).where(SourceOutbox.mode==mode,
        or_(and_(SourceOutbox.status.in_(['PENDING','RETRY']), SourceOutbox.available_at<=at),
            and_(SourceOutbox.status=='PROCESSING', SourceOutbox.lease_until<=at)))
        .order_by(SourceOutbox.created_at, SourceOutbox.id).with_for_update(skip_locked=True).limit(1))
    if not row: return None
    row.status='PROCESSING'; row.retry_count+=1; row.lease_token=str(uuid4())
    row.lease_until=at+timedelta(seconds=lease_seconds)
    db.flush()
    return row.id, row.lease_token


def finish(db, event_id, token, mode, *, now=None, error_code=None):
    at=stored_instant(now or utcnow())
    row=db.scalar(select(SourceOutbox).where(SourceOutbox.id==event_id).with_for_update().execution_options(populate_existing=True))
    if not row or row.mode!=mode: raise ValueError('Wrong event environment.')
    if row.status in {'AWAITING_POLICY','AWAITING_EVIDENCE'} and row.lease_token==token: return row
    if row.status!='PROCESSING' or row.lease_token!=token or row.lease_until<=at:
        raise ValueError('Stale or expired worker lease.')
    evidence=db.get(SourceEvidence,row.evidence_id)
    if evidence.mode!=mode or evidence.event_type!=row.event_type or evidence.source_id!=row.source_id:
        raise ValueError('Source event identity/environment mismatch.')
    digest=hashlib.sha256(json.dumps(evidence.payload, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    if digest!=evidence.payload_hash: raise ValueError('Source payload integrity failure.')
    # Do not persist arbitrary exception bodies/provider secrets in last_error.
    if error_code:
        row.last_error='SOURCE_HANDOFF_RETRY'; row.status='RETRY'
        row.available_at=at+timedelta(seconds=min(3600,2**min(row.retry_count,10)))
    else:
        row.status='AWAITING_POLICY' if evidence.evidence_status=='VERIFIED_SOURCE' else 'AWAITING_EVIDENCE'
        row.last_error=None
    row.lease_until=None
    db.flush()
    return row