# Wallet + gateway funding implementation

## Status and release boundary

**Local release update:** the user subsequently authorized local deployment.
Migration `c35d6fa89157` is now applied locally and the wallet balance display fix
is active. See `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\WALLET_LOCAL_RELEASE.md`
for backup, unchanged-data verification and actual INR 300 available-balance checks.
This supersedes the historical not-deployed/not-migrated statements below only;
Razorpay hold-release limitations and missing real sandbox certification remain.

Implemented in the existing checkout architecture, **not deployed or sandbox-certified**.
The working/customer database has not been migrated. No real recharge, purchase,
cancellation, transfer, provider refund, or webhook delivery was performed.
No credentials or provider configuration were changed. No Git commit/tag was created.

**Remaining requirement gap / release blocker:** automatic release of an expired or
failed Razorpay split checkout is not safely implementable through the current
Razorpay Orders adapter: its order can still accept another payment even when all
observed attempts have failed. The implementation retains its wallet hold, blocks
expired checkout payment/replacement, and exposes
`WALLET_HOLD_REQUIRES_PROVIDER_CLOSURE`. It does NOT pretend local expiry closes an
external order. This can leave funds held pending provider/support resolution.
Therefore the request's “no permanently reserved expired funds” requirement is NOT
fully satisfied for Razorpay. Resolve/test an authoritative terminal-order mechanism
or approve a different product/payment lifecycle before releasing Razorpay split
payments. Do not work around this by deleting holds or marking orders failed locally.

Cashfree termination is reconciled through the existing adapter. Only confirmed
closed-unpaid status with no successful, refunded, or processing payment permits
release. `TERMINATION_REQUESTED`, network errors, and unknown outcomes retain funds.
Genuinely unresolved provider outcomes still require operational attention.

## Existing architecture and reason for the old restriction

- `WalletAccount` remains the single stored wallet balance; `WalletTransaction`
  remains the permanent credit/debit ledger.
- Existing development wallet membership/cart paths explicitly rejected gateway mode.
  They lacked checkout-linked holds and mixed funding allocations. Existing gateway
  checkout amounts and revenue reports assumed full gateway funding.
- Existing `PaymentCheckout`, `PaymentAttempt`, `PaymentWebhookReceipt`, booking
  `Payment`, `Booking`, `UserMembership`, and platform orders are reused.
- Existing Razorpay and Cashfree transport/signature adapters and the environment
  provider selector are unchanged. No new gateway SDK/package was added.

## APIs and amounts

- Added `POST /api/v1/payments/quote`, authenticated, no-store, read-only (transaction
  rolled back). It validates the same source pricing/eligibility as checkout.
- Extended existing `POST /api/v1/payments/checkouts` with `use_wallet` (strict
  boolean, default false) and optional `wallet_amount` (nonnegative Decimal with
  at most two fractional digits). Absence of the amount means maximum eligible use.
- Reused existing checkout status, refresh, verify, cancel, history, and both webhook
  endpoints. Reused wallet balance/history and recharge checkout.
- Returned funding fields: `total_amount`, `wallet_amount`, `gateway_amount`,
  `wallet_status`, wallet transaction ID, and hold deadline. Quotes also return
  ledger, reserved, eligible available balances and an unavailable reason.
- `wallet = min(requested-or-total, available eligible funds, authoritative total)`;
  `gateway = total - wallet`. All calculations use Decimal/exact paise validation.
- `PaymentCheckout.amount` remains the **external gateway amount** consumed by the
  existing adapters. For new split/wallet purchases, funding stores full purchase
  value. `Payment.amount` and membership `paid_amount` retain full purchase value.
  Callers displaying purchase value must use `total_amount`, not the gateway amount.
- Gateway remainder between zero and INR 1 is rejected explicitly; no silent
  adjustment to customer-selected funding. Full wallet payment is allowed.
- Wallet cannot fund a wallet recharge. Non-INR, cross-mode funds, and unreviewed
  legacy funds in live mode are rejected. No new parallel test/live wallet exists.
- Existing source idempotency remains authoritative. Funding choice is fixed once
  created; a changed preference cannot silently mutate an existing external order.

## Database migration

Revision `c35d6fa89157`, parent `b24c5ef78046`:

- `checkout_funding`: one allocation/hold per existing checkout, user, immutable
  purchase/wallet/gateway amounts, currency/mode, hold state, request preference,
  expiry/resolution timestamps, unique link to the eventual existing wallet debit.
- `booking_funding`: per-booking allocation linked to the existing booking and
  checkout funding. Cart allocation is deterministic by booking ID, consuming the
  wallet portion first; all allocation totals are exact.
- Checks enforce nonnegative wallet/gateway amounts and sum equality; foreign keys
  and unique debit linkage preserve identity and auditability.
- These are funding metadata, not duplicate balances/payment/booking/membership ledgers.
  No pre-existing rows are backfilled or changed by the migration.
