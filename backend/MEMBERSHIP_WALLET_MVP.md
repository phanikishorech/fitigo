# Controlled wallet-only membership MVP

## Current scope

Both Single-Gym and Multi-Gym membership checkout use the existing wallet_accounts / wallet_transactions ledger. A shared service performs wallet debit, PAYMENT ledger insertion and ACTIVE/PAID membership creation in one transaction. No external payment provider, bank/card charge, automatic renewal or refund workflow is enabled. Membership pause is now supported through backend-configured policy; see MEMBERSHIP_PAUSE.md.

The backend permits this checkout only when `settings.environment == 'development'`. Every checkout displays **Test credits only**. These are not verified real-money funds. Do not expose this development environment to untrusted/public users. Changing frontend build mode does not bypass the backend gate.

Wallet top-up now requires a valid active identity and is rejected outside development. Read wallet endpoints no longer fall back to a development user. Existing day-visit cart checkout is otherwise unchanged.

## Use the MVP

1. Admin signs in and opens **Gyms → a gym → Multi-Gym participation → Enable Multi-Gym Access**. Backend requires an approved, active gym. Nothing is automatically enrolled.
2. Customer adds **development test credits** using the existing Wallet recharge screen. No real funds are collected.
3. Multi-Gym: Memberships → Multi-Gym Plans → Choose Plan → review current price and wallet balance → Pay with Wallet → Confirm Wallet Payment.
4. Single-Gym: Gym Details → View Membership Plans → select plan → Continue → same wallet confirmation UI.
5. Successful backend activation redirects to My Membership. Multi-Gym records show purchased plan details and period; gym selection and QR scan use partner eligibility.

There are currently zero automatically enabled partner gyms. Until an admin opts in at least one eligible gym, Multi-Gym purchase fails with NO_ELIGIBLE_PARTNER_GYMS without a debit.

## Contracts

- GET `/api/v1/memberships/gyms/{gym_id}/plans/{plan_id}/wallet-quote`: strict CUSTOMER identity, current plan terms, quote fingerprint, wallet balance/currency and backend payment capability; no-store.
- POST `/api/v1/memberships/gyms/{gym_id}/purchase`: now requires `plan_id`, `accepted_quote`, and `Idempotency-Key`. The previous plan-ID-only dummy activation is removed. Unknown fields are rejected.
- Existing platform order creation still accepts only plan_id and an idempotency key. GET order returns current terms, quote_token, wallet balance/currency and payment_available.
- POST `/api/v1/memberships/orders/{order_id}/pay-wallet`: owning active CUSTOMER sends only accepted_quote. Order ID is the payment idempotency reference.
- Existing `/payment-session` remains blocked with PAYMENT_NOT_CONFIGURED.
- GET/PUT `/api/v1/admin/gyms/{gym_id}/multi-gym-participation`: admin-only read/update of `{enabled: boolean}`. Enrollment does not override suspension/approval/active status.

accepted_quote is a server-produced SHA-256 fingerprint of canonical current terms, not a secret and not a client-selected price. Payment re-reads locked plan/offer state, recomputes pricing and rejects a different fingerprint with MEMBERSHIP_PRICE_CHANGED. Customer must refresh and explicitly accept again. No client amount is trusted. Retries of an already completed transaction return the original membership without another debit.

## Persistence and transaction behavior

Migration `4c9f2d3e5a71` follows `3b8e1c2d4f60`. Existing user_memberships gain explicit type, optional platform plan reference, nullable gym/Single-Gym plan references, purchased terms snapshot, unique customer checkout key and unique wallet transaction link. Platform orders link to the activated membership. Existing records are backfilled as SINGLE_GYM; historical rows are not re-priced or recharged. Gym participation defaults false.

Membership checkout takes a customer lock, then locks order/plan, checks active coverage, validates eligible gyms, and locks the wallet. Decimal amounts are used throughout. Insufficient balance, currency mismatch, unavailable plan, stale quote, no partners or activation failure roll back without a debit. Unique constraints and locks prevent duplicate activation/debit. Paid receipts retain the charged price despite later catalog edits.

MVP overlap policy: Multi-Gym purchase requires no active membership; Single-Gym purchase rejects an active membership for the same gym or any active Multi-Gym membership. No upgrade/proration is invented. Existing separate Single-Gym memberships remain usable at their specific gyms and share one daily access. The legacy scanner behavior that allowed unrelated gyms merely because a user owned multiple Single-Gym plans is closed.

Activation starts at backend UTC time at database second precision. Single-Gym duration retains configured days. Platform DAY is elapsed days; MONTH/YEAR use calendar months/years and clamp to the target month's last day. Catalog edits do not change purchased dates or prices. Current configured pause policy applies to future requests; accepted pauses remain honored. Summary/pass responses return actual pause usage.

Shared entitlement checks require ACTIVE, PAID, started and unexpired membership. Discovery/details and staff scanning use the same explicit scope/partner rules. Partner status is re-read under lock on scanning. One consumed daily access still prevents another check-in even when membership keys change. Account calendars and existing short-lived QR issuance are reused.

## Local deployment and verification

Applied the migration only after confirming the target was the local development database. Compared existing wallet account values, transaction rows, membership values and check-in rows before/after; all were unchanged. No existing customer was charged and no gym was opted in during deployment. Application catalog endpoints on ports 8000 and 5173 report WALLET_TEST_CREDIT. External payment initiation remains disabled.

Tests include isolated SQLite API/service cases, owner plan creation/purchase, prior access regressions, and explicit MySQL concurrency tests in temporary databases (created and removed by the test fixture). Same-order simultaneous retries and different competing orders result in exactly one ledger debit and one membership. Browser tests use dedicated network fixtures, never live charges, and cover both checkouts, insufficient balance/retry, confirmation duplicate clicks, responsive layout, success navigation and Multi-Gym details.

Run isolated backend verification:

```powershell
Set-Location 'C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend'
& '.\.venv\Scripts\python.exe' -m pytest -q tests/test_platform_memberships.py tests/test_access_service_regressions.py tests/test_membership_wallet_mvp.py tests/test_membership_plans_and_purchase.py
```

Optional local MySQL concurrency test requires permission to create/drop uniquely named `fitigo_wallet_test_*` databases. It does not write application data:

```powershell
$env:FITIGO_MYSQL_WALLET_TESTS='1'
& '.\.venv\Scripts\python.exe' -m pytest -q tests/test_membership_wallet_mysql.py
Remove-Item Env:FITIGO_MYSQL_WALLET_TESTS
```

Production release still needs verified funding, gateway reconciliation if added, deployment-level authorization review, rate limits, refund/cancellation policy, tax/fee requirements and security review. The controlled MVP is not a real-money payment launch. Migration downgrade is deliberately blocked to protect wallet/membership history.