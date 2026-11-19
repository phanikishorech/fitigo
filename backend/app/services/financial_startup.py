"""Fail-closed deployment checks. Validation never starts a worker or changes flags."""
from sqlalchemy import inspect


def validate_configuration(settings,engine):
    evidence=settings.source_evidence_enabled
    allocation=settings.marketplace_allocations_enabled
    live=settings.marketplace_live_allocations_enabled
    payouts=settings.marketplace_payouts_enabled
    if not any((evidence,allocation,live,payouts)):return
    if allocation and not evidence:raise RuntimeError('Financial allocations require source evidence capture; no activation performed.')
    if live and not allocation:raise RuntimeError('Live allocation gate requires the allocation gate; no activation performed.')
    if payouts and not allocation:raise RuntimeError('Payout workflow requires allocation readiness; no activation performed.')
    if engine is None:raise RuntimeError('Enabled financial capabilities require a migrated database.')
    required={'financial_agreement_scopes','financial_agreement_versions','financial_agreement_pins',
        'financial_source_evidence','financial_source_outbox','gym_owner_evidence','checkout_funding','booking_funding'}
    if allocation or payouts:
        required.update({'marketplace_allocations','gym_visit_payouts','gym_monthly_calculations','membership_visit_fees',
            'owner_payouts','owner_payout_items','owner_payout_audit','financial_review_events'})
    missing=required-set(inspect(engine).get_table_names())
    if missing:raise RuntimeError('Enabled financial capabilities require missing migrations: '+', '.join(sorted(missing)))


def validate_worker_request(settings,mode,authorization_reference,*,allocations):
    if not isinstance(authorization_reference,str) or len(authorization_reference.strip())<8:
        raise ValueError('An explicit deployment authorization reference is required to run a financial worker.')
    if mode not in {'test','live'}:raise ValueError('Explicit worker environment required.')
    if not settings.source_evidence_enabled:raise ValueError('Source evidence processing is disabled.')
    if allocations and not settings.marketplace_allocations_enabled:raise ValueError('Allocation processing is disabled.')
    if mode=='live' and not settings.marketplace_live_allocations_enabled:
        raise ValueError('Live workers require separate live-processing approval.')