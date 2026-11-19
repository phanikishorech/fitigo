"""Phase 4A arithmetic; fixtures are explicit approvals, not seeded contracts."""
from copy import deepcopy
from decimal import Decimal, localcontext
import pytest
from pydantic import ValidationError
from app.schemas.marketplace_allocation import MarketplacePolicy, AllocationInput
from app.services.marketplace_calculation import calculate, equal_units, distribute_fee, AllocationBlocked


def terms(**overrides):
    policy = dict(contract_version=1, approval={'status':'APPROVED','reference':'Unit fixture approval'},
        allocation_basis='SOURCE_PRICE_AFTER_DISCOUNTS_EXCLUDING_TAX',price_representation='GROSS_BEFORE_DISCOUNT',
        tax_treatment='EXCLUDE_EVIDENCED_TAX',rounding='HALF_UP',visitor_residual='LOWEST_VISITOR_INDEX',
        fee_split='EQUAL_ACTUAL_INCLUDING_FEE_TAX',fee_residual='FITIGO',fee_before_payout='REQUIRED',
        single_gym_entitlement='UPFRONT_ON_VERIFIED_PURCHASE',fee_distribution='PROPORTIONAL_GATEWAY_FUNDED_VALUE')
    policy.update(overrides)
    return {'marketplace_contract':policy,'attended':{'gym_percent':'85.00','fitigo_percent':'15.00'},
        'single_gym':{'gym_percent':'85.00','fitigo_percent':'15.00'},'no_show':{'gym_percent':'70.00','fitigo_percent':'30.00'}}


def inputs(**overrides):
    data=dict(category='ATTENDED_BOOKING',price_amount='100.00',discount_amount='0.00',tax_amount='0.00',
        wallet_amount='0.00',gateway_amount='100.00',actual_gateway_fee='2.36',fee_tax='0.36',
        fee_basis='INCLUDING_TAX',fee_evidence_reference='immutable-provider-fee')
    data.update(overrides)
    return AllocationInput(**data)


@pytest.mark.parametrize('category,gym,fitigo,timing',[
    ('ATTENDED_BOOKING','85','15','CONFIGURED_SETTLEMENT_CYCLE'),
    ('NO_SHOW','70','30','CONFIGURED_SETTLEMENT_CYCLE'),('SINGLE_GYM','85','15','UPFRONT')])
def test_approved_rates_and_fee_conservation(category,gym,fitigo,timing):
    result=calculate(terms(),inputs(category=category))
    assert result.gym_gross_share==Decimal(gym) and result.fitigo_gross_commission==Decimal(fitigo)
    assert result.gym_gateway_fee_share==result.fitigo_gateway_fee_share==Decimal('1.18')
    assert result.gym_owner_net_entitlement==Decimal(gym)-Decimal('1.18')
    assert result.fitigo_net_commission==Decimal(fitigo)-Decimal('1.18')
    assert result.entitlement_timing==timing and not result.statutory_reporting_enabled


@pytest.mark.parametrize('residual,gym,fitigo',[('FITIGO','0.01','0.02'),('GYM_OWNER','0.02','0.01')])
def test_odd_paise_fee(residual,gym,fitigo):
    result=calculate(terms(fee_residual=residual),inputs(actual_gateway_fee='0.03',fee_tax='0'))
    assert result.gym_gateway_fee_share==Decimal(gym) and result.fitigo_gateway_fee_share==Decimal(fitigo)
    assert result.gym_gateway_fee_share+result.fitigo_gateway_fee_share==Decimal('0.03')


def test_fee_tax_not_added_twice():
    inclusive=calculate(terms(),inputs())
    exclusive=calculate(terms(),inputs(actual_gateway_fee='2',fee_basis='EXCLUDING_TAX'))
    assert inclusive==exclusive


@pytest.mark.parametrize('policy,readiness',[('REQUIRED','FEE_PENDING'),('ALLOW_PROVISIONAL_GROSS','PROVISIONAL_GROSS')])
def test_missing_fee_preserves_gross_not_fake_net(policy,readiness):
    result=calculate(terms(fee_before_payout=policy),inputs(actual_gateway_fee=None,fee_tax=None,fee_evidence_reference=None,fee_basis='UNAVAILABLE'))
    assert result.gym_gross_share==85 and result.fitigo_gross_commission==15
    assert result.gym_owner_net_entitlement is None and result.gateway_fee is None
    assert result.payout_readiness==readiness


def test_wallet_only_zero_fee_without_external_charge():
    result=calculate(terms(),inputs(wallet_amount='100',gateway_amount='0',actual_gateway_fee=None,fee_tax=None,fee_evidence_reference=None))
    assert result.gateway_fee==0 and result.gym_owner_net_entitlement==85
    assert result.fee_status=='WALLET_ONLY_NO_GATEWAY_FEE'


def test_split_funding_does_not_multiply_actual_fee():
    result=calculate(terms(),inputs(wallet_amount='60',gateway_amount='40',actual_gateway_fee='0.94',fee_tax='0.14'))
    assert result.eligible_amount==100 and result.gateway_fee==Decimal('0.94')
    assert result.gym_gateway_fee_share==Decimal('0.47')


def test_wallet_only_with_explicit_provider_fee_keeps_actual():
    with pytest.raises(AllocationBlocked,match='Wallet-only'):
        calculate(terms(),inputs(wallet_amount='100',gateway_amount='0'))


