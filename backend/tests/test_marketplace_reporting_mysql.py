from decimal import Decimal
from sqlalchemy import select,func,event,text
from sqlalchemy.orm import Session
from app.services.marketplace_reporting import report
from app.services.marketplace_allocations import allocate_event
from app.services import owner_payouts
from test_customer_policy_mysql import database
from test_marketplace_booking_mysql import setup,gates
from test_owner_payout_workflow_mysql import prepared,request,move
from app.models.marketplace_allocation import MarketplaceAllocation
from app.models.owner_payout import OwnerPayout


def test_report_reconciles_allocation_drilldown_and_does_not_write(database):
    engine,now=database;ids,_=setup(engine,now)
    with Session(engine) as db:
        for identifier in ids:allocate_event(db,identifier);db.commit()
    writes=[]
    def spy(conn,cursor,statement,parameters,context,executemany):
        if statement.lstrip().upper().startswith(('INSERT','UPDATE','DELETE')):writes.append(statement)
    event.listen(engine,'before_cursor_execute',spy)
    try:
        with Session(engine) as db:
            data=report(db,mode='test',date_from=now.date(),date_to=now.date())
            assert data['available'] and data['total']==2
            assert Decimal(data['totals']['attended_commission'])==sum(Decimal(r['fitigo_gross_commission']) for r in data['items'])==30
            assert Decimal(data['totals']['gym_gross_share'])==sum(Decimal(r['gym_gross_share']) for r in data['items'])==170
            assert Decimal(data['totals']['allocated_gateway_fees'])==sum(Decimal(r['gateway_fee']) for r in data['items'])==Decimal('1.58')
            assert Decimal(data['totals']['total_owner_payable'])==sum(Decimal(r['owner_net']) for r in data['items'])
            assert data['totals']['multi_gym_fitigo_earnings'] is None
            assert report(db,mode='live',date_from=now.date(),date_to=now.date())['total']==0
            assert report(db,mode='test',date_from=now.date(),date_to=now.date(),owner_user_id=2)['total']==0
            assert report(db,mode='test',date_from=now.date(),date_to=now.date(),gateway='CASHFREE')['total']==0
            assert report(db,mode='test',date_from=now.date(),date_to=now.date(),category='NO_SHOW')['total']==0
        assert writes==[]
    finally:event.remove(engine,'before_cursor_execute',spy)


def test_unknown_fee_total_is_not_fake_zero(database):
    engine,now=database;ids,_=setup(engine,now,fee=None)
    with Session(engine) as db:
        allocate_event(db,ids[0]);db.commit()
        data=report(db,mode='test',date_from=now.date(),date_to=now.date())
        assert data['fee_pending_count']==1 and data['totals']['total_owner_payable'] is None
        assert data['items'][0]['gateway_fee'] is None and data['totals']['attended_commission']=='15.00'
        assert data['totals']['allocated_gateway_fees'] is None and data['totals']['known_allocated_gateway_fees']=='0.00'


def test_paid_cash_separate_from_cohort_entitlement(prepared):
    from datetime import timedelta
    engine,now,identifier=prepared
    with Session(engine) as db:
        row=owner_payouts.create(db,3,request(identifier),'report-create-key');db.commit()
        for state in ('APPROVED','PROCESSING'):move(db,row,state,state+'-report');db.commit()
        evidence={'reference':'BANK-REPORT','paid_at':(now+timedelta(days=40)).isoformat(),'amount':'84','currency':'INR',
            'source':'BANK_STATEMENT','document_reference':'Protected evidence','owner_user_id':3}
        move(db,row,'PAID','paid-report',evidence);db.commit()
        cohort=report(db,mode='test',date_from=now.date(),date_to=now.date())
        assert cohort['totals']['total_owner_payable']=='0.00'
        assert cohort['totals']['actual_payouts_made']=='0.00'
        paid=report(db,mode='test',date_from=(now+timedelta(days=40)).date(),date_to=(now+timedelta(days=40)).date())
        assert paid['totals']['actual_payouts_made']=='84.00'
        assert paid['total']==0