"""Aggregate-only inventory on an explicit READ ONLY consistent snapshot.

Never creates configuration, financial evidence, allocations, or an outbox lease.
Fingerprints stay aggregate hashes; no user/payment credentials or PII are emitted.
"""
import hashlib
import json
from sqlalchemy import inspect, text
from app.core.time import utcnow

GATES=('source_evidence_enabled','marketplace_allocations_enabled','marketplace_live_allocations_enabled','marketplace_payouts_enabled')


def fingerprint(connection, tables):
    result={}
    for table in sorted(tables):
        # Names come from SQLAlchemy schema inspection, never browser input.
        encoded=[]
        for row in connection.execute(text('SELECT * FROM `'+table.replace('`','``')+'`')).mappings():
            encoded.append(hashlib.sha256(json.dumps(dict(row),sort_keys=True,default=str,separators=(',',':')).encode()).hexdigest())
        result[table]={'rows':len(encoded),'sha256':hashlib.sha256(''.join(sorted(encoded)).encode()).hexdigest()}
    return result


def inventory(engine, runtime_settings):
    if engine.dialect.name!='mysql':raise ValueError('Readiness inventory requires MySQL.')
    with engine.connect() as c:
        c.execute(text('START TRANSACTION WITH CONSISTENT SNAPSHOT, READ ONLY'))
        try:
            inspector=inspect(c);tables=inspector.get_table_names()
            def scalar(sql):return c.scalar(text(sql))
            def groups(table,columns):
                if table not in tables:return None
                return [dict(r) for r in c.execute(text(f'SELECT {columns}, COUNT(*) AS count FROM {table} GROUP BY {columns} ORDER BY {columns}')).mappings()]
            def count(sql,needs):return scalar(sql) if all(t in tables for t in needs) else None
            result={'observed_at':utcnow().isoformat(),'read_only':True,'mysql_version':scalar('SELECT VERSION()'),
                'revision':scalar('SELECT version_num FROM alembic_version'),'table_count':len(tables),
                'gates':{key:getattr(runtime_settings,key) for key in GATES},'fingerprints':fingerprint(c,tables),
                'gyms_by_status':groups('gyms','status'),
                'gym_owners':scalar('SELECT COUNT(DISTINCT owner_user_id) FROM gyms'),
                'gyms_missing_owner':scalar('SELECT COUNT(*) FROM gyms g LEFT JOIN users u ON u.id=g.owner_user_id WHERE u.id IS NULL'),
                'gyms_inactive_owner':scalar("SELECT COUNT(*) FROM gyms g JOIN users u ON u.id=g.owner_user_id WHERE u.status<>'ACTIVE'"),
                'purchases':groups('payment_checkouts','mode, kind, status'),
                'booking_status':groups('bookings','status, attendance_status'),
                'admissions':groups('checkins','status, access_source'),
                'memberships':groups('user_memberships','membership_type, status, payment_status')}
            result['configurations']={}
            for mode in ('test','live'):
                result['configurations'][mode]={
                    'gyms_without_any_version':scalar("SELECT COUNT(*) FROM gyms g WHERE NOT EXISTS (SELECT 1 FROM financial_agreement_scopes s JOIN financial_agreement_versions v ON v.scope_id=s.id WHERE s.gym_id=g.id AND s.mode='"+mode+"')"),
                    'gyms_without_effective_own_version':scalar("SELECT COUNT(*) FROM gyms g WHERE NOT EXISTS (SELECT 1 FROM financial_agreement_scopes s JOIN financial_agreement_versions v ON v.scope_id=s.id WHERE s.gym_id=g.id AND s.mode='"+mode+"' AND v.action='AGREEMENT' AND v.effective_from<=UTC_TIMESTAMP() AND (v.effective_to IS NULL OR v.effective_to>UTC_TIMESTAMP()) AND NOT EXISTS (SELECT 1 FROM financial_agreement_versions n WHERE n.scope_id=s.id AND n.effective_from<=UTC_TIMESTAMP() AND n.effective_from>v.effective_from))")}
            result['configuration_conflicts']={
                'duplicate_starts':scalar('SELECT COUNT(*) FROM (SELECT scope_id,effective_from FROM financial_agreement_versions GROUP BY scope_id,effective_from HAVING COUNT(*)>1) x'),
                'invalid_intervals':scalar('SELECT COUNT(*) FROM financial_agreement_versions WHERE effective_to IS NOT NULL AND effective_to<=effective_from'),
                'version_time_order_conflicts':scalar('SELECT COUNT(*) FROM financial_agreement_versions a JOIN financial_agreement_versions b ON a.scope_id=b.scope_id AND a.version<b.version AND a.effective_from>=b.effective_from')}
            result['funding']={
                'purchases_without_funding':count("SELECT COUNT(*) FROM payment_checkouts p LEFT JOIN checkout_funding f ON f.checkout_id=p.id WHERE p.kind<>'WALLET_TOPUP' AND f.checkout_id IS NULL",['checkout_funding']),
                'cart_bookings_without_line_funding':count("SELECT COUNT(*) FROM bookings b JOIN payment_checkouts p ON p.id=b.checkout_id LEFT JOIN booking_funding f ON f.booking_id=b.id WHERE p.kind='CART' AND f.booking_id IS NULL",['booking_funding']),
                'component_mismatches':count('SELECT COUNT(*) FROM checkout_funding f JOIN payment_checkouts p ON p.id=f.checkout_id WHERE f.total_amount<>f.wallet_amount+f.gateway_amount OR f.gateway_amount<>p.amount OR f.mode<>p.mode OR f.user_id<>p.user_id',['checkout_funding']),
                'booking_without_checkout':scalar('SELECT COUNT(*) FROM bookings WHERE checkout_id IS NULL'),
                'membership_without_checkout':scalar('SELECT COUNT(*) FROM user_memberships WHERE gateway_checkout_id IS NULL')}
            evidence='financial_source_evidence' in tables
            result['evidence']={'schema_available':evidence,
                'purchases_without_purchase_evidence':scalar("SELECT COUNT(*) FROM payment_checkouts p WHERE p.kind<>'WALLET_TOPUP' AND NOT EXISTS (SELECT 1 FROM financial_source_evidence e WHERE e.checkout_id=p.id AND e.event_type IN ('BOOKING_PURCHASE_RECORDED','MEMBERSHIP_PURCHASE_RECORDED'))") if evidence else None,
                'purchase_tax_unknown':scalar("SELECT COUNT(*) FROM financial_source_evidence WHERE event_type IN ('BOOKING_PURCHASE_RECORDED','MEMBERSHIP_PURCHASE_RECORDED') AND (JSON_EXTRACT(payload,'$.transaction_basis.tax_amount') IS NULL OR JSON_UNQUOTE(JSON_EXTRACT(payload,'$.transaction_basis.tax_amount'))='null')") if evidence else None,
                'reason':None if evidence else 'SCHEMA_ABSENT_ALL_EXISTING_PURCHASES_LACK_IMMUTABLE_SOURCE_TAX_EVIDENCE'}
            result['admission_readiness']={
                'successful_missing_qr_window':scalar("SELECT COUNT(*) FROM checkins c LEFT JOIN access_qr_tokens q ON q.id=c.qr_token_id WHERE c.status='SUCCESS' AND (q.id IS NULL OR q.valid_from IS NULL OR q.expires_at IS NULL)"),
                'duplicate_success_daily_access':scalar("SELECT COUNT(*) FROM (SELECT daily_access_id FROM checkins WHERE status='SUCCESS' AND daily_access_id IS NOT NULL GROUP BY daily_access_id HAVING COUNT(*)>1) x"),
                'multi_memberships_visiting_multiple_gyms':scalar("SELECT COUNT(*) FROM (SELECT c.membership_id FROM checkins c JOIN user_memberships m ON m.id=c.membership_id WHERE c.status='SUCCESS' AND m.membership_type='MULTI_GYM' GROUP BY c.membership_id HAVING COUNT(DISTINCT c.gym_id)>1) x"),
                'multi_memberships_visiting_multiple_ist_months':scalar("SELECT COUNT(*) FROM (SELECT c.membership_id FROM checkins c JOIN user_memberships m ON m.id=c.membership_id WHERE c.status='SUCCESS' AND m.membership_type='MULTI_GYM' GROUP BY c.membership_id HAVING COUNT(DISTINCT DATE_FORMAT(c.checkin_time + INTERVAL 330 MINUTE,'%Y-%m'))>1) x"),
                'membership_terms_spanning_months':scalar("SELECT COUNT(*) FROM user_memberships WHERE DATE_FORMAT(start_at + INTERVAL 330 MINUTE,'%Y-%m')<>DATE_FORMAT(end_at + INTERVAL 330 MINUTE,'%Y-%m')")}
            result['cancelled_paid_without_credit_record']=count("SELECT COUNT(*) FROM bookings b JOIN payments p ON p.booking_id=b.id LEFT JOIN booking_cancellations c ON c.booking_id=b.id WHERE b.status='CANCELLED' AND p.status='PAID' AND c.id IS NULL",['booking_cancellations'])
            result['financial_tables']={name:(scalar('SELECT COUNT(*) FROM '+name) if name in tables else None) for name in
                ('financial_agreement_versions','financial_agreement_pins','financial_source_evidence','marketplace_allocations','gym_visit_payouts','gym_monthly_calculations','membership_visit_fees','owner_payouts','financial_review_events')}
            result['monitoring']={
                'outbox_by_mode_status':groups('financial_source_outbox','mode,status'),
                'expired_processing_leases':count("SELECT COUNT(*) FROM financial_source_outbox WHERE status='PROCESSING' AND lease_until<UTC_TIMESTAMP()",['financial_source_outbox']),
                'oldest_pending_created_at':scalar("SELECT MIN(created_at) FROM financial_source_outbox WHERE status IN ('PENDING','RETRY','AWAITING_POLICY','AWAITING_EVIDENCE')") if 'financial_source_outbox' in tables else None,
                'payouts_by_mode_status':groups('owner_payouts','mode,status'),
                'alert_delivery_configured_by_this_tool':False}
            result['historical_policy']='PRESERVE_AND_QUARANTINE; no invented tax/fees/owner timestamps, backfill, allocations or balance repair.'
            return result
        finally:c.rollback()