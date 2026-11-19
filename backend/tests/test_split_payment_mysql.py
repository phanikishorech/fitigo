"""InnoDB row-lock races: distinct simultaneous purchases, same wallet."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, time
from threading import Barrier
from decimal import Decimal
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from test_razorpay_mysql import database
from app.models.booking import Booking, Payment
from app.models.wallet import WalletAccount, WalletTransaction
from app.models.checkout_funding import CheckoutFunding
from app.models.slot import GymSlot
from app.schemas.payment_checkout import CheckoutCreate
from app.services.payment_checkout_service import PaymentCheckoutService


def race(*operations):
    barrier = Barrier(len(operations))
    def run(operation):
        barrier.wait(timeout=15)
        return operation()
    with ThreadPoolExecutor(max_workers=len(operations)) as pool:
        futures = [pool.submit(run, operation) for operation in operations]
        return [future.result(timeout=45) for future in futures]


def test_two_purchases_cannot_spend_same_wallet_and_duplicate_finalize_is_once(database):
    engine, gateway, uid, source = database
    with Session(engine) as db:
        from app.models.gym import GymOperatingHours
        for day in range(7): db.add(GymOperatingHours(gym_id=source.gym_id,day_of_week=day,open_time=time(0),close_time=time(23,59),is_closed=False))
        db.add(WalletAccount(user_id=uid,balance=40,currency='INR',payment_mode='test'))
        slot=GymSlot(gym_id=source.gym_id,name='Split race',start_time=time(10),end_time=time(14),capacity=50,price=150,is_active=1)
        db.add(slot);db.flush();ids=[]
        for day in (2,3):
            booking=Booking(user_id=uid,gym_id=source.gym_id,gym_slot_id=slot.id,slot_date=(datetime.utcnow()+timedelta(days=day)).date(),
                quantity=1,visitor_names=['Fixture'],unit_price=150,total_price=150,currency='INR',status='PENDING_PAYMENT',expires_at=datetime.utcnow()+timedelta(minutes=15))
            db.add(booking);db.flush();ids.append(booking.id)
            db.add(Payment(booking_id=booking.id,provider='RAZORPAY',status='INITIATED',amount=150,currency='INR'))
        db.commit()
    def buy(bid):
        with Session(engine,autoflush=False) as db:
            return PaymentCheckoutService(db).create(uid,CheckoutCreate(kind='BOOKING',booking_id=bid,use_wallet=True),f'race-key-{bid}')
    results=race(lambda:buy(ids[0]),lambda:buy(ids[1]))
    assert sorted(Decimal(row['wallet_amount']) for row in results)==[0,40]
    assert sum(Decimal(row['gateway_amount']) for row in results)==260
    with Session(engine) as db:
        assert db.scalar(select(func.sum(CheckoutFunding.wallet_amount)).where(CheckoutFunding.state=='HELD'))==40
        assert db.scalar(select(WalletAccount.balance))==40
    record=next(row for row in results if Decimal(row['wallet_amount'])==40)
    gateway.pay(record)
    def fulfill():
        with Session(engine,autoflush=False) as db:return PaymentCheckoutService(db).reconcile(record['id'],uid)
    outcomes=race(fulfill,fulfill)
    assert all(row['status']=='PAID' for row in outcomes), outcomes
    with Session(engine) as db:
        assert db.scalar(select(WalletAccount.balance))==0
        assert db.scalar(select(func.count(WalletTransaction.id)))==1