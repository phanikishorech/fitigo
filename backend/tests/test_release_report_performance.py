"""Synthetic scale/query-count acceptance on runner-owned MySQL only."""
import json
import os
import time
from pathlib import Path
from sqlalchemy import event
from sqlalchemy.orm import Session
from app.services.admin_business import summary, memberships
from test_admin_business_cleanup import evidence
from test_admin_financial_position import verified, DAY
from test_owner_dashboard_mysql import mysql_api, pytestmark


def test_report_scale_filters_query_budget_and_response_size(mysql_api):
    with Session(mysql_api[2]) as db:
        for index in range(1000):
            _, checkout = verified(db, gym=1 if index % 2 == 0 else 2)
            evidence(db, checkout)
        db.commit()
        records = []
        def record(conn, cursor, statement, parameters, context, many):
            records.append(statement.lstrip().split(None, 1)[0].upper())
        measurements = []
        for gym, mode, expected in [(None, 'test', '150000.00'), (1, 'test', '75000.00'), (None, 'live', '0.00')]:
            records.clear()
            event.listen(mysql_api[2], 'before_cursor_execute', record)
            start = time.perf_counter()
            try:
                data = summary(db, date_from=DAY, date_to=DAY, mode=mode, gym_id=gym)
            finally:
                event.remove(mysql_api[2], 'before_cursor_execute', record)
            measurements.append({'gym': gym, 'mode': mode, 'seconds': time.perf_counter()-start,
                'queries': len(records), 'bytes': len(json.dumps(data).encode()),
                'write_statements': sum(op in {'INSERT','UPDATE','DELETE'} for op in records)})
            assert data['collections']['total'] == expected
            assert measurements[-1]['write_statements'] == 0
            assert data['bookings']['total'] == (0 if mode == 'live' else 500 if gym else 1000)
        output = Path(os.environ['FITIGO_TEST_ARTIFACTS']) / 'report-performance.json'
        output.write_text(json.dumps(measurements, indent=2), encoding='utf-8')
        # Budget deliberately exposes per-purchase SELECTs; never relax to fit N+1.
        assert max(item['queries'] for item in measurements) < 300, measurements
        assert memberships(db, mode='test', limit=20, offset=100)['items'] == []