# Phase 3 — Approved reporting and cancellation subset

## Approved scope and safety

The user selected: **Implement admin test/live isolation and truthful cancellation/refund status only; defer wallet spending and gateway offers.** This document describes that completed implementation, not completion of the original full wallet/offer phase.

No working/production database changes, migration additions, environment edits, credential rotation, gateway calls, real charges/refunds, commits, pushes or deployments were performed for Phase 3. Tests used isolated databases and mocked providers; MySQL fixtures created and removed disposable schemas. Existing Phase 1/2 and Home banner work was preserved. Starting hashes were checked during execution; their temporary file was no longer accessible on the last resumption, so the final review used current Git diffs and reran targeted validation rather than claiming another hash comparison.

The architecture review and deferred business decisions remain in `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend/PAYMENT_PHASE3_REVIEW.md`.

## Admin reporting changes

Affected endpoints:
- GET `/api/v1/admin/dashboard/summary`
- GET `/api/v1/admin/reports/bookings/daily`

Both use the same `eligible_admin_payment()` SQL predicate. A contribution requires:
- Booking Payment is PAID, has a positive INR amount, and belongs to an INR booking.
- Booking links to a PAID BOOKING/CART PaymentCheckout with matching purchasing user, provider and currency.
- Checkout provider is RAZORPAY or CASHFREE and has a recorded gateway payment ID.
- Checkout mode exactly equals the effective `settings.gateway_mode` (existing PAYMENT_ENV/PAYMENT_MODE mapping).

Unlinked legacy rows have no trustworthy payment mode and are excluded, even if their provider name says Cashfree/Razorpay. Wallet, DUMMY, free, failed, pending, review-required, fully refunded and partially refunded records contribute zero. Existing records are neither rewritten nor reclassified. No order-ID prefix is used to infer environment.

The predicate uses EXISTS, not a multiplying join: each booking payment allocation contributes once. Multiple bookings sharing one cart checkout sum their allocations, not the full checkout once per booking. Selected-gym daily totals and overall totals use the same rules. QR visitor counts do not multiply payments.

### Preserved meaning and disclosed limitations

- Admin reports group by **scheduled booking date** and measure paid booking amounts, not earned revenue, cash receipts, settlement or payouts.
- Cancelled/no-show bookings remain included while their payment AND checkout are still PAID. Cancellation does not return money; this preserves the pre-existing admin paid-total interpretation instead of silently adopting owner recognition rules.
- Once a refund/partial refund/review status is reconciled, it no longer contributes. Partial refunds are excluded rather than inventing per-booking/cart net allocation rules.
- Owner reporting is unchanged: purchase-date filtering, successful-check-in eligibility for individual bookings, single-gym membership recognition, explicit mode, and no wallet/Multi-Gym allocation.
- Booking/user/gym counts are not payment-mode-filtered. UI copy explicitly states that booking counts cover all modes.
- `last_30d` is corrected to exactly today plus the preceding 29 scheduled dates. Previously it had no upper bound and could include future bookings.
- Existing amount fields are retained. Summary `revenue` and daily rows add `mode`, `currency`, `date_basis`, and `basis`. The daily endpoint still returns a list. Empty daily lists have no scope metadata; the UI says scope unavailable rather than assuming live.
- Test mode is visibly labelled **No real money**. Missing mode from an older response is labelled unavailable, never silently live.

## Cancellation and refund truthfulness

Affected cancellation routes:
- POST `/api/v1/bookings/{booking_id}/cancel` (customer)
- POST `/api/v1/gym-owner/bookings/{booking_id}/cancel` (owner)
- POST `/api/v1/admin/bookings/{booking_id}/cancel` (admin)

The existing ownership/role checks, booking cancellation, capacity logic and QR revocation remain. The removed behavior is the automatic PAID -> REFUNDED status assignment for non-gateway/unlinked payments without a real wallet reversal.

Cancellation now preserves payment state for ALL providers, including WALLET and DUMMY. It neither changes wallet balance nor inserts a fake refund ledger entry. A payment already marked REFUNDED remains so. Existing historical labels are not repaired automatically; potentially incorrect older wallet/DUMMY refund records require explicit reconciliation, not assumptions.

Customer/owner booking responses and the admin cancellation response add:
- `refund_initiated: false`
- `cancellation_message`: cancellation does not initiate a gateway refund or wallet credit; payment/refund history is separate and support must review refund requests.

`refund_initiated` describes what this API operation does, NOT proof that a separate provider-dashboard refund never happened. The existing payment status/history remains the recorded refund state. No new bank-refund state or refund eligibility promise is invented.

The admin payment-status mutation endpoint also rejects attempts to set REFUNDED without a verified refund workflow, and rejects wallet status edits that cannot execute a ledger movement. Existing gateway status overrides remain blocked. It returns HTTP 409 rather than fabricating money movement.

Customer, owner and admin booking screens show the cancellation/refund separation notice. The admin confirmation dialog no longer claims that cancellation invokes a refund workflow.

### Intended refund process (manual; not executed)

1. Support reviews the request against the merchant's approved refund policy. Cancelling access is not a refund authorization.
2. An authorized operator initiates an eligible refund against the original provider/payment through the provider's supported dashboard workflow. Never switch provider or use a replacement charge.
3. Existing signed-webhook/authenticated reconciliation reads provider evidence and updates the local payment history/access state. Pending/failed/unconfirmed refunds must not be represented as completed.
4. Full/partial refund handling remains the existing provider reconciliation behavior; partial allocations require review. Duplicate events must not create additional reversals.
5. Wallet refunds have no newly authorized credit workflow in this subset. Do not mark wallet payments REFUNDED via a status edit or manually mint replacement balance.

