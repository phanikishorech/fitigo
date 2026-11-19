"""Read-only working-data acceptance comparison; emits aggregates, never identities."""
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.database.session import engine
from app.services.admin_business import summary


def main():
    output = Path(sys.argv[1])
    if not output.is_absolute():
        raise ValueError('An absolute output path is required')
    results = {'read_only': True}
    with engine.connect() as connection:
        connection.execute(text('START TRANSACTION WITH CONSISTENT SNAPSHOT, READ ONLY'))
        try:
            with Session(bind=connection, autoflush=False) as db:
                for mode in ('test', 'live'):
                    data = summary(db, date_from=date(2026, 1, 1), date_to=date(2026, 12, 31), mode=mode)
                    results[mode] = {key: data[key] for key in ('overall', 'visits', 'collections', 'wallet', 'bookings')}
                queries = {
                    'wallet_balance_sum': 'SELECT COALESCE(SUM(balance),0) FROM wallet_accounts',
                    'wallet_ledger_net': "SELECT COALESCE(SUM(CASE WHEN direction='IN' THEN amount ELSE -amount END),0) FROM wallet_transactions",
                    'booking_count': 'SELECT COUNT(*) FROM bookings',
                    'cancelled': "SELECT COUNT(*) FROM bookings WHERE status='CANCELLED'",
                    'explicit_no_show': "SELECT COUNT(*) FROM bookings WHERE attendance_status='NO_SHOW' AND attendance_marked_at IS NOT NULL",
                }
                results['independent'] = {key: str(connection.scalar(text(sql))) for key, sql in queries.items()}
        finally:
            connection.rollback()
    with output.open('x', encoding='utf-8') as stream:
        json.dump(results, stream, indent=2, default=str)
    print('Aggregate read-only comparison saved:', output)


if __name__ == '__main__':
    main()