"""Read-only acceptance evidence. Never starts the application lifespan or workers."""
import json
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import select, text
from sqlalchemy.orm import Session
from app.database.session import engine
from app.models.wallet import WalletAccount
from app.services.admin_business import customer_activity, summary


def main():
    output = Path(sys.argv[1])
    if not output.is_absolute():
        raise ValueError('An absolute output path is required')
    result = {'read_only': True, 'date_from': '2026-01-01', 'date_to': '2026-12-31'}
    with engine.connect() as connection:
        connection.execute(text('START TRANSACTION WITH CONSISTENT SNAPSHOT, READ ONLY'))
        try:
            with Session(bind=connection, autoflush=False) as db:
                result['modes'] = {}
                for mode in ('test', 'live'):
                    data = summary(db, date_from=date(2026, 1, 1), date_to=date(2026, 12, 31), mode=mode)
                    accounts = []
                    for account in db.scalars(select(WalletAccount).where(WalletAccount.payment_mode == mode)):
                        individual = customer_activity(db, account.user_id)
                        accounts.append({'account_id': account.id, 'user_id': account.user_id,
                            'stored_balance': str(account.balance), 'individual_verified_balance': individual['wallet_balance']})
                    total = sum((Decimal(row['individual_verified_balance']) for row in accounts), Decimal(0)) if all(row['individual_verified_balance'] is not None for row in accounts) else None
                    result['modes'][mode] = {'collections': data['collections'], 'wallet': data['wallet'],
                        'individual_wallets': accounts, 'individual_sum': str(total),
                        'aggregate_matches_individuals': total is not None and data['wallet']['outstanding'] is not None and Decimal(data['wallet']['outstanding']) == total}
                queries = {
                    'checkout_counts': 'SELECT mode,kind,status,COUNT(*) AS count FROM payment_checkouts GROUP BY mode,kind,status',
                    'payment_evidence_counts': 'SELECT p.mode,p.kind,a.status,COUNT(*) AS count,SUM(a.amount) AS amount,SUM(a.refunded_amount) AS refunded FROM payment_attempts a JOIN payment_checkouts p ON p.id=a.checkout_id GROUP BY p.mode,p.kind,a.status',
                    'wallet_movements': 'SELECT a.payment_mode,t.direction,t.txn_type,COUNT(*) AS count,SUM(t.amount) AS amount FROM wallet_transactions t JOIN wallet_accounts a ON a.id=t.account_id GROUP BY a.payment_mode,t.direction,t.txn_type',
                    'wallet_unknown_modes': "SELECT id,user_id,payment_mode,balance FROM wallet_accounts WHERE payment_mode IS NULL OR payment_mode NOT IN ('test','live')",
                    'capture_date_columns': "SELECT TABLE_NAME,COLUMN_NAME FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME IN ('payment_attempts','payment_checkouts','payments') AND (COLUMN_NAME LIKE '%date%' OR COLUMN_NAME LIKE '%time%' OR COLUMN_NAME LIKE '%_at')",
                }
                result['independent'] = {name: [dict(row) for row in connection.execute(text(sql)).mappings()] for name, sql in queries.items()}
        finally:
            connection.rollback()
    with output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2, default=str)
    print('Read-only acceptance diagnostics saved:', output)


if __name__ == '__main__':
    main()