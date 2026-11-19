from decimal import Decimal
from sqlalchemy import select,func
from sqlalchemy.orm import Session
from app.core.config import settings
from app.models.source_evidence import SourceEvidence
from app.models.checkout_funding import CheckoutFunding,BookingFunding
from app.models.payment_checkout import PaymentCheckout
from app.models.booking import Booking
from test_split_payment import api,razorpay_api,cashfree_api,booking_api,balance,source,create,verify


def test_real_checkout_producer_keeps_unknown_tax_and_funding_snapshot(api,monkeypatch):
    monkeypatch.setattr(settings,'source_evidence_enabled',True)
    balance(api,40)
    record=create(api,source(api)).json()
    with Session(api[2]) as db:
        purchase=db.scalar(select(SourceEvidence).where(SourceEvidence.event_type=='BOOKING_PURCHASE_RECORDED'))
        assert purchase.payload['transaction_basis']['price_amount']=='150.00'
        assert purchase.payload['transaction_basis']['discount_amount']=='0.00'
        assert purchase.payload['transaction_basis']['tax_amount'] is None
        assert purchase.payload['transaction_basis']['tax_status']=='SOURCE_NOT_SUPPORTED'
        assert Decimal(purchase.payload['wallet_amount'])==40
        assert Decimal(purchase.payload['gateway_amount'])==110
        assert purchase.payload['mode']=='test' and purchase.payload['gym_id']==1
        assert purchase.payload['owner_id_at_event'] is not None
        assert purchase.payload['financial_configuration']['status']!='PINNED'
        assert db.get(PaymentCheckout,record['id']).amount==110
        fingerprint=purchase.payload_hash
    entity=api[3].pay(record)
    assert verify(api,record,entity).json()['status']=='PAID'
    assert verify(api,record,entity).json()['status']=='PAID'
    with Session(api[2]) as db:
        assert db.scalar(select(func.count(SourceEvidence.id)).where(SourceEvidence.event_type=='BOOKING_PURCHASE_RECORDED'))==1
        assert db.scalar(select(SourceEvidence.payload_hash).where(SourceEvidence.event_type=='BOOKING_PURCHASE_RECORDED'))==fingerprint


def test_gateway_only_cart_funding_created_without_wallet_mutation(api,monkeypatch):
    from datetime import time
    from test_booking_access_qr import NOW
    from app.models.gym import Gym,GymOperatingHours
    from app.models.wallet import WalletAccount,WalletTransaction
    from app.routers.cart import router
    api[0].app.include_router(router,prefix='/api/v1')
    monkeypatch.setattr(settings,'source_evidence_enabled',True)
    with Session(api[2]) as db:
        db.get(Gym,1).gym_price_per_person=150
        hours=db.scalar(select(GymOperatingHours).where(GymOperatingHours.gym_id==1,GymOperatingHours.day_of_week==NOW.weekday()))
        if hours:hours.open_time=time(6);hours.close_time=time(23);hours.is_closed=False
        else:db.add(GymOperatingHours(gym_id=1,day_of_week=NOW.weekday(),open_time=time(6),close_time=time(23),is_closed=False))
        before=db.scalar(select(WalletAccount.balance).where(WalletAccount.user_id==1));db.commit()
    payload={'gym_id':1,'booking_date':str(NOW.date()),'preferred_start_time':'13:00','preferred_end_time':'14:00','member_count':1,'visitor_names':['Guest']}
    item=api[0].post('/api/v1/cart/items/gym',headers=api[1][1],json=payload)
    assert item.status_code==200,item.text
    response=create(api,{'kind':'CART','cart_item_ids':[item.json()['id']],'use_wallet':False})
    assert response.status_code==200,response.text
    record=response.json();assert verify(api,record,api[3].pay(record)).json()['status']=='PAID'
    with Session(api[2]) as db:
        checkout=db.get(PaymentCheckout,record['id']);funding=db.get(CheckoutFunding,checkout.id)
        line=db.scalar(select(BookingFunding).where(BookingFunding.checkout_id==checkout.id))
        assert funding.total_amount==funding.gateway_amount==checkout.amount==150
        assert funding.wallet_amount==line.wallet_amount==0
        assert line.total_amount==line.gateway_amount==150 and funding.state=='NONE'
        assert db.scalar(select(WalletAccount.balance).where(WalletAccount.user_id==1))==before
        assert db.scalar(select(func.count(WalletTransaction.id)).where(WalletTransaction.checkout_id==checkout.id))==0