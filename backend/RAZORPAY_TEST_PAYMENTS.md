# Razorpay checkout integration

## Status and boundaries

Implemented Standard Checkout with backend-created Razorpay orders, HMAC verification, provider status reconciliation, raw-body webhook verification, SQL row locking, and durable idempotency. **Not certified production-ready.** Automated tests use a deterministic gateway or HTTP transport mock; browser tests use an isolated Razorpay fixture. Real Standard Checkout completion and public webhook delivery must be exercised with your own test account before release.

No external funds are moved by automated tests. No application-database migration is automatically applied. Existing booking/payment/membership records remain the business ledger. No new dependency is installed: the gateway adapter uses the existing httpx package.

## Existing architecture reused

- Customer Add-to-Cart and checkout: `frontend/src/pages/booking/BookingPage.tsx`, `CartPage.tsx`, `frontend/src/services/bookingService.ts`, and `backend/app/routers/cart.py`.
- Individual booking creation/confirmation: `backend/app/routers/bookings.py`, `backend/app/services/booking_service.py`, and existing `bookings` / `payments` tables.
- Single membership: `frontend/src/pages/membership/MembershipPage.tsx`, existing authoritative single-plan quote and `user_memberships`.
- Multi membership: `frontend/src/pages/membership/MembershipOrderPage.tsx`, `platform_membership_service.py`, existing `platform_membership_orders`, snapshots, and `user_memberships`.
- QR: existing `BookingAccessService.ensure_records`, booking QR API, My Bookings and `BookingAccess.tsx`. Unpaid/failed/cancelled purchases cannot gain entry. Membership daily-access/pause policies are unchanged.
- Configuration: `backend/app/core/config.py` reads the actual repository-root `.env`, then `backend/.env`. Corrected the previous off-by-one directory calculation.

## Backend environment

Set these only in the ignored root `.env` or backend environment:

```dotenv
ENVIRONMENT=development
RAZORPAY_ENABLED=true
PAYMENT_MODE=test
RAZORPAY_KEY_ID=your_test_key_id
RAZORPAY_KEY_SECRET=your_test_key_secret
RAZORPAY_WEBHOOK_SECRET=your_webhook_signing_secret
RAZORPAY_LIVE_ENABLED=false
```

Use a Key ID beginning `rzp_test_`. Secret values never belong in Vite variables, source code, browser storage, or logs. Only the public Key ID is returned to authenticated checkout owners for Standard Checkout. `PAYMENT_MODE` defaults to `test`; keys must match that mode. Live additionally requires `RAZORPAY_LIVE_ENABLED=true` and `ENVIRONMENT=production`. Switching is never automatic. Disabled integration retains the existing development wallet behavior; selecting Razorpay disables dummy and wallet payment bypasses even if the gateway configuration is incomplete.

Use separate Test and Live databases/configurations. Existing checkout records bind to their mode and public Key ID; changing keys requires an operational reconciliation/key-rotation plan.

## Database migration

Apply Alembic revision `8ad36b7c9e15`, after backing up the application database:

```powershell
Set-Location 'C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend'
& .\.venv\Scripts\python.exe -m alembic upgrade head
```

Adds two orchestration tables, not duplicate payment ledgers:

- `payment_checkouts`: one durable purchase intent, authoritative price/terms snapshot, owner, source/idempotency key, mode, gateway order/payment IDs, status and timestamps.
- `payment_webhook_receipts`: event ID, body hash, event type and processed time. No raw sensitive gateway payloads are stored.

Adds nullable checkout links to `bookings`, `cart_items`, `user_memberships`, and `platform_membership_orders`. Unique constraints prevent duplicate source fulfillment and duplicate gateway payment assignment. Existing payments keep their booking relationship and store provider/status/reference. Memberships retain their payment fields.

Migration upgrade/downgrade is tested on disposable SQLite. Downgrade refuses to proceed while gateway checkout records exist; archive/reconcile explicitly before removing orchestration history.

## API surface (relative to /api/v1)

- `GET /payments/config`: safe enablement and mode, no credentials.
- `POST /payments/checkouts`: `Idempotency-Key` header; strictly accepts one source: CART, BOOKING + booking_id, SINGLE_GYM + gym_id/plan_id/accepted_quote, or MULTI_GYM + existing order_id/accepted_quote. Browser amounts and extra fields are rejected.
- `GET /payments/checkouts`: latest 20 owned checkouts, for recovery after page reload.
- `GET /payments/checkouts/{id}`: local durable status.
- `POST /payments/checkouts/{id}/verify`: Razorpay order ID, payment ID, signature. Signature uses the stored server-side order ID. Fetches provider order/payment before fulfillment.
- `POST /payments/checkouts/{id}/refresh`: provider reconciliation, including interrupted callbacks and order creation.
- `POST /payments/checkouts/{id}/cancel`: cancels an unpaid intent after status reconciliation; does not issue a refund or pretend an in-flight gateway authorization was cancelled.
- `POST /payments/webhooks/razorpay`: signature-checked raw JSON, `X-Razorpay-Signature`, `X-Razorpay-Event-Id`; no customer JWT required.
- Existing `POST /memberships/orders/{id}/payment-session` now delegates to the shared gateway service with `accepted_quote`.
- Existing booking creation, cart Add/Remove, plan catalog/quote, membership-order creation, QR and access endpoints remain in place.

## Local run and Razorpay dashboard setup