- Downgrade refuses to remove funding evidence once records exist.
- Migration exercised only on isolated MySQL. Back up, migrate, restart, and validate
  separately during an explicitly approved release. Schema capability is cached per
  engine, so restarting after migration is necessary.

## Wallet protection, verification, and fulfillment

- Serialize by customer row, checkout, wallet row, and current locking reads of
  holds. Available funds equal stored balance minus HELD contributions.
- Reservation does not change the permanent ledger/balance. Successful fulfillment
  performs exactly one OUT/PAYMENT ledger debit and changes HELD to DEBITED in the
  same transaction as booking confirmation/membership activation/QR creation.
- Wallet-only checkout skips external order creation and SDK invocation entirely.
- Razorpay receives only the remainder in paise; confirmation signature, captured
  payment, currency/order ownership, and matching amount are verified as before.
- Cashfree receives only the remainder; existing session checkout, REST status
  verification, and raw-body signature verification are preserved.
- Duplicate callbacks/webhooks/retries cannot create a second wallet debit. Nested
  fulfillment transactions roll back partial writes. Verified fulfillment needing
  retry is reconciled without creating another charge. Closed/released orders cannot
  reactivate purchases; unexpected late captures require review.
- Existing provider binding (provider, environment, account fingerprint) remains;
  changing configuration does not silently switch an in-flight checkout's provider.
- Recovery runs every 60 seconds during ASGI lifespan in independent sessions;
  customer locks allow multiple application processes. A bounded oldest-reviewed
  batch prevents unresolved cases from starving all later holds. Standalone command:
  `python -m app.scripts.recover_wallet_holds` from the backend directory.
- Review failures/unknown outcomes remain held and visible. Operational monitoring
  and sandbox provider closure testing remain release requirements; there is no
  durable recovery-worker heartbeat or privileged manual-resolution UI.
- Recharge refunds cannot consume another checkout's hold or overdraw a wallet.
  Insufficient reversal funds preserve external refund evidence, flag
  `WALLET_REFUND_RECONCILIATION`, and block wallet spending until reconciliation.
  Existing negative historical balances are not silently rewritten.

## Cancellation and reporting

- Existing IST three-hour cutoff, eligibility, locking, and unique cancellation
  credit remain unchanged. Memberships remain non-cancellable by customers.
- Verify full purchase allocation, gateway success evidence, currency/mode, and the
  original committed wallet debit before crediting the refundable booking amount.
  A verified INR 40 + INR 110 booking credits INR 150 once, never a gateway refund.
- Preserve original debit, gateway attempts, booking payment, and cancellation audit.
- A separate provider refund of a split purchase is partial funding recovery, not
  a full-purchase refund: it is reviewed, access revoked, and no automatic second
  wallet benefit is granted.
- Admin gateway totals and owner existing recognized-gateway projections use only
  gateway allocations, with their existing date/check-in/mode eligibility filters.
  Owner transactions and admin/owner booking details expose full purchase, wallet,
  and gateway amounts. No recharge is counted again as booking gateway collection.
- Wallet history exposes ledger balance, available/reserved funds, references and
  hold/release/debit states separately. Holds are not presented as extra permanent
  charges. Payment history exposes the funding breakdown and linked purchases.

## Frontend

The shared payment component covers direct gym bookings, gym/class cart items,
Single-Gym and Multi-Gym membership checkout. Recharge stays gateway-only.
Wallet is opt-in, zero eligible balance is disabled with an explanation, maximum
eligible use is default when enabled, and a lower optional amount is supported.
Quote updates are server-backed; payment is disabled while calculating. No browser
wallet balance, discount, total, or payment-success assertion authorizes a purchase.
Existing fonts, shared cards/buttons, theme and layouts are reused; no maps changes.

## Verification

Final full-suite result: **877 passed, zero failed**, in 808.43 seconds. The isolated
runner exited 0 and stopped its owned MySQL server. The suite reported 34,011
warnings, predominantly existing `datetime.utcnow()` deprecations; passing tests
do not imply warning-free code or real-provider acceptance.
Final log:
`C:\Users\ckishor\AppData\Local\Temp\fitigo-isolated-b596474cd81c5ff1-8_vtlcc9\pytest.log`.
Migration log and JUnit `results.xml` are in the same private run directory.

Commands executed (backend working directory:
`C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend`):

```powershell
.\.venv\Scripts\python.exe scripts\run_isolated_tests.py --mysql-bin 'C:\Program Files\MySQL\MySQL Server 26.7\bin\mysqld.exe' --test-timeout 3600 tests -q
```

Frontend working directory:
`C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend`:

```powershell
npm test
npm run typecheck
npm run build
node scripts\split-payment-browser.mjs
node scripts\checkout-recovery-browser.mjs
node scripts\razorpay-browser.mjs
```

