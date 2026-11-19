"""Gym-only configuration in the existing immutable version store.

No migration, retroactive initialization, posting, approval, or payment side effects.
New-gym initialization joins the caller's transaction; GET never creates settings.
"""
import hashlib
import json
from fastapi import HTTPException
from sqlalchemy import func, select
from app.core.time import stored_instant, utcnow
from app.models.financial_agreement import FinancialAgreementScope, FinancialAgreementVersion
from app.models.gym import Gym
from app.schemas.gym_financial_settings import GymFinancialSettings
from app.services import financial_agreements as agreements

KEY = 'financial_settings'
BLOCKERS = ['SOURCE_TAX_EVIDENCE_REQUIRED', 'PROCESSING_REQUIRES_SEPARATE_ACTIVATION']


def defaults():
    result = GymFinancialSettings().model_dump(mode='json')
    result['multi_gym'].update(period_timezone='Asia/Kolkata', rounding='MONTHLY_TOTAL_HALF_UP',
        version_boundary='PIN_AT_ADMISSION', purchase_fee_attribution='MEMBERSHIP_COMPLETE_EQUAL_VISITS',
        invalidated_visit_correction='APPEND_ONLY_SOURCE_BACKED')
    return result


def binding_at(db, mode, gym_id, instant):
    """Capture only the gym override. Missing stays missing, never shared fallback.

    Called at the original mutation boundary; no version is manufactured later.
    Does not block customer payment/access when commercial configuration is absent.
    """
    if not agreements.available(db): return {'status': 'CONFIGURATION_SCHEMA_MISSING'}
    if agreements.scope(db, mode, None, lock=True) is None:
        return {'status': 'CONFIGURATION_SCOPE_MISSING'}
    selected = agreements.scope(db, mode, gym_id, lock=True)
    row = agreements.active_version(db, selected.id, stored_instant(instant), lock=True) if selected else None
    if not row or KEY not in row.terms: return {'status': 'GYM_CONFIGURATION_MISSING'}
    from app.services.marketplace_calculation import commercial_settings, AllocationBlocked
    try: commercial_settings(row.terms)
    except AllocationBlocked as error: return {'status': error.code}
    return {'status': 'PINNED', 'agreement_version_id': row.id, 'agreement_version': row.version,
        'terms_hash': digest(row.terms), 'selected_at': stored_instant(instant).isoformat(), 'gym_id': gym_id, 'mode': mode}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def lock_root(db, mode):
    root = agreements.scope(db, mode, None, lock=True)
    if root is None:
        raise HTTPException(409, 'Agreement environment scope missing. No configuration was saved.')
    return root


def search_gyms(db, query, limit, offset):
    rows = select(Gym.id, Gym.name).where(Gym.name.contains(query.strip(), autoescape=True))
    total = db.scalar(select(func.count()).select_from(rows.subquery()))
    return {'items': [dict(row) for row in db.execute(rows.order_by(Gym.name, Gym.id).limit(limit).offset(offset)).mappings()], 'total': total}


def configuration(db, mode, gym_id, limit=20, offset=0):
    if mode not in {'test', 'live'}: raise HTTPException(422, 'Invalid payment environment')
    gym = db.get(Gym, gym_id)
    if not gym: raise HTTPException(404, 'Gym not found')
    base = {'gym_id': gym_id, 'gym_name': gym.name, 'mode': mode, 'available': agreements.available(db),
        'posting_enabled': False, 'statutory_reporting_enabled': False, 'processing_blockers': list(BLOCKERS)}
    if not base['available']:
        return {**base, 'reason': 'Financial settings require migration d46e70ba9268.', 'template': None,
            'latest_version': 0, 'effective': None, 'latest': None, 'history': [], 'total': 0, 'legacy_replacement_required': False}
    now = utcnow()
    selected = agreements.scope(db, mode, gym_id)
    last = agreements.latest(db, selected.id) if selected else None
    effective = agreements.resolve(db, mode, gym_id, now)
    rows = select(FinancialAgreementVersion).where(FinancialAgreementVersion.scope_id == selected.id) if selected else None
    history = list(db.scalars(rows.order_by(FinancialAgreementVersion.version.desc()).limit(limit).offset(offset))) if rows is not None else []
    legacy = any(row and row.action == 'AGREEMENT' and KEY not in row.terms for row in (last, effective))
    from app.services.commercial_settlement import readiness as settlement_readiness
    settlement_raw=(last.terms.get(KEY) or {}).get('settlements') if last else None
    base['settlement_readiness']={category:settlement_readiness(settlement_raw,category)
        for category in ('ATTENDED_BOOKING','NO_SHOW','SINGLE_GYM','MULTI_GYM')}
    if any(not item['ready'] for item in base['settlement_readiness'].values()):
        base['processing_blockers'].append('SETTLEMENT_TIMING_NOT_FULLY_CONFIGURED')
    if last and KEY in last.terms:
        from app.services.gym_visit_payouts import monthly_settings
        from app.services.marketplace_calculation import AllocationBlocked
        try: monthly_settings(last.terms)
        except AllocationBlocked: base['processing_blockers'].append('MONTHLY_POLICY_MISSING')
    return {**base, 'latest_version': last.version if last else 0,
        'latest': agreements.present(db, last, now) if last else None,
        'effective': agreements.present(db, effective, now) if effective else None,
        'template': last.terms[KEY] if last and KEY in last.terms else defaults(),
        'legacy_replacement_required': legacy, 'history': [agreements.present(db, row, now) for row in history],
        'total': db.scalar(select(func.count()).select_from(rows.subquery())) if rows is not None else 0}