1. Configure Test credentials and run the migration above. Restart the backend after configuration changes.
2. Start backend: `& .\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000` from the backend directory.
3. Start frontend: `npm run dev` from `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend`.
4. In the Razorpay Test dashboard, configure automatic capture. Authorized-only payments intentionally remain pending; FitiGo grants access only for verified capture and a fully paid matching order.
5. Register a reachable HTTPS webhook URL ending `/api/v1/payments/webhooks/razorpay`, using the same webhook secret as the backend. Subscribe to `payment.authorized`, `payment.captured`, `payment.failed`, `order.paid`, and `refund.processed`.
6. For localhost delivery use a supported public tunnel or staging host. Razorpay does not deliver directly to localhost and restricts some tunnel domains. Confirm current supported domains in its official webhook documentation.
7. Purchase through the existing cart checkout or membership checkout. The review page must show Test Mode. Test success/failure and close the modal, then use Refresh payment status or recent payments. Confirm correct booking/membership IDs and QR access.

Official references: Razorpay Standard Checkout integration steps, webhook validation/testing, Orders API fetch-all (receipt filtering), and payment capture settings.

## Idempotency and failure behavior

- Same booking/source reuses one checkout and one Razorpay order. Pending cart checkout is resumed across new browser keys. Pending overlapping membership purchases are resumed or blocked before another charge.
- Customer-level and checkout row locks serialize concurrent payment handling. Booking/class/membership writes are atomic; duplicate callbacks and webhook events do not create new access records.
- An ambiguous order-create timeout remains CREATING and is reconciled by receipt. It never blindly submits another external order. If the provider cannot locate the order, it stays pending for manual investigation rather than risking duplicate charge.
- Capture is validated against order ID, amount, currency, captured flag, order amount_paid/amount_due/status. Failed/authorized payments do not activate access.
- If a booking expires, is cancelled, a class fills, or membership eligibility changes during payment, captured funds become REVIEW_REQUIRED. No usable QR or membership is produced. Contact support and refund/reconcile in the Razorpay dashboard; **automatic refunds are not implemented**.
- Cancelling a paid booking revokes access but does not falsely mark gateway funds refunded. Provider refund reconciliation marks full refunds or partial-refund review and revokes access.
- Cart class capacity is checked again under a lock at fulfillment; it is not held while the external payment modal is open. A sold-out class after capture needs manual refund/reconciliation.
- Webhook failures are non-2xx and receipts are committed only after processing. A duplicate ID with different raw payload is rejected. There is no background reconciliation scheduler yet; webhooks and customer refresh perform reconciliation.

## Tests

```powershell
# Backend (disposable SQLite, mocked provider)
& .\.venv\Scripts\python.exe -m pytest tests/test_razorpay_payments.py tests/test_razorpay_migration.py -q

# MySQL concurrency (creates and drops a separate local test database)
$env:FITIGO_MYSQL_PAYMENT_TESTS='1'
& .\.venv\Scripts\python.exe -m pytest tests/test_razorpay_mysql.py -q
Remove-Item Env:FITIGO_MYSQL_PAYMENT_TESTS

# Frontend
npm test
npm run typecheck
npm run build
# With an isolated headless Chrome CDP endpoint at localhost:9231:
node scripts/razorpay-browser.mjs
```

Coverage includes successful booking capture/QR, failure/retry, authorized pending, incorrect amount/currency/order/signature, browser amount injection, ownership, duplicate callback/webhook, out-of-order events, raw-body tampering, interrupted order creation, interrupted callback, cancelled/expired booking late capture, single/multi membership activation once, cart repeat submission, class capacity once, refund revocation, mode guards, bypass rejection, free memberships, transport parameters, migration round-trip, and concurrent MySQL creation/fulfillment. Browser fixtures cover dismissal, failure, retry reuse, interrupted verification, refresh recovery, recent payments, and responsive layouts.

Before production: complete actual Razorpay Test checkout and webhook delivery, operational alerting/reconciliation/refunds, capture configuration checks, account onboarding, key rotation, deployment backups/migration rehearsal, gateway incident/retry policies, and a security review. Automated fixtures alone are not production certification.

## Changed-file manifest

All paths below are absolute. Existing Add-to-Cart UI and QR policy services were inspected and reused, not duplicated.

### Configuration and application wiring
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\.env.example`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\.gitignore`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\core\config.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\main.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\alembic\env.py`

### Backend models, migration and payment implementation
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\alembic\versions\8ad36b7c9e15_razorpay_checkout.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\models\payment_checkout.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\models\booking.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\models\cart.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\models\membership.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\models\platform_membership.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\schemas\payment_checkout.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\routers\payments.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\routers\bookings.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\routers\cart.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\routers\memberships.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\routers\platform_memberships.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\services\razorpay_gateway.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\services\payment_checkout_service.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\services\booking_service.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\services\admin_booking_ops_service.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\services\membership_wallet_service.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\services\platform_membership_service.py`

### Frontend
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\services\paymentService.ts`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\utils\razorpay.ts`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\components\common\GatewayPayment.tsx`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\pages\booking\CartPage.tsx`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\pages\booking\BookingAccess.tsx`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\pages\membership\MembershipPage.tsx`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\pages\membership\MembershipOrderPage.tsx`

### Tests and documentation
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\tests\test_razorpay_payments.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\tests\test_razorpay_migration.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\tests\test_razorpay_mysql.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\tests\test_platform_memberships.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\tests\test_access_service_regressions.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\tests\test_membership_wallet_mysql.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\scripts\razorpay.test.mjs`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\scripts\razorpay-browser.mjs`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\RAZORPAY_TEST_PAYMENTS.md`