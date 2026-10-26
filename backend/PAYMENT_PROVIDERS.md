# FitiGo payment providers — deployment and verification

## Status and boundaries

Extends the existing Razorpay checkout rather than rebuilding it. No real payment
has been made during implementation. Automated provider responses are mocked.
Real Cashfree/Razorpay sandbox completion and public webhook delivery remain a
release gate. Do not interpret passing mocked tests as production certification.

The application database was **not migrated**. Migration is an explicit operator
step below. New MySQL concurrency tests create and drop their own isolated database.
Some older repository tests use the configured database; do not run the entire
backend suite against a production database.

## Architecture inspected and retained

- Python 3.12; FastAPI 0.115.0, Pydantic 2.8.2, SQLAlchemy 2.0.32,
  Alembic 1.13.2, httpx 0.27.0. Backend entry point:
  `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend/app/main.py` (`app`).
- React 18.3.1, TypeScript ^5.5.4, Vite ^6.0.0 (installed build: 6.4.3).
  Frontend entry point:
  `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/frontend/src/main.tsx`.
- Existing routers → services → SQLAlchemy models/repositories remain in place.
  No new runtime Python/npm dependency is required. Cashfree uses existing httpx
  on the server and the official hosted JavaScript v3 SDK in the browser.
- Individual bookings retain backend slot pricing and pending booking/payment
  rows. Cart retains server-priced gym/class entries, visitors, and capacity checks.
- Single-Gym purchases retain plan quotes and eligibility; Multi-Gym purchases
  retain offers, quote acceptance, platform orders, and membership snapshots.
- The same checkout service serializes purchases using customer/checkout row locks.
  Its existing fulfillment transaction confirms bookings, records paid status,
  and invokes the existing booking QR service; membership fulfillment creates one
  linked membership. Pauses, daily access and scanner policies were not modified.
- Browser SDK results only trigger authenticated backend verification. Webhooks
  and refresh use the same reconciliation/fulfillment path. Failure/pending status
  cannot activate access. A payment received after local cancellation/expiry or
  lost eligibility becomes `REVIEW_REQUIRED`, not usable access or a fake refund.
- Provider adapters own external request/response and signature details.
  Existing Razorpay transport/signatures are wrapped. Existing API response fields
  are preserved, with provider/environment/session fields added for Cashfree.

## Environment

Use server environment or the ignored file
`C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/.env`.
The backend-local `.env`, if present, takes precedence over the root file.
Never use VITE_ variables for API/webhook secrets, commit secrets, or log raw
provider requests/responses. Protect DB backups containing checkout sessions.

Common:

```dotenv
PAYMENT_GATEWAY=razorpay
PAYMENT_ENV=sandbox
PAYMENT_RETURN_URL=http://localhost:5173/checkout
```

`PAYMENT_GATEWAY`: `razorpay` or `cashfree`. Explicit selection enables gateway
checkout regardless of the legacy RAZORPAY_ENABLED flag. No failure fallback.
`PAYMENT_ENV`: `sandbox` or `production`. When omitted, legacy PAYMENT_MODE
(`test` default / `live`) is honored. Conflicting explicitly supplied old/new modes
fail startup. Remove PAYMENT_MODE when adopting PAYMENT_ENV.

For backward compatibility, omitting PAYMENT_GATEWAY retains RAZORPAY_ENABLED:
true selects Razorpay; false retains existing development-only wallet/dummy
behavior. Explicitly selecting either provider disables those bypasses even when
its credentials are missing. The updated example opts into verified Razorpay and
therefore requires credentials before startup.

Razorpay required:

```dotenv
RAZORPAY_KEY_ID=
RAZORPAY_KEY_SECRET=
RAZORPAY_WEBHOOK_SECRET=
RAZORPAY_LIVE_ENABLED=false
```

Use the dashboard's actual values. Sandbox requires an rzp_test_ key; production
requires rzp_live_, RAZORPAY_LIVE_ENABLED=true, and ENVIRONMENT=production.

