# Customer wallet recharge, payment history and account editing

## Gateway-only history and discounted-order recovery correction

Payment history now includes only Razorpay/Cashfree purchases, including gateway
wallet recharges. Wallet spending, MVP top-ups, free purchases and wallet-only
membership payments are excluded; they remain in the separate wallet ledger.
The backend filters before pagination. Unlinked legacy gateway payments remain
visible, but wallet/DUMMY rows do not. This supersedes broader history descriptions
below. Unpaid history rows expose a direct Cancel unpaid payment action.

The two stuck local Cashfree sandbox orders were already PAID at the provider:
the INR 500 recharge had a successful INR 450 payment, and the INR 150 cart had
a successful INR 100 payment. Both had a provider-reported INR 50 offer. Exact
amount verification was correctly preventing fulfillment, but throwing on every
refresh also prevented the local intent from leaving PENDING.

Reconciliation now stores observed attempts and records successful/refunded
amount mismatches as REVIEW_REQUIRED / PAYMENT_AMOUNT_MISMATCH. No wallet credit,
membership or booking access is granted, and a paid order is never labelled
cancelled. Those reviewed intents no longer block new carts/recharges. Failed or
pending attempts with a different attempted amount can be recorded without
blocking a later matching successful payment or safe unpaid cancellation.
Order identity and currency mismatches still fail closed. A provider-paid order
with temporarily missing successful payment details also requires review rather
than being cancelled. Transport failures do not create replacement charges.

The existing two local sandbox checkouts were refreshed through the running API:
both returned HTTP 200 with REVIEW_REQUIRED; their real transaction amounts are
stored, the wallet balance is unchanged, and no pending cart/top-up blockers
remain for the affected customer. No refund/charge was initiated. Provider offers
that alter payment amounts remain unsupported for fulfillment; remove the INR 50
offer from the Cashfree sandbox configuration before making a fresh test payment,
or implement a separately agreed promotion/accounting policy. Do not bypass the
amount check or retry the already-paid orders.

## Local deployment repair

The local development `fitigo` database has now been upgraded from
`9be47c8d0f26` to `acf58d9e1037`. Earlier statements below that the migration was
unapplied describe the original handoff, not the current local database.

The first migration attempt found 11 pre-existing wallet ledger records with
missing user references and stopped after adding the nullable columns. The
migration now detects completed steps so partial MySQL DDL can be resumed.
For this local repair only, the new checkout FK was added on a dedicated
connection after verifying every checkout link was NULL; that connection's
foreign-key checks were immediately restored. No global SQL settings changed.
Orphan records were not deleted or reassigned. They need separate data cleanup.

All original values in 11 wallet accounts and 44 ledger rows were compared with
the pre-migration backup and preserved. Backup (contains private ledger data;
keep outside version control):
`C:/Users/ckishor/AppData/Local/cline/backups/fitigo-wallet-20261027-062334/wallet-before-migration.json`.

Authenticated requests through the running frontend proxy returned HTTP 200 for
wallet balance, wallet transactions and payment history. Migration/recharge
regressions: 16 passed, including fresh/partially applied migration cases.

## Implemented

- `/wallet/recharge` uses the existing shared GatewayPayment component and
  configured Razorpay/Cashfree adapter. It creates `WALLET_TOPUP` through the
  existing POST `/api/v1/payments/checkouts` with an idempotency key and a validated
  INR amount (1–100000, at most two decimal places).
- Wallet credit occurs only during verified checkout fulfillment. User/account
  row locking and a unique ledger checkout link prevent repeated credits from
  browser retries, concurrent requests, callbacks or duplicate webhooks.
- Unpaid attempts resume the same recharge. Changing amount while an unpaid
  recharge exists requires resolving/cancelling it first. Closing checkout does
  not prove failure. Late payment after cancellation requires review, not credit.
- The old POST `/api/v1/wallet/topup` now returns 409, directing callers to gateway
  checkout. It cannot mint development credits in any environment.
- Provider refunds reverse only the incremental refunded amount, once. If money
  was already spent, the wallet can become negative rather than retain free
  credits. No automatic external refund initiation was added. Partial refunds
  retain REVIEW_REQUIRED checkout status and exact observed refunded amount in
  attempt history.
- `/profile/payments` shows paginated customer-only purchases and legacy wallet
  ledger rows. Filters: purchase type and status. Details include internal/order/
  transaction IDs, linked bookings/memberships, wallet entries, payment attempts,
  observed refunds, timestamps and review codes. No secrets or checkout sessions.
- History shows both test/live purchases, labeled individually. Gateway carts are
  one purchase with booking allocations, not duplicated as individual charges.
  Legacy wallet payments and purchase rows can both appear as distinct ledger
  movements; the UI does not sum these as additional charges.
- Membership-covered check-ins are access history, not invented payment rows;
  the page links to check-in history. Historical failed attempts cannot be
  reconstructed from absent records. Refresh reconciles available provider
  attempts; first_seen_at is explicitly an observation time, not payment time.
- `/settings` provides first/last name, email and phone editing and the existing
  change-password form. PATCH `/api/v1/users/me` rejects unexpected privilege
  fields, validates inputs, handles uniqueness conflicts and rate-limits requests.
- Contact changes require the current password, reset changed verification flags,
  revoke refresh/reset tokens, increment token version and require sign-in again.
  Name-only edits retain sessions. Password change reuses `/auth/change-password`.