def create(db, actor_id, payload, key):
    agreements.require_schema(db)
    canonical = payload.model_dump(mode='json')
    # New optional settlement fields must not change hashes of Increment 1/2
    # requests retried after rollout. Unset/null retains the old wire shape.
    original_fields={'booking_cycle','multi_gym_cycle','minimum_payout','admin_approval_required','automatic_transfers'}
    settlement=canonical['settings']['settlements']
    for name in list(settlement):
        if name not in original_fields and settlement[name] is None: settlement.pop(name)
    request_hash = digest(canonical)
    try:
        lock_root(db, payload.mode)
        if not db.get(Gym, payload.gym_id): raise HTTPException(404, 'Gym not found')
        selected = agreements.scope(db, payload.mode, payload.gym_id, lock=True)
        if selected:
            prior = db.scalar(select(FinancialAgreementVersion).where(FinancialAgreementVersion.scope_id == selected.id,
                FinancialAgreementVersion.request_key == key).with_for_update())
            if prior:
                if prior.request_hash != request_hash or prior.actor_id != actor_id:
                    raise HTTPException(409, 'This request key belongs to a different change.')
                result = agreements.present(db, prior); db.commit(); return result
        last = agreements.latest(db, selected.id, lock=True) if selected else None
        if payload.expected_version != (last.version if last else 0):
            raise HTTPException(409, 'Financial settings changed. Reload history before saving.')
        effective = agreements.resolve(db, payload.mode, payload.gym_id, utcnow(), lock=True)
        if payload.expected_effective_version_id != (effective.id if effective else None):
            raise HTTPException(409, 'The effective contract changed. Reload before saving.')
        legacy = any(row and row.action == 'AGREEMENT' and KEY not in row.terms for row in (last, effective))
        if legacy and not payload.acknowledge_legacy_replacement:
            raise HTTPException(409, 'Explicitly acknowledge future replacement of the legacy contract. History and pins remain unchanged.')
        now = stored_instant(utcnow()).replace(microsecond=0)
        starts = stored_instant(payload.effective_from)
        if starts <= now: raise HTTPException(422, 'Effective start must be in the future; backdating is forbidden.')
        if last and starts <= last.effective_from:
            raise HTTPException(409, 'Schedule after the latest version start.')
        if not selected:
            selected = FinancialAgreementScope(mode=payload.mode, scope_key=agreements.scope_key(payload.gym_id), gym_id=payload.gym_id)
            db.add(selected); db.flush()
        row = FinancialAgreementVersion(scope_id=selected.id, version=payload.expected_version + 1,
            effective_from=starts, effective_to=None, terms={KEY: canonical['settings']}, action='AGREEMENT',
            agreement_reference='Gym financial settings', reason=payload.reason, ca_status='PENDING', ca_reference=None,
            actor_id=actor_id, request_key=key, request_hash=request_hash, created_at=now)
        db.add(row); db.flush()
        result = agreements.present(db, row); db.commit(); return result
    except Exception:
        db.rollback()
        raise


def initialize_new_gym(db, gym, actor_id):
    """Only the creation path calls this, before its commit. Never a historical backfill."""
    agreements.require_schema(db)
    now = stored_instant(utcnow()).replace(microsecond=0)
    for mode in ('test', 'live'):
        lock_root(db, mode)
        selected = agreements.scope(db, mode, gym.id, lock=True)
        if selected and agreements.latest(db, selected.id):
            continue  # Caller retry never overwrites an existing contract.
        if not selected:
            selected = FinancialAgreementScope(mode=mode, scope_key=agreements.scope_key(gym.id), gym_id=gym.id)
            db.add(selected); db.flush()
        terms = {KEY: defaults()}
        db.add(FinancialAgreementVersion(scope_id=selected.id, version=1, effective_from=now,
            effective_to=None, terms=terms, action='AGREEMENT', agreement_reference='New gym default configuration v1',
            reason='Independent commercial defaults initialized atomically with new gym creation; processing remains disabled.',
            ca_status='PENDING', ca_reference=None, actor_id=actor_id, request_key=f'new-gym-{gym.id}-{mode}',
            request_hash=digest(terms), created_at=now))
    db.flush()