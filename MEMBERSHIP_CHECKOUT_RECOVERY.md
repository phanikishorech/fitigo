# Membership checkout recovery

Implemented locally on November 18, 2026. No customer payment records, credentials,
gateway configuration, or working database schema were changed. No new dependency
or database migration is required. Deploy the backend and frontend together.

## Customer flow

- Both Single-Gym and Multi-Gym payment screens discover unresolved overlapping
  membership checkouts before offering a fresh funding selection. Discovery is
  authenticated, owner-scoped, no-store, read-only, and not restricted to the most
  recent twenty payments. A failed discovery blocks a new payment and offers retry.
- Existing checkout amounts and plan name are displayed, including the reserved
  wallet contribution. A conflicting selection is explicitly identified.
- Resume uses the original checkout. A second discovery immediately before create
  handles another tab; the backend customer lock remains the authority.
- Cancel and change requires confirmation and uses the existing cancellation API.
  Cashfree cancellation intent survives network errors. Termination is followed by
  fetching the order and payment attempts; a request alone is never safe closure.
- Processing, ambiguous creation, pending termination and provider timeouts retain
  the original checkout and wallet hold. No replacement payment is opened.
- Confirmed unpaid closure releases the hold. Review plan and payment method
  reloads the current plan quote, remounts wallet selection, and generates a fresh
  idempotency key. Multi-Gym orders support separate immutable checkout attempts.
- Legacy unsafe cancellations block replacement. Previously closed overlapping
  checkouts are reconciled before creating or reopening a replacement, so a late
  capture becomes review-required rather than silently enabling another charge.
- Membership order review reports its linked checkout status instead of always
  showing NOT_STARTED.

## Provider limitation

The existing Razorpay adapter does not implement authoritative order closure.
This change deliberately does not release Razorpay holds or claim cancellation
without evidence. The customer can refresh/resume where allowed, or seek support.
No real provider payment or cancellation was exercised during implementation.

## Validation

- Frontend unit suite: 501 passed.
- TypeScript typecheck and production Vite build: passed.
- New isolated-browser membership regression: passed (popup dismissal, reload,
  restored funding, conflicting selection, pending cancellation, refresh-driven
  closure, available wallet refresh, distinct replacement key, discovery failure).
- Existing split-payment browser regression: passed for both mocked providers,
  custom contribution, zero wallet balance, wallet-only payment and responsive UI.
- Final isolated MySQL recovery/cart/expiry run: 38 passed, 7 skipped. Skips are
  Cashfree-only termination scenarios parameterized against Razorpay.
- Earlier broader gateway/split run: 118 passed, 5 skipped and 2 failures caused by
  a new test fixture accidentally funding the entire membership. That fixture was
  corrected and both cases pass in the final run. The existing gateway/split tests
  all passed in that broader run; no application code changed after it.
- Updated expiry tests assert the new cancellation response contract and prove
  processing/unknown orders remain blocked without a termination PATCH.

Test logs are in disposable directories, not the application database. Existing
datetime.utcnow deprecation warnings remain outside this change's scope.

Backend final artifacts:
`C:\Users\ckishor\AppData\Local\Temp\fitigo-isolated-537307105de4b6fb-viy56q8e`

Frontend unit log:
`C:\Users\ckishor\AppData\Local\Temp\fitigo-membership-frontend-tests.log`