No refund initiation adapter, automatic cancellation refund, wallet spending, promotional credit or gateway-offer fulfillment was added. Amount/currency verification and REVIEW_REQUIRED protections remain unchanged.

## Files changed in this subset

Backend:
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend/app/services/admin_revenue.py` (new shared predicate and scope)
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend/app/services/admin_dashboard_service.py`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend/app/routers/admin.py`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend/app/services/booking_service.py`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend/app/services/admin_booking_ops_service.py`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend/app/schemas/admin_reports.py`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend/app/schemas/booking.py`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend/app/schemas/booking_owner.py`

Frontend:
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/frontend/src/admin/RevenueScope.tsx` (new)
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/frontend/src/admin/Dashboard.tsx`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/frontend/src/admin/Account.tsx`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/frontend/src/admin/Bookings.tsx`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/frontend/src/admin/services.ts`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/frontend/src/screens/Admin/api.ts`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/frontend/src/components/common/CancellationNotice.tsx` (new)
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/frontend/src/owner/Bookings.tsx`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/frontend/src/pages/booking/BookingDetailPage.tsx`

Tests/documentation:
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend/tests/test_admin_financial_integrity.py` (new)
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend/tests/test_admin_financial_mysql.py` (new)
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend/tests/test_dashboard_date_ranges.py` (revenue fixtures now include verified mode linkage)
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend/tests/test_razorpay_payments.py` (explicit cancellation assertions)
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/frontend/scripts/financialScope.test.mjs` (new)
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/frontend/scripts/financial-scope-browser.mjs` (new)
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend/DASHBOARD_DATE_RANGES.md`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend/PAYMENT_PHASE3_REVIEW.md`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend/PAYMENT_PHASE3_IMPLEMENTATION.md` (this handoff)

## Validation actually performed

- Pre-change payment/reporting baseline: 170 passed; focused resumption subset: 34 passed (overlapping, not additive).
- Implementation targeted suite: 161 passed, including the two real strict-MySQL test/live reporting cases. Repeated on final resumption: **161 passed**. All MySQL writes were to fixture-created disposable schemas.
- Full backend suite on a freshly migrated disposable MySQL schema: **574 passed, 24 failed, 2 setup errors** (600 cases). Initial attempt timed out at 290 seconds; a subsequent 600-second-limit run completed. Both temporary main schemas were removed.
- Compared with Phase 2, one additional legacy test failed: booking-idempotency fixture uses `date.today()` with an 18:00 start. A direct no-database check at the local test clock 18:09 IST confirmed BOOKING_TIME_PASSED for that same-day start and success for the following day. No booking-time check was weakened and this unrelated fixture was not edited.
- Other failures remain legacy time-sensitive booking/obsolete membership and wallet expectations, in-process migration logging interference, and the existing wallet downgrade index/FK-order setup errors. The full suite is NOT green.
- Frontend: **381 tests passed**, TypeScript app check passed, production build passed; rerun successfully after final resumption.
- Isolated mocked browser harness passed dashboard/daily test/live labels, 360/768/1440px layout, cancellation warning, one cancellation request and PAID-not-REFUNDED display. The initial browser attempt started before Vite was ready and failed; the readiness-gated rerun passed.
- No provider signatures/adapters were modified. Existing Razorpay/Cashfree, duplicate webhook, recovery, mismatch, refund reconciliation, and wallet-history regressions passed in the targeted selection. These are mock-provider checks, not real payment acceptance.
- No new schema/migration is required by this subset. Fresh migration-to-head was tested as setup for the isolated full run; no working-database migration was performed.

Temporary Phase 3 artifacts disappeared before the last resumption. The earlier full-suite/browser outcomes above are recorded from tool output in this task, not from a newly inspected archived XML. Final frontend logs were recreated under `C:/Users/ckishor/AppData/Local/Temp/fitigo-payment-phase3`. Treat all raw test logs as private because legacy failure assertions can include disposable fixture tokens.

## Remaining manual acceptance / exact next step

In a separately authorized staging deployment, confirm the configured gateway mode and use the respective provider's sandbox credentials to:
1. Complete one Razorpay and one Cashfree booking; verify their recorded checkout mode/provider and payment history. No provider switching during an attempt.
2. Check dashboard and daily report amounts on the matching scheduled date; verify test scope labels and selected-gym totals. Use isolated seeded reporting fixtures to demonstrate live scope excludes test rows; do not issue a real live charge merely to test a report.
3. Cancel each paid booking: unused access revoked, payment remains PAID, refund_initiated=false, and UI does not claim a refund or wallet credit.
4. With separate explicit refund authorization, initiate a sandbox refund through the original provider dashboard. Reconcile it, repeat the event/refresh, and verify no duplicated refund or false status. Confirm pending/failed/partial refund handling remains conservative.

Exact next step: review this subset's diff and authorize staging deployment/acceptance if desired. Wallet spending, gateway-funded offers, split payments, legacy balance reconciliation and automatic refund initiation remain deferred pending explicit policy and authorization. This subset is not certification of all financial flows or production security.