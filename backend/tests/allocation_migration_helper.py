"""Child migration ordering for earlier schema round-trip regression tests."""
from importlib.util import spec_from_file_location, module_from_spec
from pathlib import Path
from alembic.operations import Operations
from alembic.migration import MigrationContext


def allocation_migration(connection):
    path = Path(__file__).resolve().parents[1] / 'alembic/versions/a79ba3ed2591_marketplace_allocation.py'
    spec = spec_from_file_location('allocation_migration', path)
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    module.op = Operations(MigrationContext.configure(connection))
    child_path=path.parent/'b80cb4fe3602_gym_visit_payouts.py'
    child_spec=spec_from_file_location('visit_migration',child_path)
    child=module_from_spec(child_spec);child_spec.loader.exec_module(child)
    child.op=module.op
    payout_path=path.parent/'c91dc50f4713_owner_payout_workflow.py'
    payout_spec=spec_from_file_location('payout_migration',payout_path)
    payout=module_from_spec(payout_spec);payout_spec.loader.exec_module(payout);payout.op=module.op
    monthly_path=path.parent/'da2e6f105824_monthly_visit_completion.py'
    monthly_spec=spec_from_file_location('monthly_migration',monthly_path)
    monthly=module_from_spec(monthly_spec);monthly_spec.loader.exec_module(monthly);monthly.op=module.op
    review_path=path.parent/'eb3f70126935_financial_review_controls.py'
    review_spec=spec_from_file_location('review_migration',review_path)
    review=module_from_spec(review_spec);review_spec.loader.exec_module(review);review.op=module.op
    class OrderedMigrations:
        def downgrade(self):
            # Test-only empty-fixture teardown, NOT a production downgrade path.
            import sqlalchemy as sa
            for table in ('financial_review_events','membership_visit_fees','gym_monthly_calculations'):
                if sa.inspect(connection).has_table(table):
                    assert connection.scalar(sa.text(f'SELECT COUNT(*) FROM {table}')) == 0
                    module.op.drop_table(table)
            payout.downgrade();child.downgrade();module.downgrade()
        def upgrade(self):
            module.upgrade();child.upgrade();payout.upgrade();monthly.upgrade();review.upgrade()
    return OrderedMigrations()