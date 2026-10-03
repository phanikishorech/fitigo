"""Owner plan + customer wallet purchase regression, isolated from application DB."""
from decimal import Decimal
from sqlalchemy.orm import Session
from test_membership_wallet_mvp import funded
from test_platform_memberships import api
from app.models.wallet import WalletAccount


def test_owner_can_create_plan_and_customer_can_purchase_and_list_memberships(funded):
    client, headers, engine = funded
    created = client.post('/api/v1/memberships/gyms/1/plans', headers=headers[2], json={
        'name':'Owner created plan', 'duration_days':30, 'price':'999.00', 'currency':'INR',
    })
    assert created.status_code == 200, created.text
    plan_id = created.json()['id']
    quote = client.get(f'/api/v1/memberships/gyms/1/plans/{plan_id}/wallet-quote',headers=headers[1]).json()
    purchase = client.post('/api/v1/memberships/gyms/1/purchase', headers={**headers[1], 'Idempotency-Key':'owner-plan-wallet-001'}, json={
        'plan_id':plan_id, 'accepted_quote':quote['quote_token'],
    })
    assert purchase.status_code == 200, purchase.text
    assert purchase.json()['payment_provider'] == 'WALLET'
    assert purchase.json()['wallet_transaction_id'] is not None
    listed = client.get('/api/v1/memberships/me',headers=headers[1])
    assert listed.status_code == 200 and len(listed.json()) == 1
    with Session(engine) as db:
        assert db.get(WalletAccount,1).balance == Decimal('4001.00')