def test_gross_discount_tax_basis_and_already_discounted_do_not_double_discount():
    gross=calculate(terms(),inputs(price_amount='130',discount_amount='12',tax_amount='18',gateway_amount='118'))
    net=calculate(terms(price_representation='ALREADY_DISCOUNTED'),inputs(price_amount='118',discount_amount='12',tax_amount='18',gateway_amount='118'))
    assert gross==net and gross.eligible_amount==100


@pytest.mark.parametrize('field',['tax_amount','discount_amount'])
def test_unknown_discount_or_tax_is_blocked(field):
    with pytest.raises(AllocationBlocked) as exc:calculate(terms(),inputs(**{field:None}))
    assert exc.value.code=='SOURCE_DATA_MISSING'


@pytest.mark.parametrize('amount',[0.1,True,'NaN','Infinity','-1','0.001','10000000000'])
def test_invalid_money_input(amount):
    with pytest.raises(ValidationError):inputs(price_amount=amount)


@pytest.mark.parametrize('updates,code',[
    ({'wallet_amount':'1'},'FUNDING_MISMATCH'),({'tax_amount':'101'},'SOURCE_DATA_INVALID'),
    ({'discount_amount':'101'},'SOURCE_DATA_INVALID'),({'fee_evidence_reference':None},'SOURCE_DATA_MISSING'),
    ({'fee_tax':'3'},'SOURCE_DATA_INVALID')])
def test_bad_evidence_rejected(updates,code):
    with pytest.raises(AllocationBlocked) as exc:calculate(terms(),inputs(**updates))
    assert exc.value.code==code


def test_incomplete_fee_tax_is_pending():
    result=calculate(terms(),inputs(fee_basis='EXCLUDING_TAX',fee_tax=None))
    assert result.gateway_fee is None and result.fee_status=='PENDING_EVIDENCE'


def test_negative_net_not_clamped_or_available():
    result=calculate(terms(),inputs(actual_gateway_fee='40',fee_tax='0'))
    assert result.fitigo_net_commission==-5 and result.payout_readiness=='NEGATIVE_NET_REVIEW'


def test_agreement_history_not_repriced():
    original=terms();original['attended']['gym_percent']='80';original['attended']['fitigo_percent']='20'
    saved=deepcopy(original)
    result=calculate(original,inputs())
    assert result.gym_gross_share==80 and saved==original


def test_unknown_commercial_policies_have_no_defaults():
    blank=MarketplacePolicy()
    assert blank.rounding is None and blank.allocation_basis is None and blank.fee_before_payout is None
    with pytest.raises(AllocationBlocked):calculate({},inputs())
    with pytest.raises(ValidationError):MarketplacePolicy(approval={'status':'APPROVED','reference':'No policies'})


def test_multi_gym_leftover_formula_is_not_supported():
    with pytest.raises(ValidationError):inputs(category='MULTI_GYM')


@pytest.mark.parametrize('count',[1,2,3,17,100])
def test_visitor_partition_conserves_every_paise(count):
    for amount in ('0.00','0.01','0.03','1.00','100.01','9999999999.99'):
        for method in ('LOWEST_VISITOR_INDEX','FINAL_VISITOR'):
            parts=equal_units(Decimal(amount),count,method)
            assert sum(parts)==Decimal(amount) and len(parts)==count
            assert all(v>=0 for v in parts)


def test_partial_group_uses_purchased_not_attended_count():
    parts=equal_units(Decimal('100'),3,'LOWEST_VISITOR_INDEX')
    assert parts==(Decimal('33.34'),Decimal('33.33'),Decimal('33.33'))
    assert sum(parts[i] for i in (0,2))==Decimal('66.67')
    with pytest.raises(AllocationBlocked):equal_units(Decimal('100'),3,'REQUIRE_EXACT')


def test_fee_distribution_ignores_wallet_weights_and_conserves_total():
    parts=distribute_fee(Decimal('0.05'),[Decimal('0'),Decimal('50'),Decimal('50')])
    assert parts==(Decimal('0'),Decimal('0.03'),Decimal('0.02'))
    with pytest.raises(AllocationBlocked):distribute_fee(Decimal('1'),[Decimal('0')])


def test_decimal_calculation_does_not_depend_on_global_precision():
    with localcontext() as ctx:
        ctx.prec=6
        result=calculate(terms(),inputs(price_amount='9999999999.99',gateway_amount='9999999999.99'))
        assert result.gym_gross_share==Decimal('8499999999.99')
        assert equal_units(Decimal('9999999999.99'),3,'LOWEST_VISITOR_INDEX')[0]==Decimal('3333333333.33')


def test_new_approved_contract_rejects_conflicting_rates_without_rewriting_legacy():
    from app.schemas.financial_agreement import AgreementTerms
    from test_financial_agreements import payload
    data=payload()['terms'];data['attended']={'gym_percent':'80','fitigo_percent':'20'}
    assert AgreementTerms.model_validate(data).attended.gym_percent==80
    data['marketplace_contract']=terms()['marketplace_contract']
    assert AgreementTerms.model_validate(data).attended.gym_percent==80


def test_visit_approval_rejects_unconfigured_rate_limits():
    from app.schemas.financial_agreement import AgreementTerms
    from test_financial_agreements import payload
    data=payload()['terms'];data['visit_payout_contract']={'approval':{'status':'APPROVED','reference':'Explicit visit fixture'},
        'period_timezone':'Asia/Kolkata','platform_cap_mode':'NOT_APPLICABLE','cap_exhaustion':'REJECT_WHOLE_VISIT',
        'cap_order':'SERIALIZED_PROCESSING_ORDER','fee_readiness':'HOLD_PAYOUT_PENDING_FEE_DISTRIBUTION'}
    with pytest.raises(ValidationError):AgreementTerms.model_validate(data)