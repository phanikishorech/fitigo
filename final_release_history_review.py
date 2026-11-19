"""One-off READ ONLY record classification; no provider calls or historical repair."""
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'backend'))
from sqlalchemy import inspect, select, text
from sqlalchemy.orm import Session
from app.database.session import engine
from app.models.payment_checkout import PaymentCheckout, PaymentAttempt
from app.models.booking import Booking, Payment
from app.models.membership import UserMembership
from app.models.checkout_funding import CheckoutFunding, BookingFunding
from app.models.access import Checkin, AccessQrToken
from app.models.customer_policy import BookingCancellation
from app.models.wallet import WalletTransaction
from app.models.financial_agreement import FinancialAgreementVersion


def main():
    records = []
    with engine.connect() as connection:
        connection.execute(text('START TRANSACTION WITH CONSISTENT SNAPSHOT, READ ONLY'))
        try:
            tables = set(inspect(connection).get_table_names())
            with Session(bind=connection, autoflush=False) as db:
                # This review deliberately refuses to invent generalized classifications
                # if the known historical evidence/configuration baseline has changed.
                assert 'financial_source_evidence' not in tables
                assert db.scalar(select(FinancialAgreementVersion.id).limit(1)) is None
                purchases = list(db.scalars(select(PaymentCheckout).order_by(PaymentCheckout.id)))
                for purchase in purchases:
                    funding = db.get(CheckoutFunding, purchase.id)
                    bookings = list(db.scalars(select(Booking).where(Booking.checkout_id == purchase.id)))
                    members = list(db.scalars(select(UserMembership).where(UserMembership.gateway_checkout_id == purchase.id)))
                    attempts = list(db.scalars(select(PaymentAttempt).where(PaymentAttempt.checkout_id == purchase.id)))
                    missing = ['SOURCE_EVIDENCE', 'AUTHORITATIVE_PURCHASE_TAX', 'PINNED_HISTORICAL_GYM_CONFIGURATION']
                    if funding is None: missing.append('CHECKOUT_FUNDING')
                    line_missing = [b.id for b in bookings if db.get(BookingFunding, b.id) is None]
                    if line_missing: missing.append('BOOKING_LINE_FUNDING')
                    wallet_date = bool(funding and funding.gateway_amount == 0 and funding.resolved_at)
                    if not wallet_date: missing.append('AUTHORITATIVE_PAYMENT_DATE')
                    records.append({'type': 'purchase', 'record_id': purchase.id, 'kind': purchase.kind,
                        'mode': purchase.mode, 'status': purchase.status, 'booking_ids': [b.id for b in bookings],
                        'membership_ids': [m.id for m in members], 'missing_line_funding_booking_ids': line_missing,
                        'classification': 'Not eligible for financial allocation',
                        'review_classification': 'Incomplete and requires manual review', 'missing': missing,
                        'provider_lookup_reference_present': bool(purchase.gateway_payment_id),
                        'provider_attempt_count': len(attempts),
                        'recovery': 'Provider reference may permit authenticated investigation; capture timestamp, tax and historical terms recovery is NOT verified. Do not backfill or allocate.'})
                for scan in db.scalars(select(Checkin).order_by(Checkin.id)):
                    token = db.get(AccessQrToken, scan.qr_token_id)
                    missing = []
                    if not token or not token.valid_from or not token.expires_at:
                        missing.append('QR_VALIDITY_WINDOW')
                    elif not token.valid_from <= scan.checkin_time < token.expires_at:
                        missing.append('SCAN_OUTSIDE_QR_WINDOW')
                    if token and scan.access_source == 'BOOKING_ACCESS':
                        booking = db.get(Booking, scan.booking_id)
                        if not booking or token.booking_id != booking.id or scan.gym_id != booking.gym_id or scan.user_id != booking.user_id or token.visitor_index != scan.visitor_index:
                            missing.append('BOOKING_SOURCE_LINK')
                    elif token and token.daily_access_id != scan.daily_access_id:
                        missing.append('DAILY_ACCESS_SOURCE_LINK')
                    records.append({'type': 'admission', 'record_id': scan.id, 'booking_id': scan.booking_id,
                        'membership_id': scan.membership_id, 'classification': 'Incomplete and requires manual review' if missing else 'Complete',
                        'classification_scope': 'QR/source evidence only', 'missing': missing,
                        'allocation_classification': 'Not eligible for financial allocation: purchase/configuration evidence missing'})
                for booking in db.scalars(select(Booking).where(Booking.status == 'CANCELLED').order_by(Booking.id)):
                    cancellation = db.scalar(select(BookingCancellation).where(BookingCancellation.booking_id == booking.id))
                    credit = db.get(WalletTransaction, cancellation.wallet_transaction_id) if cancellation and cancellation.wallet_transaction_id else None
                    complete = bool(cancellation and (cancellation.amount == 0 or credit and credit.amount == cancellation.amount
                        and credit.user_id == booking.user_id and credit.direction == 'IN' and credit.txn_type == 'CANCELLATION_CREDIT'))
                    records.append({'type': 'cancellation', 'record_id': booking.id,
                        'classification': 'Complete' if complete else 'Incomplete and requires manual review',
                        'classification_scope': 'Cancellation-to-wallet-credit consistency',
                        'cancellation_id': cancellation.id if cancellation else None,
                        'wallet_transaction_id': credit.id if credit else None,
                        'reason': 'Linked credit matches' if complete else 'No matching permanent cancellation/credit evidence; eligibility must not be inferred'})
        finally:
            connection.rollback()
    result = {'read_only': True, 'source_schema_available': False, 'historical_versions': 0,
        'classification_counts': dict(Counter(row['classification'] for row in records)),
        'recoverable_from_authoritative_source_confirmed': 0, 'records': records,
        'limitations': 'Complete admission/cancellation evidence does not make its purchase allocation-ready. No source was fabricated and no recovery was executed.'}
    with (ROOT / 'FINAL_RELEASE_HISTORY.json').open('x', encoding='utf-8') as output:
        json.dump(result, output, indent=2)
    print('Read-only historical classification:', result['classification_counts'])


if __name__ == '__main__':
    main()