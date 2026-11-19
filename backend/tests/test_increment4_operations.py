from types import SimpleNamespace
from pathlib import Path
import pytest
from sqlalchemy import event,select,func
from app.services.financial_startup import validate_configuration,validate_worker_request
from app.services.financial_deployment_readiness import inventory
from app.core.config import settings
from test_customer_policy_mysql import database


def flags(**changes):
    return SimpleNamespace(**{**dict(source_evidence_enabled=False,marketplace_allocations_enabled=False,
        marketplace_live_allocations_enabled=False,marketplace_payouts_enabled=False),**changes})


def test_all_disabled_startup_does_not_open_database():
    validate_configuration(flags(),object())


@pytest.mark.parametrize('changes',[
    {'marketplace_allocations_enabled':True},{'marketplace_live_allocations_enabled':True},
    {'marketplace_payouts_enabled':True},{'source_evidence_enabled':True}])
def test_invalid_gate_combinations_fail_closed(changes):
    with pytest.raises(RuntimeError):validate_configuration(flags(**changes),None)


@pytest.mark.parametrize('mode,reference,allocation', [('test','',False),('live','approved-reference',False),('test','approved-reference',True)])
def test_workers_require_explicit_authorization_and_gates(mode,reference,allocation):
    with pytest.raises(ValueError):validate_worker_request(flags(source_evidence_enabled=True),mode,reference,allocations=allocation)


def test_worker_validation_never_activates_flags():
    config=flags(source_evidence_enabled=True,marketplace_allocations_enabled=True)
    validate_worker_request(config,'test','approved-isolated-reference',allocations=True)
    assert config.marketplace_live_allocations_enabled is False and config.marketplace_payouts_enabled is False


def test_no_financial_scheduler_at_application_start():
    root=Path(__file__).resolve().parents[1]
    source=(root/'app/main.py').read_text()
    assert 'validate_configuration(settings,financial_engine)' in source
    assert 'create_task(recovery_loop(stop))' in source # pre-existing wallet recovery preserved
    for name in ('allocate_event(', 'allocate_visit(', 'finalize_month(', 'attribute_membership_fee('):assert name not in source
    for script in ('source_event_worker.py','marketplace_allocation_worker.py'):
        text=(root/'scripts'/script).read_text()
        assert "'--authorization-reference',required=True" in text
        assert text.index('validate_worker_request(settings')<text.index('with SessionLocal()')


def test_readonly_inventory_never_mutates_disposable_data(database):
    from app.models.financial_agreement import FinancialAgreementScope
    from sqlalchemy.orm import Session
    engine,now=database
    # This metadata fixture lacks alembic_version; inventory is for deployed
    # databases. Use migrated runner engine for a real schema-read test.
    from app.database.session import engine as migrated
    writes=[]
    def spy(conn,cursor,statement,parameters,context,executemany):
        if statement.lstrip().upper().startswith(('INSERT','UPDATE','DELETE','ALTER','CREATE','DROP')):writes.append(statement)
    event.listen(migrated,'before_cursor_execute',spy)
    try:
        before=inventory(migrated,settings);after=inventory(migrated,settings)
        assert before['fingerprints']==after['fingerprints']
        assert writes==[] and before['read_only']
    finally:event.remove(migrated,'before_cursor_execute',spy)