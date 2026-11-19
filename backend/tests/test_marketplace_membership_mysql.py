"""4C verified Single-Gym entitlement, not statutory recognition or paid payout."""
from datetime import timedelta
from decimal import Decimal
from uuid import uuid4
import pytest
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from app.core.time import stored_instant
from app.models.membership import UserMembership
from app.models.payment_checkout import PaymentCheckout, PaymentAttempt
from app.models.checkout_funding import CheckoutFunding
from app.models.wallet import WalletTransaction
from app.models.financial_agreement import FinancialAgreementScope, FinancialAgreementVersion
from app.models.source_evidence import SourceOutbox
from app.models.marketplace_allocation import MarketplaceAllocation
from app.schemas.accounting_policy import AccountingPolicy
from app.services import source_evidence
from app.services.marketplace_allocations import allocate_event
from app.services.marketplace_calculation import AllocationBlocked
from test_customer_policy_mysql import database
from test_marketplace_booking_mysql import gates
from test_marketplace_calculation import terms
from test_financial_agreements import payload


def setup(engine,now,wallet,gateway,fee):
    at=stored_instant(now)
    with Session(engine) as db:
        scope=FinancialAgreementScope(mode='test',scope_key='DEFAULT');db.add(scope);db.flush()
        data=payload()['terms'];data['marketplace_contract']=terms()['marketplace_contract']
        policy=AccountingPolicy().model_dump(mode='json')
        policy['selection']['MEMBERSHIP_ACTIVATION']={'instant':'MEMBERSHIP_ACTIVATED','approval':{'status':'APPROVED','reference':'Activation fixture'}}
        data['policy_contract']=policy
        db.add(FinancialAgreementVersion(scope_id=scope.id,version=1,effective_from=at-timedelta(days=2),terms=data,action='AGREEMENT',
            agreement_reference='Fixture commercial',reason='Single fixture',ca_status='PENDING',actor_id=3,
            request_key=uuid4().hex,request_hash='0'*64,created_at=at-timedelta(days=3)))
        checkout=PaymentCheckout(id=str(uuid4()),user_id=1,source_key=uuid4().hex,kind='SINGLE_GYM',provider='RAZORPAY',mode='test',key_id='fixture',
            amount=gateway,currency='INR',snapshot={'gym_id':1},status='PAID',gateway_payment_id='pay_'+uuid4().hex if gateway else None,created_at=at-timedelta(hours=1))
        db.add(checkout);db.flush()
        debit=None
        if wallet:
            debit=WalletTransaction(account_id=1,user_id=1,checkout_id=checkout.id,direction='OUT',txn_type='PAYMENT',amount=wallet,currency='INR')
            db.add(debit);db.flush()
        db.add(CheckoutFunding(checkout_id=checkout.id,user_id=1,total_amount=100,wallet_amount=wallet,gateway_amount=gateway,
            currency='INR',mode='test',state='DEBITED' if wallet else 'NONE',request_wallet=str(wallet),
            wallet_transaction_id=debit.id if debit else None,expires_at=at+timedelta(hours=1)))
        if gateway:
            db.add(PaymentAttempt(id=str(uuid4()),checkout_id=checkout.id,external_id=checkout.gateway_payment_id,
                amount=gateway,currency='INR',status='SUCCESS',refunded_amount=0))
        member=db.get(UserMembership,1);member.membership_type='SINGLE_GYM';member.gym_id=1;member.gateway_checkout_id=checkout.id
        member.start_at=at;member.wallet_transaction_id=debit.id if debit else None
        db.flush()
        source_evidence.snapshot(db,'MEMBERSHIP_PURCHASE_RECORDED','CHECKOUT',checkout.id,checkout=checkout,occurred_at=checkout.created_at,
            gym_id=1,observe_owner=True,payload={'transaction_basis':{'price_amount':'100.00','discount_amount':'0.00','tax_amount':'0.00',
                'price_representation':'GROSS_BEFORE_DISCOUNT','currency':'INR'}})
        if fee is not None:
            source_evidence.snapshot(db,'PAYMENT_CAPTURED','PAYMENT_ATTEMPT',checkout.gateway_payment_id,checkout=checkout,
                payload={'provider_payment_id':checkout.gateway_payment_id,'verification_status':'VERIFIED',
                    'verification_source':'AUTHENTICATED_PROVIDER_FETCH','fee_amount':str(fee),'fee_basis':'INCLUDING_TAX'})
        source_evidence.membership_event(db,member,'MEMBERSHIP_ACTIVATED',member.id,member.start_at,fresh_activation=True)
        db.commit()
        return db.scalar(select(SourceOutbox.id).where(SourceOutbox.event_type=='MEMBERSHIP_ACTIVATED'))


@pytest.mark.parametrize('wallet,gateway,fee,net',[(0,100,'2.00','84.00'),(100,0,None,'85.00'),(60,40,'0.94','84.53')])
def test_single_gym_upfront_entitlement_wallet_gateway_split(database,wallet,gateway,fee,net):
    engine,now=database
    event_id=setup(engine,now,Decimal(wallet),Decimal(gateway),Decimal(fee) if fee else None)
    with Session(engine) as db:
        row=allocate_event(db,event_id)[0];db.commit()
        assert row.gym_gross_share==85 and row.fitigo_gross_commission==15
        assert row.gym_owner_net_entitlement==Decimal(net)
        assert row.calculation_snapshot['result']['entitlement_timing']=='UPFRONT'
        assert row.calculation_snapshot['result']['statutory_reporting_enabled'] is False
        assert allocate_event(db,event_id)[0].id==row.id;db.commit()
        assert db.scalar(select(func.count(MarketplaceAllocation.id)))==1
        assert db.get(UserMembership,1).paid_amount==100


def test_single_missing_fee_no_invented_paid_balance(database):
    engine,now=database;event_id=setup(engine,now,Decimal(0),Decimal(100),None)
    with Session(engine) as db:
        row=allocate_event(db,event_id)[0];db.commit()
        assert row.gym_gross_share==85 and row.gym_owner_net_entitlement is None
        assert row.calculation_status=='FEE_PENDING'


def test_cancelled_membership_is_not_new_entitlement(database):
    engine,now=database;event_id=setup(engine,now,Decimal(0),Decimal(100),None)
    with Session(engine) as db:
        db.get(UserMembership,1).status='CANCELLED';db.commit()
        with pytest.raises(AllocationBlocked):allocate_event(db,event_id)
        db.rollback();assert db.scalar(select(func.count(MarketplaceAllocation.id)))==0