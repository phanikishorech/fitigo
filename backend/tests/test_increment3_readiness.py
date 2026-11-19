from types import SimpleNamespace
from decimal import Decimal
from datetime import datetime,timezone,timedelta
import pytest
from pydantic import ValidationError
from app.schemas.gym_financial_settings import SettlementSettings
from app.services.financial_readiness import tax_readiness
from app.services.marketplace_allocations import digest
from app.services.commercial_settlement import readiness,policy_for,due_at
from app.services.marketplace_calculation import AllocationBlocked
from app.models.marketplace_allocation import MarketplaceAllocation


def settlement():
    return dict(booking_cycle='WEEKLY',multi_gym_cycle='MONTHLY',single_gym_cycle='UPFRONT',minimum_payout='1',
        cutoff_time='12:00:00',timezone='Asia/Kolkata',weekly_cutoff_day=0,monthly_cutoff_day=1,
        short_month='LAST_CALENDAR_DAY',holding_days=2,eligible_deductions=[],payout_eligibility='VERIFIED_NET_SOURCE_UNDISPUTED',
        partial_settlement='FULL_ENTITLEMENT_ONLY',failed_settlement='REMAIN_OUTSTANDING_REQUIRE_EVIDENCE')


@pytest.mark.parametrize('tax,status',[(None,'UNKNOWN'),('0.00','CONFIRMED_ZERO'),('18.00','CONFIRMED_NONZERO'),('NaN','UNKNOWN')])
def test_tax_states_are_not_fee_tax(tax,status):
    payload={'fee_tax_amount':'10.00','transaction_basis':{'price_amount':'118','discount_amount':'0','tax_amount':tax,'currency':'INR','price_representation':'GROSS_BEFORE_DISCOUNT'}}
    row=SimpleNamespace(id='source',payload=payload,payload_hash=digest(payload),evidence_status='VERIFIED_SOURCE')
    result=tax_readiness(row)
    assert result['status']==status
    assert bool(result['blockers'])==(tax in (None,'NaN'))


def test_tax_missing_conflicting_or_corrupt_blocks():
    assert tax_readiness(None)['tax_amount'] is None
    payload={'transaction_basis':{'tax_amount':'0','tax_status':'SOURCE_NOT_SUPPORTED'}}
    source=SimpleNamespace(id='s',payload=payload,payload_hash=digest(payload),evidence_status='VERIFIED_SOURCE')
    assert tax_readiness(source)['status']=='INVALID'
    source.payload_hash='bad'
    assert tax_readiness(source)['blockers']==['PURCHASE_EVIDENCE_INVALID']


@pytest.mark.parametrize('category',['ATTENDED_BOOKING','NO_SHOW','SINGLE_GYM','MULTI_GYM'])
def test_settlement_has_no_unapproved_defaults(category):
    assert not readiness({},category)['ready']
    with pytest.raises(AllocationBlocked):policy_for({'financial_settings':{'settlements':{}}},category)
    assert readiness(settlement(),category)['ready']


@pytest.mark.parametrize('changes',[{'holding_days':True},{'holding_days':-1},{'cutoff_time':'25:00:00'},
    {'eligible_deductions':['ACTUAL_GATEWAY_FEES']},{'eligible_deductions':['ACTUAL_TAX_WITHHOLDING']*2},{'automatic_transfers':True}])
def test_invalid_settlement_rejected(changes):
    with pytest.raises(ValidationError):SettlementSettings(**{**settlement(),**changes})


def test_upfront_entitlement_has_explicit_holding_period():
    stamp=datetime(2026,11,12,9,tzinfo=timezone.utc)
    row=MarketplaceAllocation(category='SINGLE_GYM',occurred_at=stamp)
    assert due_at(row,{},SettlementSettings(**settlement()))==stamp+timedelta(days=2)


def test_single_weekly_settlement_does_not_use_legacy_upfront_bypass():
    row=MarketplaceAllocation(category='SINGLE_GYM',occurred_at=datetime(2026,11,12,9,tzinfo=timezone.utc))
    policy=SettlementSettings(**{**settlement(),'single_gym_cycle':'WEEKLY'})
    due=due_at(row,{},policy)
    assert due.date().isoformat()=='2026-11-18'