Existing recovery browser suites were also run with
`FITIGO_TEST_REPLACEMENT=1` and `FITIGO_TEST_PROVIDER=cashfree`, respectively, in
separate isolated browser contexts on debugging port 9231. All API/payment SDK
requests were mocked. Syntax/file verification checked all 52 listed source/test
files for existence, nonempty contents, conflict markers, Python AST parsing and
the four browser/unit script syntax checks.
Prior checkpoint: 857 backend tests passed. A later full run had 875 passed / 2
failed (Cashfree timeout mock flag and outdated readiness expectation); both were
corrected rather than hidden. Final targeted payment run: **62 passed** in 189.93s.
All new split scenarios run on disposable MySQL schemas with mocked providers;
real InnoDB races cover distinct purchases sharing funds and concurrent fulfillment.

Frontend: **447 tests passed**, TypeScript passed, production build passed.
Mocked browser checks passed for split Razorpay/Cashfree, wallet-only, zero funds,
custom contribution, 320/390/768/1440 widths; existing Razorpay/Cashfree membership
recovery and current-cart/replacement checks also passed. No live SDK payment or
provider-delivered webhook was used.

Covered: zero/40/150/200 wallet balances against 150 purchase; opt-out; lower amount;
both providers; pending/failure/success; duplicate callbacks/retries; current cart
and class fulfillment; hold expiry and unresolved Razorpay state; delayed results;
creation timeout; recoverable fulfillment; full cancellation credits/idempotency;
mode separation; membership activation; pre-payment QR denial; ledger reconciliation;
nonnegative recharge refund handling; migration preservation and downgrade refusal.

## Manual sandbox/release acceptance still required

1. Real Razorpay and Cashfree sandbox purchases: gateway-only, wallet-only, split,
   lower contribution, and each eligible purchase type. Compare provider charged
   amount with the server remainder and database allocations.
2. Actual signed webhook delivery (success, failure, duplicates, delayed delivery),
   callback interruption, page close, backend restart, provider/API timeouts.
3. Cashfree termination and TERMINATION_REQUESTED races; resolve the documented
   Razorpay still-payable-order expiry/release blocker before release.
4. Approved test-account cancellation and wallet history/revenue reconciliation;
   do not mutate customer records for acceptance testing.
5. Recovery-worker operation/alerts and a documented support escalation procedure
   for captured-but-unfulfillable orders, unknown order creation, external refunds,
   missing/rotated original provider credentials, and long-held funds.
6. Backup/restore rehearsal, approved working-database migration, backend restart,
   frontend deployment, and sandbox/live isolation checks.

This report is not a claim of successful real payment integration or production readiness.

## Files modified / added

All paths below are absolute. Existing provider adapters, environment files, and
maps files were not modified for this task.

### Backend

- C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\main.py
- C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\models\__init__.py
- C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\models\checkout_funding.py (new)
- C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\alembic\versions\c35d6fa89157_checkout_funding.py (new)
- C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\schemas\payment_checkout.py
- C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\schemas\wallet.py
- C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\schemas\admin_booking.py
- C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\schemas\booking_owner.py
- C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\routers\payments.py
- C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\routers\wallet.py
- C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\routers\cart.py
- C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\routers\admin.py
- C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\services\checkout_funding.py (new)
- C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\services\payment_quote.py (new)
- C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\services\wallet_hold_recovery.py (new)
- C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\scripts\recover_wallet_holds.py (new)
- C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\services\payment_checkout_service.py
- C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\services\wallet_gateway_service.py
- C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\services\membership_wallet_service.py
- C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\services\booking_cancellation.py
- C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\services\customer_payment_history.py
- C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\services\admin_revenue.py
- C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\services\admin_dashboard_service.py
- C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\services\admin_analytics_service.py
- C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\services\owner_revenue.py
- C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\services\owner_dashboard_service.py
- C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\services\owner_analytics_service.py
- C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\services\owner_booking_policy.py
- C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\services\readiness_service.py
- C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\tests\test_split_payment.py (new)
- C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\tests\test_split_payment_mysql.py (new)
- C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\tests\test_wallet_gateway_history.py
- C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\tests\test_support_workflows.py

### Frontend

- C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\components\payments\WalletFunding.tsx (new)
- C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\components\common\GatewayPayment.tsx
- C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\services\paymentService.ts
- C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\services\accountService.ts
- C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\screens\Checkout\api.ts
- C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\screens\Admin\api.ts
- C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\screens\GymOwner\api.ts
- C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\pages\booking\CartPage.tsx
- C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\pages\wallet\WalletPage.tsx
- C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\pages\profile\PaymentHistory.tsx
- C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\admin\Bookings.tsx
- C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\owner\Bookings.tsx
- C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\owner\Analytics.tsx
- C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\owner\analyticsService.ts
- C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\utils\checkoutRecovery.ts
- C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\scripts\split-payment.test.mjs (new)
- C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\scripts\split-payment-browser.mjs (new)
- C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\scripts\checkout-recovery-browser.mjs
- C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\scripts\razorpay-browser.mjs

Verification artifacts: C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\split-unit-results.txt
and C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\split-build-results.txt.