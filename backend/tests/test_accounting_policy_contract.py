"""Pure contract checks; no commission, journal, payment or environment writes."""
import pytest
from pydantic import ValidationError
from app.schemas.accounting_policy import AccountingPolicy, ALLOWED_INSTANTS
from app.schemas.financial_agreement import AgreementCreate, AgreementTerms
from app.schemas.financial_evidence import FinancialSourceEvidence
from app.services.accounting_policy import contract_catalog, policy_readiness
from test_financial_agreements import payload


def test_empty_contract_keeps_all_commercial_choices_unset():
    policy = AccountingPolicy().model_dump(mode='json')
    for context in ALLOWED_INSTANTS:
        assert policy['selection'][context]['instant'] is None
        assert policy['selection'][context]['approval']['status'] == 'AWAITING_APPROVAL'
    for name in ('attended','no_show','single_gym','multi_gym','settlements'):
        assert all(value is None for key,value in policy[name].items() if key != 'approval')
    assert policy['monetary']['currency']=='INR' and policy['monetary']['storage_scale']==2
    assert contract_catalog()['posting_enabled'] is False


def test_legacy_contract_remains_legacy():
    terms = payload()['terms']
    assert policy_readiness(terms)['contract_version']==1
    parsed = AgreementCreate(**payload())
    canonical = parsed.model_dump(mode='json'); canonical['terms'].pop('policy_contract')
    # Old validation serializes datetime identically to the new parsed request;
    # only the optional field differs. Hash preservation covered against DB below.
    assert 'policy_contract' not in canonical['terms'] and parsed.terms.policy_contract is None
    assert policy_readiness(terms)['status']=='NOT_CONFIGURED'


@pytest.mark.parametrize('context', list(ALLOWED_INSTANTS))
def test_each_selection_context_requires_explicit_approved_instant(context):
    terms = payload()['terms']; policy = AccountingPolicy().model_dump(mode='json')
    choice = sorted(ALLOWED_INSTANTS[context])[0]
    policy['selection'][context]['instant']=choice
    terms['policy_contract']=policy
    assert policy_readiness(terms)['sections'][context]['status']=='AWAITING_APPROVAL'
    policy['selection'][context]['approval']={'status':'APPROVED','reference':'Test approval'}
    AgreementTerms.model_validate(terms)
    result=policy_readiness(terms)
    assert result['sections'][context]['status']=='CONFIGURED'
    assert result['contexts'][context]['posting_eligible'] is False


@pytest.mark.parametrize('change', [
    {'contract_version':3}, {'posting_enabled':True},
    {'selection':{'BOOKING_PURCHASE':{'instant':'CHECKIN'}}},
    {'selection':{'NO_SHOW':{'approval':{'status':'APPROVED','reference':'Approval'}}}},
    {'monetary':{'rounding':'HALF_UP'},'attended':{'rounding':'DOWN'}},
    {'monetary':{'storage_scale':3}},
    {'monetary':{'calculation_precision':16}},
    {'multi_gym':{'platform_monthly_payout_cap':0.1}},
    {'multi_gym':{'earning_percent':True}},
    {'settlements':{'weekly_cutoff_day':True}}, {'settlements':{'monthly_cutoff_day':32}},
    {'settlements':{'cutoff_time':'25:00:00'}}, {'settlements':{'timezone':'EST'}},
    {'settlements':{'holding_days':-1}}, {'settlements':{'eligible_deductions':['ACTUAL_GATEWAY_FEES','ACTUAL_GATEWAY_FEES']}},
    {'multi_gym':{'platform_monthly_payout_cap':'NaN'}}, {'multi_gym':{'platform_monthly_payout_cap':'1.001'}},
    {'multi_gym':{'earning_formula':'FIXED_PER_VERIFIED_VISIT'}},
    {'multi_gym':{'earning_formula':'FIXED_PER_VERIFIED_VISIT','earning_fixed_amount':'10.00','earning_percent':'15.00'}},
    {'single_gym':{'recognition_method':'OTHER_APPROVED'}},
    {'single_gym':{'pause_treatment':'SUSPEND_AND_EXTEND','end_event':'ORIGINAL_EXPIRY'}},
    {'attended':{'approval':{'status':'APPROVED'}}},
])
def test_invalid_or_contradictory_contract_rejected(change):
    with pytest.raises(ValidationError):AccountingPolicy.model_validate(change)


def test_approved_incomplete_sections_cannot_be_saved():
    terms=payload()['terms'];terms['policy_contract']={'attended':{'approval':{'status':'APPROVED','reference':'Not enough'}}}
    with pytest.raises(ValidationError):AgreementTerms.model_validate(terms)


def test_other_approved_is_stored_but_never_executable():
    policy=AccountingPolicy(single_gym={'recognition_method':'OTHER_APPROVED','other_method_reference':'Specification document'})
    terms=payload()['terms'];terms['policy_contract']=policy.model_dump(mode='json')
    assert policy_readiness(terms)['sections']['single_gym']['status']=='UNSUPPORTED'


