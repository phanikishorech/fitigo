from copy import deepcopy
from decimal import Decimal
import pytest
from pydantic import ValidationError
from app.schemas.gym_financial_settings import GymFinancialSettings, SettingsCreate
from app.services.gym_financial_settings import defaults


def test_independent_defaults_and_no_invented_policies():
    first, second = defaults(), defaults()
    assert first['individual']['revenue'] == {'gym_percent': '85', 'fitigo_percent': '15'}
    assert first['single_gym'] == first['individual']
    assert first['no_show']['revenue'] == {'gym_percent': '70', 'fitigo_percent': '30'}
    for category in ('individual', 'single_gym', 'no_show'):
        assert first[category]['gateway_fee'] == {'gym_percent': '50', 'fitigo_percent': '50'}
    monthly = first['multi_gym']
    assert Decimal(monthly['reference_amount']) / monthly['reference_visits'] == 30
    assert monthly['gateway_fee'] == {'gym_percent': '0', 'fitigo_percent': '100'}
    assert monthly['fitigo_earnings'] == 'NOT_APPROVED'
    assert monthly['period_timezone']=='Asia/Kolkata'
    assert monthly['rounding']=='MONTHLY_TOTAL_HALF_UP'
    assert monthly['version_boundary']=='PIN_AT_ADMISSION'
    assert monthly['purchase_fee_attribution']=='MEMBERSHIP_COMPLETE_EQUAL_VISITS'
    assert monthly['invalidated_visit_correction']=='APPEND_ONLY_SOURCE_BACKED'
    assert not any('cap' in key for key in monthly)
    assert first['settlements']['minimum_payout'] is None
    assert first['settlements']['booking_cycle'] is None
    first['individual']['revenue']['gym_percent'] = '1'
    assert second == defaults()
    assert first['single_gym']['revenue']['gym_percent'] == '85'


@pytest.mark.parametrize('path,value', [
    (('individual', 'revenue', 'gym_percent'), '85.001'),
    (('single_gym', 'gateway_fee', 'gym_percent'), '-1'),
    (('no_show', 'gateway_fee', 'fitigo_percent'), '49'),
    (('multi_gym', 'reference_visits'), 0),
    (('multi_gym', 'reference_visits'), True),
    (('multi_gym', 'reference_visits'), 1.5),
    (('multi_gym', 'reference_amount'), 'NaN'),
    (('multi_gym', 'reference_amount'), '1.001'),
    (('multi_gym', 'rounding'), 'HALF_UP'),
    (('multi_gym', 'payout_cap'), '500'),
    (('settlements', 'automatic_transfers'), True),
    (('settlements', 'minimum_payout'), '-1'),
    (('no_show_eligibility',), 'UNSCANNED_QR'),
])
def test_invalid_settings_rejected(path, value):
    data = deepcopy(defaults()); target = data
    for key in path[:-1]: target = target[key]
    target[path[-1]] = value
    with pytest.raises(ValidationError): GymFinancialSettings.model_validate(data)


def test_custom_percentages_and_independent_fee_responsibility():
    data = defaults()
    data['individual']['revenue'] = {'gym_percent': '80.25', 'fitigo_percent': '19.75'}
    data['single_gym']['gateway_fee'] = {'gym_percent': '100', 'fitigo_percent': '0'}
    data['multi_gym']['gateway_fee'] = {'gym_percent': '12.50', 'fitigo_percent': '87.50'}
    parsed = GymFinancialSettings.model_validate(data)
    assert parsed.individual.revenue.gym_percent == Decimal('80.25')
    assert parsed.no_show.gateway_fee.gym_percent == 50
    assert parsed.multi_gym.gateway_fee.gym_percent == Decimal('12.50')


def test_consolidated_configuration_never_advertises_posting_readiness():
    from app.services.accounting_policy import policy_readiness
    result = policy_readiness({'financial_settings': defaults()})
    assert result['posting_eligible'] is False
    assert result['status'] == 'NOT_CONFIGURED'
    assert 'Consolidated gym settings' in result['reason']


@pytest.mark.parametrize('change', [
    {'effective_from': '2030-01-01T00:00:00'}, {'effective_from': '2030-01-01T00:00:00.000001Z'},
    {'gym_id': None}, {'expected_version': True}, {'mode': 'mixed'},
    {'reason': ' '}, {'acknowledge_configuration_only': False}, {'acknowledge_configuration_only': 'true'},
])
def test_invalid_metadata_rejected(change):
    data = dict(mode='test', gym_id=1, expected_version=0, expected_effective_version_id=None,
        effective_from='2030-01-01T00:00:00Z', settings=defaults(), reason='Initial configuration', acknowledge_configuration_only=True)
    with pytest.raises(ValidationError): SettingsCreate(**{**data, **change})