Cashfree required when selected:

```dotenv
CASHFREE_CLIENT_ID=
CASHFREE_CLIENT_SECRET=
CASHFREE_API_VERSION=2026-01-01
```

PAYMENT_RETURN_URL is the existing frontend checkout page, not a webhook or proof
of payment. Set its actual HTTPS origin in production. Cashfree requires a valid
customer phone; missing/invalid profile phones are rejected before a durable
checkout is committed. Existing free purchases stay free; nonzero amounts below
INR 1 are rejected without creating an external order.

Production additionally requires:

```dotenv
ENVIRONMENT=production
DEBUG=false
PAYMENT_ENV=production
```

There are no configurable API host overrides: Cashfree sandbox and production
hosts are fixed by backend configuration. Production startup makes a read-only
GET for a random nonexistent order on the production API. Only an authenticated
order-not-found response is accepted; authentication errors, unexpected responses
and timeouts fail startup. This prevents sandbox credentials from silently being
used in production without guessing undocumented key prefixes. Production
startup consequently needs Cashfree connectivity. This guard is mocked in tests;
validate it with your actual account before launch.

Keep sandbox and production in separate deployments/databases/secret stores.
Changing mode or merchant credentials cannot reuse existing checkout sessions.

## Switching providers

Set PAYMENT_GATEWAY=cashfree (or razorpay) and restart the backend. No UI/code
change and no customer gateway-selection screen are needed. New purchases use
the selected provider. Existing purchases remain bound to their persisted provider,
environment and account fingerprint/public key. Keep both providers' credentials
and webhook endpoints available until old purchases/refunds are reconciled.
An outstanding purchase resumes its original provider instead of creating a
second charge after a configuration switch. Missing old credentials fail clearly.

## API compatibility

All paths below use the default `/api/v1` prefix:

| Method | Path | Behavior |
|---|---|---|
| GET | /api/v1/payments/config | Active provider, environment, legacy mode, availability |
| POST | /api/v1/payments/checkouts | Existing source IDs + Idempotency-Key; server price only |
| GET | /api/v1/payments/checkouts | Owner's recent checkouts, including previous provider |
| GET | /api/v1/payments/checkouts/{id} | Local status (no external side effect) |
| POST | /api/v1/payments/checkouts/{id}/verify | Existing signed Razorpay payload; Cashfree uses `{}` |
| POST | /api/v1/payments/checkouts/{id}/refresh | Reconcile existing order; recover lost create response |
| POST | /api/v1/payments/checkouts/{id}/cancel | Reconcile first, then cancel unpaid local purchase |
| POST | /api/v1/payments/webhooks/razorpay | Existing signature/event ID contract |
| POST | /api/v1/payments/webhooks/cashfree | New timestamp + raw-body signature endpoint |

Customer routes retain existing authentication/ownership and no-store headers.
Membership quote/order payment_mode may now be CASHFREE as well as RAZORPAY.
Cashfree returns payment_session_id, not client credentials. The frontend polls
refresh for pending checkouts and provides explicit refresh/recent-payment recovery.
No status timeout creates another order or automatically charges a customer.

Cashfree order IDs are `fitigo_` + internal checkout UUID without hyphens (39 chars).
Create calls use that UUID as x-idempotency-key. After an ambiguous response,
reconciliation GETs that same external order; it never blindly creates another one.
An unknown order remains CREATING for operator investigation. Cancelled external
sessions may still settle; the existing review-required safeguard blocks access.

## Migration

Revision `9be47c8d0f26` follows `8ad36b7c9e15`:

- Adds non-null payment_checkouts.provider with RAZORPAY server default, preserving
  all existing rows and permitting the old application to keep inserting rows.
- Adds nullable JSON checkout_data for payment session/public checkout state.
- Reuses existing amount/currency/status/order/payment ID/timestamp columns and
  payment_webhook_receipts; adds no parallel business ledger or membership table.
