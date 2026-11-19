"""Fresh install, representative d46 upgrade, and isolated backup/restore rehearsal."""
import os
import subprocess
from pathlib import Path
from datetime import datetime,date,time,timedelta
from decimal import Decimal
from uuid import uuid4
import pytest
from sqlalchemy import create_engine,text,inspect
from sqlalchemy.orm import Session
from sqlalchemy.exc import DBAPIError
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from app.core.config import settings
from app.database.session import engine as runner
from app.services.financial_deployment_readiness import fingerprint
from test_database_guard import disposable_name

ROOT=Path(__file__).resolve().parents[1]


def alembic():
    config=Config(str(ROOT/'alembic.ini'));config.set_main_option('script_location',str(ROOT/'alembic'))
    return config


@pytest.fixture
def isolated_pair(monkeypatch):
    names=[disposable_name(),disposable_name()]
    control=create_engine(runner.url.set(database=None),isolation_level='AUTOCOMMIT')
    with control.connect() as c:
        for name in names:c.execute(text(f'CREATE DATABASE `{name}` CHARACTER SET utf8mb4'))
    engines=[create_engine(runner.url.set(database=name)) for name in names]
    try:yield engines
    finally:
        for engine in engines:engine.dispose()
        with control.connect() as c:
            for name in names:c.execute(text(f'DROP DATABASE `{name}`'))
        control.dispose()


def migrate(engine,monkeypatch,revision):
    monkeypatch.setattr(settings,'database_url',engine.url.render_as_string(hide_password=False))
    command.upgrade(alembic(),revision)


def seed_legacy(engine):
    from app.models.auth import User
    from app.models.gym import Gym
    from app.models.slot import GymSlot
    from app.models.booking import Booking,Payment
    from app.models.payment_checkout import PaymentCheckout
    from app.models.membership import UserMembership
    from app.models.wallet import WalletAccount,WalletTransaction
    from app.models.financial_agreement import FinancialAgreementScope,FinancialAgreementVersion
    now=datetime(2026,11,12,9)
    with Session(engine) as db:
        db.add_all([User(id=i,email=f'upgrade-{i}@example.test',password_hash='unused',status='ACTIVE') for i in (1,2,3)]);db.flush()
        db.add(Gym(id=1,owner_user_id=3,name='Legacy preserved gym',status='APPROVED'));db.flush()
        db.add(GymSlot(id=1,gym_id=1,name='Legacy slot',start_time=time(9),end_time=time(20),capacity=10,price=100,is_active=1));db.flush()
        checkout=PaymentCheckout(id=str(uuid4()),user_id=1,source_key='legacy-fixture',kind='CART',mode='test',provider='RAZORPAY',key_id='fixture',
            amount=Decimal('100'),currency='INR',snapshot={},status='PAID',created_at=now)
        db.add(checkout);db.flush()
        db.add(Booking(id=1,user_id=1,gym_id=1,gym_slot_id=1,slot_date=date(2026,11,12),quantity=1,unit_price=100,total_price=100,currency='INR',status='CANCELLED',expires_at=now,checkout_id=checkout.id));db.flush()
        db.add(Payment(booking_id=1,provider='RAZORPAY',status='PAID',amount=100,currency='INR'))
        db.add(WalletAccount(id=1,user_id=1,balance=200,currency='INR',payment_mode='test'));db.flush()
        db.add(WalletTransaction(account_id=1,user_id=1,direction='IN',txn_type='TOPUP',amount=200,currency='INR'))
        db.add(UserMembership(user_id=1,membership_type='MULTI_GYM',status='ACTIVE',payment_status='PAID',payment_provider='WALLET',
            start_at=now,end_at=now+timedelta(days=40),paid_amount=100,currency='INR'))
        parent=db.query(FinancialAgreementScope).filter_by(mode='test',scope_key='DEFAULT').one()
        db.add(FinancialAgreementVersion(scope_id=parent.id,version=1,effective_from=now,terms={'legacy_fixture':True},action='AGREEMENT',
            agreement_reference='Preserved legacy contract',reason='Upgrade fixture',ca_status='PENDING',actor_id=3,request_key='legacy-request',request_hash='0'*64,created_at=now))
        db.commit()
        return checkout.id


def test_linear_chain_and_fresh_install(isolated_pair,monkeypatch):
    script=ScriptDirectory.from_config(alembic())
    assert script.get_heads()==['eb3f70126935']
    chain=list(script.walk_revisions())
    assert len(chain)==36 and all(not row.dependencies for row in chain)
    assert [r.revision for r in chain[:7]]==['eb3f70126935','da2e6f105824','c91dc50f4713','b80cb4fe3602','a79ba3ed2591','f68a92dc1480','e57f81cb0379']
    engine=isolated_pair[0];migrate(engine,monkeypatch,'head')
    with engine.connect() as c:
        assert c.scalar(text('SELECT version_num FROM alembic_version'))=='eb3f70126935'
        schema=inspect(c)
        assert {'financial_review_events','gym_monthly_calculations','financial_agreement_pins'}<=set(schema.get_table_names())
        assert c.scalar(text('SELECT COUNT(*) FROM financial_agreement_versions'))==0
        assert len(schema.get_check_constraints('marketplace_allocations'))>=6
        assert any(set(i['column_names'])=={'mode','gym_id','period','revision'} for i in schema.get_unique_constraints('gym_monthly_calculations'))
        assert any(i['name']=='ix_source_outbox_claim' for i in schema.get_indexes('financial_source_outbox'))
        assert next(c for c in schema.get_columns('gym_visit_payouts') if c['name']=='applied_cap')['nullable']
        triggers=set(c.scalars(text('SELECT TRIGGER_NAME FROM information_schema.TRIGGERS WHERE TRIGGER_SCHEMA=DATABASE()')))
        for table in ('marketplace_allocations','gym_visit_payouts','owner_payout_items','owner_payout_audit','gym_monthly_calculations','membership_visit_fees','financial_review_events'):
            assert {table+'_no_update',table+'_no_delete'}<=triggers


