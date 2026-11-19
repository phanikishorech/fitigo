"""SELECT-only transaction trace and authenticated GET matrix; no provider calls."""
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import httpx
from sqlalchemy import select, text
from sqlalchemy.orm import Session
from app.core.config import settings
from app.core.security import create_access_token
from app.core.time import as_ist, ist_today
from app.database.session import engine
from app.models.auth import User, Role, UserRole
from app.services.admin_business import summary


def main():
    output = Path(sys.argv[1])
    if not output.is_absolute():
        raise ValueError('Absolute output path required')
    result = {'read_only': True, 'observed_ist_date': str(ist_today()), 'configured_mode': settings.gateway_mode}
    with engine.connect() as connection:
        connection.execute(text('START TRANSACTION WITH CONSISTENT SNAPSHOT, READ ONLY'))
        try:
            def rows(sql):
                return [dict(row) for row in connection.execute(text(sql)).mappings()]
            result['wallet_funded_purchases'] = rows('''
                SELECT p.id checkout_id,p.kind,p.mode,p.provider configured_provider,p.status checkout_status,
                p.amount checkout_gateway_amount,p.gateway_payment_id,f.total_amount,f.wallet_amount,f.gateway_amount,
                f.state funding_state,f.resolved_at,f.wallet_transaction_id,w.direction,w.txn_type,w.amount ledger_amount,
                w.created_at ledger_created_at,a.payment_mode wallet_environment,
                b.id booking_id,b.gym_id,g.name gym_name,b.status booking_status,b.slot_date,b.total_price,
                pm.id payment_id,pm.provider payment_provider,pm.status payment_status,pm.amount payment_amount
                FROM payment_checkouts p JOIN checkout_funding f ON f.checkout_id=p.id
                LEFT JOIN wallet_transactions w ON w.id=f.wallet_transaction_id
                LEFT JOIN wallet_accounts a ON a.id=w.account_id
                LEFT JOIN bookings b ON b.checkout_id=p.id LEFT JOIN gyms g ON g.id=b.gym_id
                LEFT JOIN payments pm ON pm.booking_id=b.id
                WHERE f.wallet_amount>0 ORDER BY f.resolved_at,p.id''')
            for row in result['wallet_funded_purchases']:
                row['funding_resolved_ist'] = as_ist(row['resolved_at']).isoformat() if row['resolved_at'] else None
            result['cancellation_evidence'] = rows('''
                SELECT c.id cancellation_id,c.booking_id,c.payment_id,c.amount,c.currency,c.created_at,
                c.wallet_transaction_id,w.direction,w.txn_type,w.amount ledger_credit,w.created_at ledger_created_at
                FROM booking_cancellations c JOIN bookings b ON b.id=c.booking_id
                JOIN checkout_funding f ON f.checkout_id=b.checkout_id
                LEFT JOIN wallet_transactions w ON w.id=c.wallet_transaction_id
                WHERE f.wallet_amount>0 ORDER BY c.id''')
            for row in result['cancellation_evidence']:
                row['cancelled_ist'] = as_ist(row['created_at']).isoformat()
            result['membership_evidence'] = rows('''
                SELECT p.id checkout_id,p.kind,p.mode,p.status checkout_status,p.amount gateway_amount,
                m.id membership_id,m.gym_id,m.payment_status,m.paid_amount,m.currency,
                a.status attempt_status,a.amount attempt_amount,a.refunded_amount
                FROM payment_checkouts p JOIN user_memberships m ON m.gateway_checkout_id=p.id
                LEFT JOIN payment_attempts a ON a.checkout_id=p.id AND a.external_id=p.gateway_payment_id
                WHERE p.kind IN ('SINGLE_GYM','MULTI_GYM') ORDER BY p.id''')
            result['wallet_only_provider_attempts'] = rows('''
                SELECT a.checkout_id,a.id,a.status,a.amount,a.currency,a.refunded_amount
                FROM payment_attempts a JOIN checkout_funding f ON f.checkout_id=a.checkout_id
                WHERE f.wallet_amount>0 AND f.gateway_amount=0''')
            with Session(bind=connection, autoflush=False) as db:
                user = db.scalar(select(User).join(UserRole, UserRole.user_id == User.id).join(Role, Role.id == UserRole.role_id)
                    .where(Role.name.in_(['ADMIN', 'SUPER_ADMIN']), User.status == 'ACTIVE'))
                token = create_access_token(str(user.id), {'version': user.token_version})
                cases = [('default', {}), ('full_test', {'date_from': '2026-01-01', 'date_to': '2026-12-31', 'mode': 'test'}),
                    ('payment_day_test', {'date_from': '2026-11-17', 'date_to': '2026-11-17', 'mode': 'test'}),
                    ('booking_day_test', {'date_from': '2026-11-18', 'date_to': '2026-11-18', 'mode': 'test'}),
                    ('full_test_gym_189', {'date_from': '2026-01-01', 'date_to': '2026-12-31', 'mode': 'test', 'gym_id': 189}),
                    ('full_test_gym_188', {'date_from': '2026-01-01', 'date_to': '2026-12-31', 'mode': 'test', 'gym_id': 188}),
                    ('full_live', {'date_from': '2026-01-01', 'date_to': '2026-12-31', 'mode': 'live'})]
                result['api_matrix'] = {}
                with httpx.Client(base_url='http://127.0.0.1:8000', headers={'Authorization': 'Bearer ' + token}, timeout=60) as client:
                    for name, params in cases:
                        response = client.get('/api/v1/admin/business/summary', params=params)
                        response.raise_for_status()
                        data = response.json()
                        parsed = {k: date.fromisoformat(v) if k in {'date_from', 'date_to'} else v for k, v in params.items()}
                        expected = summary(db, **parsed)
                        assert data['collections'] == expected['collections'], name
                        result['api_matrix'][name] = {'request': str(response.request.url), 'status': response.status_code,
                            'cache_control': response.headers.get('cache-control'), 'requested_filters': params,
                            **{key: data[key] for key in ('date_from', 'date_to', 'mode', 'collections')},
                            'nonzero_days': [row for row in data['series'] if any(row[k] != '0.00' for k in
                                ('individual_collections', 'single_gym_collections', 'multi_gym_collections'))]}
        finally:
            connection.rollback()
    with output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2, default=str)
    print('Saved read-only transaction audit:', output)
    for name, row in result['api_matrix'].items():
        print(name, row['date_from'], row['date_to'], row['mode'], row['collections']['known_dated_categories'],
            'known total=', row['collections']['known_dated_total'], 'full total=', row['collections']['total'])


if __name__ == '__main__':
    main()