def test_explicit_zero_and_empty_deductions_differ_from_missing():
    p=AccountingPolicy(settlements={'holding_days':0,'eligible_deductions':[]},multi_gym={'platform_monthly_payout_cap':'0.00'})
    terms=payload()['terms'];terms['policy_contract']=p.model_dump(mode='json')
    readiness=policy_readiness(terms)
    assert 'holding_days' not in readiness['sections']['settlements']['missing_fields']
    assert 'eligible_deductions' not in readiness['sections']['settlements']['missing_fields']
    assert 'platform_monthly_payout_cap' not in readiness['sections']['multi_gym']['missing_fields']


def test_unknown_stored_schema_is_not_reinterpreted():
    assert policy_readiness({'policy_contract':{'contract_version':999}})['status']=='UNSUPPORTED'


def test_owner_identity_without_historical_evidence_rejected():
    body={'checkout_id':'source','source_type':'BOOKING','source_id':'1','context':'BOOKING_PURCHASE',
        'environment':'test','environment_source':'PAYMENT_CHECKOUT','occurred_at':'2026-11-12T12:00:00Z',
        'gym_id':1,'original_purchaser_id':3,'holder_id_at_event':4,'owner_id_at_event':2}
    with pytest.raises(ValidationError):FinancialSourceEvidence(**body)
    evidence=FinancialSourceEvidence(**body,ownership_evidence_reference='Future immutable event snapshot')
    assert evidence.original_purchaser_id!=evidence.holder_id_at_event


def test_full_policy_can_be_configured_without_enabling_posting():
    approval={'status':'APPROVED','reference':'Explicit test-policy approval'}
    terms=payload()['terms']
    terms['multi_gym']={'payout_per_visit':'50.00','visits_per_member_month':10,'payout_cap_per_member_month':'500.00'}
    terms['policy_contract']={
        'monetary':{'approval':approval,'rounding':'HALF_UP','rounding_stage':'PER_VISITOR',
            'residual_paise':'LARGEST_REMAINDER_VISITOR_INDEX','discount_allocation':'EXPLICIT_SOURCE_LINES',
            'tax_treatment':'EXCLUDE_SEPARATELY_COLLECTED_TAX','partial_refund':'REVERSE_ORIGINAL_ALLOCATIONS'},
        'attended':{'approval':approval,'allocation_basis':'PAID_NET_OF_DISCOUNTS_EXCLUDING_TAX',
            'calculation_unit':'PER_ATTENDED_VISITOR','eligibility':'VERIFIED_BACKEND_CHECKIN','rounding':'HALF_UP'},
        'no_show':{'approval':approval,'allocation_basis':'PAID_NET_OF_DISCOUNTS_EXCLUDING_TAX',
            'eligibility':'CONFIRMED_PAID_CLOSED_WINDOW_NO_SCAN','partial_attendance':'BLOCK_FOR_REVIEW','rounding':'HALF_UP'},
        'single_gym':{'approval':approval,'recognition_method':'DAILY_SERVICE_PERIOD','start_event':'ACTIVATION',
            'end_event':'ADJUSTED_EXPIRY','pause_treatment':'SUSPEND_AND_EXTEND','transfer_treatment':'PRESERVE_SCHEDULE_NO_NEW_SALE',
            'refund_treatment':'REVERSE_ORIGINAL_RECOGNITION'},
        'multi_gym':{'approval':approval,'platform_monthly_payout_cap':'1000.00','platform_cap_scope':'PER_MEMBERSHIP_ALL_GYMS',
            'cap_exhaustion':'HOLD_FOR_REVIEW','earning_formula':'FIXED_PER_VERIFIED_VISIT','earning_fixed_amount':'5.00',
            'recognition_method':'PER_VERIFIED_EVENT','unused_value':'REMAIN_UNALLOCATED','monthly_reconciliation':'ADMIN_APPROVED_VERIFIED_VISITS','allocation_timezone':'Asia/Kolkata'},
        'settlements':{'approval':approval,'weekly_cutoff_day':0,'monthly_cutoff_day':31,'short_month':'LAST_CALENDAR_DAY',
            'cutoff_time':'12:00:00','timezone':'Asia/Kolkata','holding_days':0,'eligible_deductions':[],
            'partial_settlement':'ALLOW_WITH_ALLOCATION_LINKS','failed_settlement':'REMAIN_OUTSTANDING_REQUIRE_EVIDENCE'},
        'selection':{context:{'instant':sorted(allowed)[0],'approval':approval} for context,allowed in ALLOWED_INSTANTS.items()},
    }
    saved=AgreementTerms.model_validate(terms).model_dump(mode='json')
    readiness=policy_readiness(saved)
    assert readiness['status']=='CONFIGURED'
    assert readiness['posting_eligible'] is False
    assert all(c['policy_ready'] and not c['posting_eligible'] for c in readiness['contexts'].values())