def test_upgrade_from_working_revision_preserves_every_existing_row(isolated_pair,monkeypatch):
    engine=isolated_pair[0];migrate(engine,monkeypatch,'d46e70ba9268');seed_legacy(engine)
    with engine.connect() as c:
        tables=set(inspect(c).get_table_names())-{'alembic_version'};before=fingerprint(c,tables)
    migrate(engine,monkeypatch,'head')
    with engine.connect() as c:
        assert fingerprint(c,tables)==before
        for table in ('financial_agreement_pins','financial_source_evidence','marketplace_allocations','gym_visit_payouts','owner_payouts','financial_review_events'):
            assert c.scalar(text('SELECT COUNT(*) FROM '+table))==0
        assert c.scalar(text('SELECT COUNT(*) FROM checkout_funding'))==0
    with pytest.raises(RuntimeError,match='Forward-only'):command.downgrade(alembic(),'da2e6f105824')
    with engine.connect() as c:assert c.scalar(text('SELECT version_num FROM alembic_version'))=='eb3f70126935'


def test_disposable_dump_restore_preserves_data_schema_and_triggers(isolated_pair,monkeypatch,tmp_path):
    source,target=isolated_pair
    migrate(source,monkeypatch,'head');checkout_id=seed_legacy(source)
    from app.models.source_evidence import SourceEvidence
    from app.models.financial_review import FinancialReviewEvent
    from app.services.marketplace_allocations import digest
    with Session(source) as db:
        stamp=datetime(2026,11,12,9)
        evidence=SourceEvidence(id=str(uuid4()),idempotency_key=uuid4().hex,event_type='BOOKING_PURCHASE_RECORDED',source_type='CHECKOUT',
            source_id=checkout_id,checkout_id=checkout_id,mode='test',evidence_status='VERIFIED_SOURCE',occurred_at=stamp,created_at=stamp,payload={},payload_hash=digest({}))
        db.add(evidence);db.flush()
        db.add(FinancialReviewEvent(id=str(uuid4()),case_id=str(uuid4()),revision=1,mode='test',gym_id=1,checkout_id=checkout_id,
            source_evidence_id=evidence.id,kind='RESERVED_OR_PAID',status='OPEN',actor_id=3,reason='Restore fixture only',
            request_key=uuid4().hex,request_hash='0'*64,snapshot={},snapshot_hash=digest({}),created_at=stamp));db.commit()
    binaries=Path(os.environ.get('FITIGO_MYSQL_BIN_DIR',r'C:\Program Files\MySQL\MySQL Server 26.7\bin'))
    assert (binaries/'mysqldump.exe').is_file() and (binaries/'mysql.exe').is_file()
    config=tmp_path/'isolated-client.cnf';dump=tmp_path/'isolated-financial.sql'
    # Credentials are generated by the isolated runner, never printed/in argv.
    config.write_text(f'[client]\nhost=127.0.0.1\nport={source.url.port}\nuser={source.url.username}\npassword={source.url.password}\n',encoding='utf-8')
    try:
        with dump.open('wb') as output:
            result=subprocess.run([str(binaries/'mysqldump.exe'),f'--defaults-extra-file={config}',
                '--single-transaction','--skip-lock-tables','--no-tablespaces','--set-gtid-purged=OFF','--triggers','--routines','--events',source.url.database],stdout=output,stderr=subprocess.PIPE,timeout=90)
        assert result.returncode==0,result.stderr.decode(errors='replace')
        assert dump.stat().st_size>1000
        with dump.open('rb') as input_stream:
            result=subprocess.run([str(binaries/'mysql.exe'),f'--defaults-extra-file={config}',target.url.database],stdin=input_stream,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=90)
        assert result.returncode==0,result.stderr.decode(errors='replace')
        with source.connect() as a,target.connect() as b:
            tables=inspect(a).get_table_names();assert set(tables)==set(inspect(b).get_table_names())
            assert fingerprint(a,tables)==fingerprint(b,tables)
            sql=text('SELECT TRIGGER_NAME FROM information_schema.TRIGGERS WHERE TRIGGER_SCHEMA=DATABASE()')
            assert set(a.scalars(sql))==set(b.scalars(sql))
        for statement in ('UPDATE financial_review_events SET reason=\'rewrite\'','DELETE FROM financial_review_events'):
            with target.begin() as c:
                with pytest.raises(DBAPIError,match='immutable'):c.execute(text(statement))
    finally:config.unlink(missing_ok=True)