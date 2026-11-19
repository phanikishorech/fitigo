# Financial simplification — increment 1

## Scope and activation boundary

Implemented **configuration and onboarding only**, not the complete financial
simplification. No existing migration was edited and no new migration is needed
for this increment: settings use the existing immutable agreement version store.
No working database configuration, completed transactions, evidence, wallet
liabilities, flags, workers, or payout records were changed by implementation.
Migrations were exercised only on newly created disposable MySQL servers.

The working database was rechecked read-only: revision `d46e70ba9268`, two default
proposal scopes, zero agreement versions. Repository migration head remains
`c91dc50f4713`. All four source/allocation/live-allocation/payout gates remain false.
Do not deploy or activate this increment as a completed financial engine.

## Implemented

- Dedicated Admin → Financial Settings page, reusing existing UI components,
  agreement CSS, and global styles without modifying global CSS.
- Paginated, literal-name gym search; explicit gym and test/live selection.
- Independent percentage and actual-fee splits for Individual, Single-Gym,
  authorized no-show, and Multi-Gym. Defaults are backend-owned, not UI constants.
- Defaults: 85/15 Individual and Single-Gym; 70/30 authorized no-show;
  50/50 fee responsibility for each; Multi-Gym reference ₹3,000 / 100 visits
  with 0/100 fee responsibility. The divisor is not a visit cap.
- Nullable settlement cycle/minimum configuration. Missing is not zero.
- Explicit future effective start, actor, reason, immutable history, review before
  save, optimistic version checks, and same-payload/same-actor idempotent retry.
- Legacy agreement replacement requires explicit acknowledgment. Existing rows
  and pins are not rewritten. The old API cannot switch a consolidated gym back
  to legacy terms or shared inheritance.
- Existing gyms without configuration are not initialized on GET or in bulk;
  an Admin must schedule an explicit future version.
- New gyms created through the owner API/GymService receive separate versions
  for both environments in the same transaction as gym creation. Missing schema
  or environment scope fails the entire creation instead of producing a gym
  without its required defaults. Initialization retries preserve existing versions.
- Admin/Super Admin authorization and no-store headers on all new endpoints.

## API

- `GET /api/v1/admin/financial-settings/gyms?q=...&limit=20&offset=0`
- `GET /api/v1/admin/financial-settings?mode=test&gym_id=...&limit=20&offset=0`
- `POST /api/v1/admin/financial-settings` with `Idempotency-Key`.

POST includes gym/environment, expected gym version, expected current effective
version ID (nullable), effective start, settings, reason, configuration-only
acknowledgment, and legacy-replacement acknowledgment when applicable.

## Storage/dependency decisions

- Retained: `FinancialAgreementScope`, immutable `FinancialAgreementVersion`,
  historical `FinancialAgreementPin`, effective-version resolver, scope locks,
  history presentation, and the old request hashing/retry behavior.
- New consolidated versions contain `terms.financial_settings` and do **not**
  duplicate legacy percentage, accounting, marketplace, and visit-cap contracts.
- Legacy terms remain stored and usable for their original versions. They are
  not automatically converted, reapproved, or copied into new settings.
- The legacy RevenueSharingSettings editor is no longer mounted in runtime
  settings. Its source and old API remain for compatibility/history work, but
  consolidated gym edits go through the new API. Existing legacy browser scripts
  that expect that editor at `/admin/settings` are superseded for this navigation
  and were not claimed as passing in this increment.
- Existing source pins cannot process the new format: it intentionally contains
  no approved legacy selection/marketplace/visit contract. Readiness explicitly
  reports configuration-only status. Calculator adapters must be added before
  any activation; do not synthesize approved contracts to bypass this boundary.
- The only production gym creation path found is GymService through the owner
  API. Direct ORM test fixtures and the development seed script are not onboarding
  paths and were not changed into financial backfills.

## Still required

1. Connect consolidated versions to one backend calculator, removing hardcoded
   rate enforcement for new-version processing while preserving historical pins.
2. Preserve transaction-wide paise and actual provider fee/tax conservation,
   wallet-only zero-fee behavior, split-funding evidence, and gross/net-pending.
3. Decide monthly timezone, rounding, effective-version boundaries, purchase-fee
   attribution, and invalidated-visit corrections. These settings currently accept
   only explicit unknown/null; no guessed executable policies or caps are added.
4. Implement monthly completion/entitlements and keep unallocated collections
   separate. Multi-Gym FitiGo earnings remain unapproved.
5. Add authoritative purchase tax/discount facts and gateway-only cart funding
   rows without altering prices or existing payment/wallet safeguards.
6. Consolidate reports, owner views, and status filters using allocation versus
   collection definitions; preserve unknown rather than showing zero.
7. Reuse payout reservations and audit. Approval must remain distinct from payment.
8. Complete broader regression and deployment review before enabling anything.

No historical wallet/check-in/cancellation findings were repaired.

## Validation

- Initial backend attempt: collection stopped on a syntax error in a new test;
  corrected before execution. No successful-suite claim for that attempt.
- Focused disposable-MySQL run: **175 passed**, zero failures/skips, 166.21s.
  Includes settings, legacy agreements, selection, calculator, accounting policy,
  gym approval, booking capacity/idempotency/reschedule, and owner gym review.
- Frontend unit suite: **477 passed**, zero failures/skips.
- TypeScript check and production build: passed after final UI adjustments.
- Mocked browser flow: passed defaults, percentage editing/validation, review,
  interrupted-request same-key retry, save/history, gym/environment isolation,
  schema-unavailable display, and 360/768/1440 layouts. Every API request intercepted.
- Scoped diff whitespace checks: clean. The whole working-tree check identifies
  pre-existing trailing whitespace in the unrelated frontend Vite configuration;
  it was deliberately left untouched.

- Broader disposable-MySQL financial/access regression: **69 passed**, zero
  failures/skips, 534.17s. Allocation, visit entitlement, payout reservation/audit,
  reporting, source evidence, split funding, QR/access, owner bookings, slots,
  and staff invitation/access suites passed. The shell returned after 300 seconds
  while this run continued; the runner subsequently completed successfully,
  within its 900-second bound. This was **not** a timeout.
- Final settings/schema/API/policy rerun after readiness and additional isolation
  tests: **77 passed**, zero failures/skips, 176.25s.
- These are overlapping focused checkpoints, not a full backend-suite run or a
  combined unique-test total. Existing datetime.utcnow deprecation warnings remain.
- Every disposable server was stopped by its runner. All three runs migrated a
  fresh disposable schema to the unchanged repository head successfully.

## Validation artifacts

- `C:\Users\ckishor\AppData\Local\Temp\fitigo-isolated-2d3b5d27c3d02866-q1ph324d\pytest.log`
- `C:\Users\ckishor\AppData\Local\Temp\fitigo-isolated-7ea922604072d65f-s9iow_by\pytest.log`
- `C:\Users\ckishor\AppData\Local\Temp\fitigo-isolated-38612e9e5d742c62-ahomrr3w\pytest.log`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\financial-settings-unit-results.txt`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\financial-settings-build-results.txt`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\financial-settings-browser-results.txt`