## Important boundaries

**Contact ownership verification is not implemented by the existing OTP delivery
stack.** Its email/SMS send functions do not deliver messages. This change does
not pretend those contacts are verified. Contact edits are password-authorized
but saved unverified; production verification should be implemented with a real
delivery provider and pending-contact confirmation workflow before relying on
contact verification. OTP-only accounts need password recovery first; password
recovery requires the existing SMTP configuration. No new credentials or flags.

**Gateway-funded recharge is not a new wallet-spending checkout flow.** Existing
rules that disable wallet-funded booking/membership purchase when gateway mode is
selected were intentionally preserved. Enabling wallet spending with gateway
payments is a separate business-flow change; do not advertise live recharges for
spending until that policy is confirmed. No live wallet/payments certification.

Test/live credits must not mix. The wallet is bound to the mode of its first
gateway recharge. A different mode is rejected. Existing nonzero unclassified
MVP balances may bind only to test; live requires explicit balance reconciliation.
Existing balance values are never silently converted or deleted.

## Migration — required before running the changed backend

Revision `acf58d9e1037` follows `9be47c8d0f26`:
- Nullable `wallet_accounts.payment_mode` (existing configuration value, not a new flag).
- Nullable unique `wallet_transactions.checkout_id` FK to existing checkouts.
- `payment_attempts`: checkout/external payment ID, status, amount/currency,
  observed refunded amount, first-observed and updated timestamps.

Existing rows/balances are retained. Downgrade blocks removal when gateway wallet
or attempt history exists. The migration has **not been applied to the application
database** by the coding agent. Back up, then:

```powershell
Set-Location 'C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend'
python -m alembic upgrade head
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

No new package installation is necessary. Use existing PAYMENT_GATEWAY,
PAYMENT_ENV/PAYMENT_MODE and provider credentials/webhook setup. Actual sandbox
payments and public webhook delivery still require testing with your credentials.

## API additions/changes

- Existing checkout create accepts `{kind: "WALLET_TOPUP", amount: "500.00"}`.
- Existing verify/refresh/cancel/webhook endpoints handle recharges.
- GET `/api/v1/payments/history?limit=20&offset=0&kind=WALLET_TOPUP&status=PAID`.
  Authenticated customer only, no-store, server-side filters/pagination.
- PATCH `/api/v1/users/me`: first_name, last_name, email, phone, optional
  current_password (required for changed contact details). Returns user and
  reauthenticate boolean; never password hashes or authentication secrets.
- GET `/api/v1/users/me` also reports email/phone verification status.
- POST `/api/v1/wallet/topup`: rejects direct credits with HTTP 409.

## Validation commands

```powershell
Set-Location 'C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend'
$env:FITIGO_MYSQL_PAYMENT_TESTS='1'
python -m pytest tests/test_wallet_gateway_history.py tests/test_customer_profile_edit.py tests/test_password_recovery.py tests/test_wallet_history_migration.py tests/test_razorpay_payments.py tests/test_cashfree_payments.py tests/test_razorpay_mysql.py -q --disable-warnings
Remove-Item Env:FITIGO_MYSQL_PAYMENT_TESTS
Set-Location 'C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/frontend'
npm.cmd test
npm.cmd run typecheck
npm.cmd run build
# With Vite and isolated Chrome DevTools on 9231:
node 'C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/frontend/scripts/customer-account-browser.mjs'
```

MySQL tests use isolated, automatically dropped databases, not the application
database. Browser fixture passed wallet gateway confirmation, history IDs/refund
details/filtering, profile save, password form and 360/768/1440px overflow checks.
No real funds were moved. See final handoff for final regression counts.

Final verification: **194 backend tests passed, pytest exit 0**, including wallet,
profile/password, migration, Razorpay/Cashfree, MySQL concurrency, owner analytics,
date reports and booking QR regressions. **357 frontend tests passed**, typecheck
and production build passed. Python compileall and git diff checks passed.
The complete unrelated backend suite was not run. Existing deprecation warnings
remain. The full customer browser fixture passed with mocked API/SDK responses.

## Main files

- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend/alembic/versions/acf58d9e1037_wallet_gateway_history.py`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend/app/models/wallet.py`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend/app/models/payment_checkout.py`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend/app/services/payment_checkout_service.py`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend/app/services/wallet_gateway_service.py`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend/app/services/customer_payment_history.py`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend/app/routers/payments.py`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend/app/routers/wallet.py`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend/app/routers/users.py`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend/app/schemas/payment_checkout.py`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend/app/schemas/user.py`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/frontend/src/pages/wallet/WalletPage.tsx`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/frontend/src/pages/profile/PaymentHistory.tsx`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/frontend/src/pages/profile/SettingsPage.tsx`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/frontend/src/pages/profile/ProfilePage.tsx`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/frontend/src/pages/CustomerApp.tsx`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/frontend/src/customerRoutes.ts`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/frontend/src/services/accountService.ts`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/frontend/src/services/paymentService.ts`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/frontend/src/components/common/GatewayPayment.tsx`

Tests are in the backend files named in the commands above (plus the updated
MySQL concurrency fixture), and
`C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/frontend/scripts/customerAccount.test.mjs`
and `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/frontend/scripts/customer-account-browser.mjs`.