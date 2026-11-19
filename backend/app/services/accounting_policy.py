"""Policy completeness != approval != evidence eligibility != posting availability."""
from pydantic import ValidationError
from app.schemas.accounting_policy import AccountingPolicy, ALLOWED_INSTANTS


def contract_catalog():
    from app.services.financial_evidence_contract import EVIDENCE_CONTRACT
    from app.schemas.marketplace_allocation import MarketplacePolicy, VisitPayoutPolicy
    return {'schema': AccountingPolicy.model_json_schema(),
        'marketplace_schema': MarketplacePolicy.model_json_schema(),
        'marketplace_empty': MarketplacePolicy().model_dump(mode='json'),
        'visit_schema': VisitPayoutPolicy.model_json_schema(),
        'visit_empty': VisitPayoutPolicy().model_dump(mode='json'),
        'evidence': EVIDENCE_CONTRACT,
        'empty': AccountingPolicy().model_dump(mode='json'),
        'selection_instants': {k: sorted(v) for k, v in ALLOWED_INSTANTS.items()},
        'posting_enabled': False, 'statutory_reporting_enabled': False}


def policy_readiness(terms):
    if (terms or {}).get('financial_settings') is not None:
        return {'contract_version': 1, 'status': 'NOT_CONFIGURED', 'posting_eligible': False,
            'reason': 'Consolidated gym settings use the operational commercial calculator, not statutory recognition. Source evidence, completed monthly attribution and settlement readiness remain independent requirements.', 'sections': {}}
    raw = (terms or {}).get('policy_contract')
    if raw is None:
        return {'contract_version': 1, 'status': 'NOT_CONFIGURED', 'posting_eligible': False,
            'reason': 'Legacy terms have no Phase 2 policy contract. Create a new version; history is not upgraded in place.', 'sections': {}}
    try: policy = AccountingPolicy.model_validate(raw)
    except ValidationError:
        return {'contract_version': None, 'status': 'UNSUPPORTED', 'posting_eligible': False,
            'reason': 'Stored policy contract is invalid or its version is unsupported. Historical data was not modified.', 'sections': {}}
    data = policy.model_dump(mode='json')
    sections = {}
    required = {
        'monetary': ['rounding', 'rounding_stage', 'residual_paise', 'discount_allocation', 'tax_treatment', 'partial_refund'],
        'attended': ['allocation_basis', 'calculation_unit', 'eligibility', 'rounding'],
        'no_show': ['allocation_basis', 'eligibility', 'partial_attendance', 'rounding'],
        'single_gym': ['recognition_method', 'start_event', 'end_event', 'pause_treatment', 'transfer_treatment', 'refund_treatment'],
        'multi_gym': ['platform_monthly_payout_cap', 'platform_cap_scope', 'cap_exhaustion', 'earning_formula', 'recognition_method', 'unused_value', 'monthly_reconciliation', 'allocation_timezone'],
        'settlements': ['cutoff_time', 'timezone', 'holding_days', 'eligible_deductions', 'partial_settlement', 'failed_settlement'],
    }
    cycles = (terms.get('settlements') or {})
    if 'WEEKLY' in (cycles.get('booking_cycle'), cycles.get('multi_gym_cycle')): required['settlements'].append('weekly_cutoff_day')
    if 'MONTHLY' in (cycles.get('booking_cycle'), cycles.get('multi_gym_cycle')): required['settlements'].extend(['monthly_cutoff_day', 'short_month'])
    for name, fields in required.items():
        section = data[name]
        gaps = [field for field in fields if section.get(field) is None]
        if name == 'multi_gym':
            gaps += ['terms.multi_gym.'+field for field in ('payout_per_visit', 'visits_per_member_month', 'payout_cap_per_member_month') if (terms.get('multi_gym') or {}).get(field) is None]
        unsupported = any(value == 'OTHER_APPROVED' for value in section.values() if isinstance(value, str))
        status = 'UNSUPPORTED' if unsupported else 'NOT_CONFIGURED' if gaps else 'AWAITING_APPROVAL' if section['approval']['status'] != 'APPROVED' else 'CONFIGURED'
        sections[name] = {'status': status, 'missing_fields': gaps, 'policy_complete': not gaps,
            'posting_eligible': False, 'posting_blockers': ['CALCULATION_NOT_IMPLEMENTED', 'SOURCE_EVIDENCE_NOT_EVALUATED'],
            'reason': 'Custom methods are stored for review, not executable.' if unsupported else 'Phase 2 stores policy only; no posting engine is enabled.'}
    for context, rule in data['selection'].items():
        sections[context] = {'status': 'NOT_CONFIGURED' if rule['instant'] is None else 'AWAITING_APPROVAL' if rule['approval']['status'] != 'APPROVED' else 'CONFIGURED',
            'missing_fields': ['instant'] if rule['instant'] is None else [], 'posting_eligible': False,
            'reason': 'A source-backed timestamp and approved selection rule are required; no implicit latest-version selection.'}
    dependencies = {'BOOKING_PURCHASE': ['monetary'], 'BOOKING_ATTENDANCE': ['monetary', 'attended'],
        'NO_SHOW': ['monetary', 'no_show'], 'MEMBERSHIP_PURCHASE': ['monetary', 'single_gym'],
        'MEMBERSHIP_ACTIVATION': ['monetary', 'single_gym'], 'MEMBERSHIP_RECOGNITION': ['monetary', 'single_gym'],
        'MULTI_GYM_VISIT': ['monetary', 'multi_gym']}
    contexts = {context: {'policy_ready': all(sections[k]['status']=='CONFIGURED' for k in [context, *needs]),
        'blocked_policies': [k for k in [context, *needs] if sections[k]['status'] != 'CONFIGURED'],
        'posting_eligible': False, 'posting_status': 'CALCULATION_NOT_IMPLEMENTED'} for context, needs in dependencies.items()}
    # Purchase/activation/recognition contexts exist for both membership types.
    # Never advertise a Multi-Gym policy as ready solely because Single-Gym is.
    for context in ('MEMBERSHIP_PURCHASE', 'MEMBERSHIP_ACTIVATION', 'MEMBERSHIP_RECOGNITION'):
        required_sections = [context, 'monetary', 'single_gym', 'multi_gym']
        contexts[context].update(policy_ready=all(sections[k]['status']=='CONFIGURED' for k in required_sections),
            blocked_policies=[k for k in required_sections if sections[k]['status']!='CONFIGURED'])
    return {'contract_version': 2, 'contexts': contexts, 'status': 'CONFIGURED' if all(s['status']=='CONFIGURED' for s in sections.values()) else
        'UNSUPPORTED' if any(s['status']=='UNSUPPORTED' for s in sections.values()) else
        'NOT_CONFIGURED' if any(s['status']=='NOT_CONFIGURED' for s in sections.values()) else 'AWAITING_APPROVAL',
        'sections': sections, 'posting_eligible': False, 'reason': 'Policy contract only. Posting and statutory reporting remain disabled.'}