from decimal import Decimal, localcontext
import pytest
from app.services.gym_financial_settings import defaults
from app.services.marketplace_calculation import calculate, monthly_visit_amounts, AllocationBlocked
from test_marketplace_calculation import inputs


@pytest.mark.parametrize('category,key,owner,fee_owner',[
    ('ATTENDED_BOOKING','individual','80','25'),('SINGLE_GYM','single_gym','92','100'),('NO_SHOW','no_show','60','0')])
def test_independent_configured_revenue_and_fees(category,key,owner,fee_owner):
    settings=defaults()
    settings[key]['revenue']={'gym_percent':owner,'fitigo_percent':str(100-Decimal(owner))}
    settings[key]['gateway_fee']={'gym_percent':fee_owner,'fitigo_percent':str(100-Decimal(fee_owner))}
    row=calculate({'financial_settings':settings},inputs(category=category,actual_gateway_fee='2.00',fee_tax='0'))
    assert row.gym_gross_share==Decimal(owner)
    assert row.gym_gateway_fee_share==Decimal(fee_owner)*Decimal('.02')
    assert row.gym_gateway_fee_share+row.fitigo_gateway_fee_share==2
    assert row.gym_owner_net_entitlement==row.gym_gross_share-row.gym_gateway_fee_share


@pytest.mark.parametrize('count,total',[(50,1500),(100,3000),(160,4800),(200,6000)])
def test_uncapped_monthly_examples(count,total):
    gross,parts=monthly_visit_amounts([(Decimal('3000'),100)]*count)
    assert gross==total and sum(parts)==total and all(p==30 for p in parts)


def test_monthly_round_once_mixed_version_and_deterministic_paise():
    gross,parts=monthly_visit_amounts([(Decimal('1'),3)]*3)
    assert gross==1 and parts==(Decimal('.34'),Decimal('.33'),Decimal('.33'))
    assert monthly_visit_amounts([(Decimal('3000'),100)]*50+[(Decimal('4000'),100)]*50)[0]==3500


def test_monthly_rational_rounding_independent_of_global_precision():
    with localcontext() as ctx:
        ctx.prec=6
        gross,parts=monthly_visit_amounts([(Decimal('100.01'),7)]*7)
    assert gross==Decimal('100.01') and sum(parts)==gross


def test_missing_configuration_and_evidence_remain_unknown():
    with pytest.raises(AllocationBlocked):calculate({'financial_settings':{}},inputs())
    raw=defaults();raw.pop('individual')
    with pytest.raises(AllocationBlocked):calculate({'financial_settings':raw},inputs())
    row=calculate({'financial_settings':defaults()},inputs(actual_gateway_fee=None,fee_tax=None,fee_evidence_reference=None))
    assert row.gym_owner_net_entitlement is None and row.gym_gross_share==85
    with pytest.raises(AllocationBlocked):calculate({'financial_settings':defaults()},inputs(tax_amount=None))