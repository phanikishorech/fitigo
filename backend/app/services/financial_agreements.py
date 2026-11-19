"""Future-only agreement versions. No purchase writes or retrospective repricing."""
import hashlib
import json
from copy import deepcopy
from fastapi import HTTPException
from sqlalchemy import func, inspect, select
from app.core.time import as_ist, stored_instant, utcnow
from app.models.financial_agreement import FinancialAgreementScope, FinancialAgreementVersion
from app.models.gym import Gym
from app.services.accounting_policy import contract_catalog, policy_readiness


def available(db):
    inspector = inspect(db.connection())
    return all(inspector.has_table(name) for name in ('financial_agreement_scopes', 'financial_agreement_versions'))


def require_schema(db):
    if not available(db):
        raise HTTPException(503, 'Revenue-sharing configuration requires migration d46e70ba9268. No settings were saved.')


def scope_key(gym_id):
    return f'GYM:{gym_id}' if gym_id is not None else 'DEFAULT'


def scope(db, mode, gym_id, *, lock=False):
    query = select(FinancialAgreementScope).where(FinancialAgreementScope.mode == mode,
        FinancialAgreementScope.scope_key == scope_key(gym_id))
    return db.scalar(query.with_for_update().execution_options(populate_existing=True) if lock else query)


def latest(db, identifier, *, lock=False):
    query = select(FinancialAgreementVersion).where(FinancialAgreementVersion.scope_id == identifier).order_by(FinancialAgreementVersion.version.desc()).limit(1)
    return db.scalar(query.with_for_update().execution_options(populate_existing=True) if lock else query)


def active_version(db, identifier, instant, *, lock=False):
    # The newest commenced version supersedes older terms permanently. Expiry
    # never revives an older gym override. A missing override falls back to default.
    query = select(FinancialAgreementVersion).where(FinancialAgreementVersion.scope_id == identifier,
        FinancialAgreementVersion.effective_from <= instant).order_by(FinancialAgreementVersion.effective_from.desc()).limit(1)
    row = db.scalar(query.with_for_update().execution_options(populate_existing=True) if lock else query)
    if not row or row.action == 'INHERIT' or (row.effective_to and row.effective_to <= instant): return None
    return row


def resolve(db, mode, gym_id, instant, *, lock=False):
    """Read an exact immutable agreement version; callers must pin its ID when posting.

    This is a configuration resolver only. No financial transaction currently uses
    it to recalculate completed commissions or to initiate payouts.
    """
    require_schema(db)
    if mode not in {'test', 'live'}: raise HTTPException(422, 'Invalid payment environment')
    if instant.tzinfo is None: raise HTTPException(422, 'Resolution time requires a timezone')
    at = stored_instant(instant)
    if gym_id is not None:
        custom = scope(db, mode, gym_id, lock=lock)
        selected = active_version(db, custom.id, at, lock=lock) if custom else None
        if selected: return selected
    standard = scope(db, mode, None, lock=lock)
    return active_version(db, standard.id, at, lock=lock) if standard else None


def present(db, row, now=None):
    now = stored_instant(now or utcnow())
    next_start = db.scalar(select(func.min(FinancialAgreementVersion.effective_from)).where(
        FinancialAgreementVersion.scope_id == row.scope_id,
        FinancialAgreementVersion.effective_from > row.effective_from))
    ends = min(value for value in (row.effective_to, next_start) if value is not None) if row.effective_to or next_start else None
    state = 'SCHEDULED' if row.effective_from > now else 'EXPIRED' if ends and ends <= now else 'INHERITING' if row.action == 'INHERIT' else 'EFFECTIVE'
    return {'id': row.id, 'scope_id': row.scope_id, 'version': row.version, 'action': row.action,
        'effective_from': as_ist(row.effective_from).isoformat(),
        'effective_to': as_ist(row.effective_to).isoformat() if row.effective_to else None,
        'superseded_at': as_ist(next_start).isoformat() if next_start else None,
        'applies_until': as_ist(ends).isoformat() if ends else None, 'state': state,
        'policy_readiness': policy_readiness(row.terms),
        'terms': row.terms if row.action == 'AGREEMENT' else None, 'agreement_reference': row.agreement_reference,
        'reason': row.reason, 'ca_status': row.ca_status, 'ca_reference': row.ca_reference,
        'actor_id': row.actor_id, 'created_at': as_ist(row.created_at).isoformat(), 'statutory_reporting_enabled': False}