- Downgrade refuses to discard Cashfree history. Do not roll back to an old binary
  that cannot understand Cashfree while Cashfree purchases remain unresolved.

Back up first, then run against the intended deployment database:

```powershell
Set-Location 'C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend'
python -m alembic current
python -m alembic upgrade head
```

## Dashboard and webhook setup

Substitute your actual public API origin; these are exact path suffixes, not
invented deployed domains:

```text
https://YOUR_API_HOST/api/v1/payments/webhooks/razorpay
https://YOUR_API_HOST/api/v1/payments/webhooks/cashfree
```

Use distinct sandbox and production origins/deployments with matching credentials.
For local sandbox work expose the backend through a trusted HTTPS tunnel; do not
expose development debug pages or use production credentials.

Cashfree:
1. Open the Payment Gateway dashboard in the desired environment and generate
   PG API credentials. Configure them only on that backend.
2. Whitelist the actual frontend domain and set PAYMENT_RETURN_URL accordingly.
3. In Developers → Webhooks, add the public Cashfree endpoint. Enable payment
   success, failure and user-dropped notifications, and refund status if using
   dashboard refunds. Use the dashboard's supported payment-webhook version;
   REST x-api-version is a separate setting, not an assumed webhook version.
4. Preserve x-webhook-signature and x-webhook-timestamp through your proxy. Verify
   the Base64 HMAC-SHA256 of timestamp + original body using that environment's
   Cashfree client secret. Do not parse/re-serialize before verification.
5. Test delivery, inspect dashboard response codes, and ensure retries work.
   Invalid signatures return 400; oversized bodies return 413; transient provider
   failures are not acknowledged as success. Replays cannot grant access twice.

Razorpay:
1. Configure the Razorpay endpoint separately in each dashboard mode.
2. Set a dedicated webhook signing secret matching RAZORPAY_WEBHOOK_SECRET.
3. Subscribe to payment.captured, payment.authorized, payment.failed, order.paid,
   and refund.processed. Preserve X-Razorpay-Signature and X-Razorpay-Event-Id.
4. Preserve the existing automatic-capture setup: authorized-only is not paid.

Neither adapter initiates refunds. Dashboard refunds are fetched/reconciled and
access is revoked; local cancellation never pretends a provider refund occurred.

Cashfree dashboard payment surcharges/extra discounts must be disabled for this
integration: FitiGo requires the payment amount and currency to exactly match its
authoritative quote. An unexpected provider-adjusted amount fails closed instead
of silently changing the customer's purchase price.

## Verification results (October 26, 2026)

- Targeted payment/configuration/migration suite plus both providers' isolated
  MySQL concurrency cases: **77 passed**, pytest exit code **0**.
- Frontend Node tests: **347 passed**. TypeScript typecheck and Vite production
  build passed. Python compileall and Alembic single-head inspection passed.
- Mocked Chrome browser checkout tests passed for **both** Razorpay and Cashfree.
- Full backend run before the final three added Cashfree cases: **313 passed,
  17 failed, 7 skipped**. Failures include clock-dependent booking fixtures
  (`BOOKING_TIME_PASSED`) and legacy membership quote fixtures
  (`MEMBERSHIP_PRICE_CHANGED`). The complete repository suite is not green.
  These tests were not rewritten or business rules relaxed to hide failures.
- Actual provider network payments, actual sandbox checkout, production
  credential probing, and public dashboard webhook delivery were **not tested**.
- Application migration was not applied. Full-suite legacy DB tests can create
  local test records; the targeted payment tests use disposable databases.
- Existing deprecation warnings remain (notably datetime.utcnow and Pydantic).

Review the accompanying file manifest for every created/modified file.

## Install, run and automated tests

