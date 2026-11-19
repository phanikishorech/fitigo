from datetime import datetime, timezone
import pytest
from pydantic import ValidationError
from app.schemas.gateway_evidence import GatewaySettlementEvidence


def body():
    return dict(provider='CASHFREE',environment='test',provider_settlement_id='settlement-fixture',currency='INR',
        verified_at=datetime.now(timezone.utc),verification_source='AUTHENTICATED_PROVIDER_FETCH',evidence_reference='Provider export reference')


def test_unavailable_fee_and_settlement_are_null_not_zero():
    value=GatewaySettlementEvidence(**body())
    assert value.actual_settlement_amount is None and value.gateway_fee is None and value.settled_at is None
    assert value.reconciliation_status=='UNRECONCILED'


@pytest.mark.parametrize('updates',[{'gateway_fee':'1.00'}, {'actual_settlement_amount':0.1},
    {'actual_settlement_amount':'NaN'}, {'gateway_fee_tax':'-1'}, {'settled_at':'2026-11-12T12:00:00'}])
def test_invalid_gateway_contract_rejected(updates):
    with pytest.raises(ValidationError):GatewaySettlementEvidence(**{**body(),**updates})