def configuration(db, mode, gym_id=None, limit=20, offset=0):
    if mode not in {'test', 'live'}: raise HTTPException(422, 'Invalid payment environment')
    if gym_id is not None and not db.get(Gym, gym_id): raise HTTPException(404, 'Gym not found')
    now = utcnow()
    base = {'policy_catalog': contract_catalog(), 'available': available(db), 'mode': mode, 'gym_id': gym_id,
        'server_time': as_ist(now).isoformat(), 'statutory_reporting_enabled': False,
        'posting_enabled': False, 'options': [dict(r) for r in db.execute(select(Gym.id, Gym.name).order_by(Gym.name)).mappings()],
        'notice': 'Configuration only. No commission postings, payouts, or statutory reporting are enabled. New versions are future-only; completed transactions are never repriced.'}
    if not base['available']:
        return {**base, 'reason': 'Apply migration d46e70ba9268 before configuring revenue sharing.',
            'latest_version': 0, 'latest': None, 'effective': None, 'template': None, 'history': [], 'total': 0}
    standard = scope(db, mode, None)
    selected_scope = scope(db, mode, gym_id)
    last = latest(db, selected_scope.id) if selected_scope else None
    effective = resolve(db, mode, gym_id, now)
    default_latest = latest(db, standard.id) if standard else None
    template = (last.terms if last and last.action == 'AGREEMENT' else
        effective.terms if effective else default_latest.terms if default_latest and default_latest.action == 'AGREEMENT' else
        standard.template if standard else None)
    rows = select(FinancialAgreementVersion).where(FinancialAgreementVersion.scope_id == selected_scope.id) if selected_scope else None
    total = db.scalar(select(func.count()).select_from(rows.subquery())) if rows is not None else 0
    history = list(db.scalars(rows.order_by(FinancialAgreementVersion.version.desc()).limit(limit).offset(offset))) if rows is not None else []
    return {**base, 'latest_version': last.version if last else 0, 'latest': present(db, last, now) if last else None,
        'effective': present(db, effective, now) if effective else None,
        'effective_scope': 'GYM' if effective and selected_scope and effective.scope_id == selected_scope.id and gym_id else 'DEFAULT' if effective else None,
        'template': deepcopy(template), 'history': [present(db, r, now) for r in history], 'total': total,
        'limits_notice': 'Blank Multi-Gym rate or cap means NOT CONFIGURED, never zero or unlimited. Existing visit limits are per member, per gym, per calendar month. Phase 2 records explicit policy choices and cutoffs only; allocation posting and settlement execution remain unimplemented.'}


def create(db, actor_id, payload, key):
    require_schema(db)
    canonical = payload.model_dump(mode='json')
    # Preserve hashes for all pre-Phase-2 requests, including retries after rollout.
    if canonical.get('terms') and canonical['terms'].get('policy_contract') is None:
        canonical['terms'].pop('policy_contract', None)
    if canonical.get('terms') and canonical['terms'].get('marketplace_contract') is None:
        canonical['terms'].pop('marketplace_contract', None)
    if canonical.get('terms') and canonical['terms'].get('visit_payout_contract') is None:
        canonical['terms'].pop('visit_payout_contract', None)
    digest = hashlib.sha256(json.dumps(canonical, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    try:
        # Default scope is the stable lock for this environment, including creation
        # of the first gym override. Never rely on locking a nonexistent row.
        root = db.scalar(select(FinancialAgreementScope).where(FinancialAgreementScope.mode == payload.mode,
            FinancialAgreementScope.scope_key == 'DEFAULT').with_for_update().execution_options(populate_existing=True))
        if root is None: raise HTTPException(409, 'Default scope is missing; repair the configuration migration first.')
        if payload.gym_id is not None and not db.get(Gym, payload.gym_id): raise HTTPException(404, 'Gym not found')
        selected = root if payload.gym_id is None else scope(db, payload.mode, payload.gym_id, lock=True)
        if selected:
            previous = db.scalar(select(FinancialAgreementVersion).where(FinancialAgreementVersion.scope_id == selected.id,
                FinancialAgreementVersion.request_key == key).with_for_update().execution_options(populate_existing=True))
            if previous:
                if previous.request_hash != digest or previous.actor_id != actor_id:
                    raise HTTPException(409, 'This request key belongs to a different change.')
                result = present(db, previous); db.commit(); return result
        last = latest(db, selected.id, lock=True) if selected else None
        if last and 'financial_settings' in last.terms:
            raise HTTPException(409, 'This gym uses consolidated Financial Settings. Legacy edits and inheritance are disabled for it.')
        if payload.expected_version != (last.version if last else 0):
            raise HTTPException(409, 'Another administrator changed this agreement. Reload history before saving.')
        starts = stored_instant(payload.effective_from)
        now = stored_instant(utcnow()).replace(microsecond=0)
        if starts <= now: raise HTTPException(422, 'Effective start must be in the future. Backdated changes are not allowed.')
        if last and starts <= last.effective_from:
            raise HTTPException(409, 'Schedule after the latest version start. Earlier or same-time replacements are not allowed.')
        if not selected:
            selected = FinancialAgreementScope(mode=payload.mode, scope_key=scope_key(payload.gym_id), gym_id=payload.gym_id)
            db.add(selected); db.flush()
        row = FinancialAgreementVersion(scope_id=selected.id, version=payload.expected_version+1,
            effective_from=starts, effective_to=stored_instant(payload.effective_to) if payload.effective_to else None,
            terms=canonical['terms'] if payload.terms else {}, action=payload.action,
            agreement_reference=payload.agreement_reference, reason=payload.reason, ca_status=payload.ca_status,
            ca_reference=payload.ca_reference, actor_id=actor_id, request_key=key, request_hash=digest, created_at=now)
        db.add(row); db.flush()
        # The immutable version itself is mandatory financial change evidence,
        # independent of the optional general operational-audit deployment gate.
        result = present(db, row); db.commit(); return result
    except Exception:
        db.rollback()
        raise