```powershell
Set-Location 'C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend'
python -m pip install -r 'C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend/requirements.txt'
# Configure the root .env using the example; do not overwrite existing secrets.
python -m pytest tests/test_razorpay_payments.py tests/test_cashfree_payments.py tests/test_payment_configuration.py tests/test_razorpay_migration.py tests/test_cashfree_migration.py -q
# Optional: requires local MySQL CREATE/DROP DATABASE permission; isolated DB only.
$env:FITIGO_MYSQL_PAYMENT_TESTS='1'
python -m pytest tests/test_razorpay_mysql.py -q
Remove-Item Env:FITIGO_MYSQL_PAYMENT_TESTS
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

In another terminal:

```powershell
Set-Location 'C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/frontend'
npm.cmd ci
npm.cmd test
npm.cmd run typecheck
npm.cmd run build
npm.cmd run dev
```

Browser fixtures use the existing Chrome DevTools harness, not real SDK payments.
Start a separate headless Chrome profile with remote debugging on port 9231 and
Vite on port 5173, then:

```powershell
Set-Location 'C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/frontend'
node 'C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/frontend/scripts/razorpay-browser.mjs'
$env:FITIGO_TEST_PROVIDER='cashfree'
node 'C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/frontend/scripts/razorpay-browser.mjs'
Remove-Item Env:FITIGO_TEST_PROVIDER
```

## Manual sandbox acceptance (required before release)

Use your own real sandbox credentials and only Cashfree/Razorpay's documented
test instruments. Do not use real cards in sandbox or invent test credentials.

For each of Single-Gym, Multi-Gym (including discounts), individual booking,
cart/class and booking-for-others:

1. **Success:** record expected backend price and checkout ID; pay in sandbox.
   Verify server PAID status, one membership or expected booking(s), correct
   transaction/provider, and exactly one visitor pass per paid visitor.
2. **Failure:** select the sandbox failure outcome. Verify no membership/QR;
   retry the same checkout, confirm the same external order and no extra booking.
3. **Dismissal:** close the modal. Verify no activation; refresh before retrying.
   Closing a browser is not proof that a payment failed.
4. **Pending/delayed:** use a documented asynchronous sandbox flow when available;
   otherwise reproduce with the transport tests. Verify no access while pending,
   then process a later success and activate once. Do not claim a real pending
   scenario was tested if the sandbox method cannot simulate it.
5. **Leave checkout:** complete a payment then close the page before callback.
   The webhook must fulfill it; reopen recent payments and refresh. Temporarily
   delay webhook delivery in sandbox and verify manual refresh independently.
6. **Duplicate/out-of-order:** resend a signed webhook through dashboard logs,
   including an earlier failure after success. Membership/booking/visit/QR counts
   must not increase. A tampered raw body or timestamp must be rejected.
7. **Timeout:** interrupt the order-create response in a controlled sandbox proxy.
   Refresh must recover the original order, never create another charge. Missing
   external orders stay CREATING for manual reconciliation.
8. **Late payment/cancellation:** cancel locally before a delayed success. Expect
   REVIEW_REQUIRED, no new access, and a support/refund reconciliation action.
9. **Configuration:** switch the selected provider; confirm new purchases use it
   and old payments still reconcile through their original provider. Attempt
   production with sandbox credentials in a controlled deployment: startup must
   fail, with no payment creation. Never test this against real customers.

## Official references checked on October 26, 2026

```text
https://www.cashfree.com/docs/api-reference/payments/latest/orders/create-order
https://www.cashfree.com/docs/api-reference/payments/latest/payments/get-payments-for-an-order
https://www.cashfree.com/docs/api-reference/payments/latest/refunds/get-all-refunds-for-an-order
https://www.cashfree.com/docs/payments/online/web/redirect
https://www.cashfree.com/docs/payments/online/webhooks/signature-verification
https://www.cashfree.com/docs/payments/online/webhooks/configure
https://www.cashfree.com/docs/payments/online/webhooks/webhook-indempotency
```