# Membership pause

## Configure and use

- Gym Owner → My gyms → Membership plans → Create/Edit: **Allow Pause** and **Maximum pause days** for the gym's Single-Gym plan.
- Admin → Membership Plans → Create/Edit: the same settings for Multi-Gym plans.
- Customer → My Membership → membership card/details: current allowance, original/current expiry, eligible Pause Membership action and Pause History. The existing `/membership/pause` route also works.

Existing plans default to disabled with zero allowance. No live plans were enabled and no customer pauses were created during implementation.

## Backend rules

Policy is read from the current owning plan for each eligibility, preview and confirmation. Policy edits apply to future requests for existing memberships; already accepted periods remain honored. Reducing the limit below usage clamps remaining allowance to zero. Disabled policies require zero; enabled policies require positive integer days, with a backend safety ceiling of 3660.

Dates use **UTC**, consistent with daily access. Only future complete UTC days within current membership validity may be paused. End dates of pauses are inclusive; membership expiry timestamps remain exclusive. Multiple non-overlapping periods are supported within total allowance. No early resume or cancellation of a pause is introduced.

Future periods are **SCHEDULED**: membership remains active until the pause starts. During the date range the backend derives PAUSED; after it ends the backend derives ACTIVE without a cron job. Allowance is reserved and expiry extended atomically when scheduling. Original expiry is retained. For example, five complete days extend an exclusive November 1 timestamp to November 6.

## Contracts and safety

- Existing owner plan endpoints accept/return `pause_policy: { allowed, max_pause_days }`.
- Existing Admin platform plan endpoints accept/return `pause_rule` in the same shape.
- `GET /api/v1/memberships/me/{membership_id}/pause`: policy, eligibility/status, date bounds, original/current expiry and history.
- `POST /api/v1/memberships/me/{membership_id}/pause/preview`: `{ start_date, days }`; read-only validation returning all computed dates and a preview fingerprint.
- `POST /api/v1/memberships/me/{membership_id}/pause`: selection plus `accepted_preview`, and an `Idempotency-Key` header. Revalidates policy/allowance/overlap/validity under locks.

Endpoints require an authenticated active CUSTOMER owning the membership. Owner changes require gym ownership; platform configuration requires Admin privileges. Customer, membership, policy and pause rows are locked for atomic scheduling. Unique request keys and current reads protect concurrency and lost-response retries. Preview fingerprints detect stale review; they are not authorization secrets. Clients cannot submit authoritative expiry/usage/status.

Shared entitlement checks exclude paused memberships from discovery and QR issuance. Existing staff scanning rechecks membership pause and responds `MEMBERSHIP_PAUSED`. Legacy daily-QR transport is blocked too. Multi-Gym pause applies across partner gyms. A paused Single-Gym plan does not block another independent active membership. Wallet overlap checks include paused memberships to prevent duplicate coverage purchases.

Calendar marks a day PAUSED when all applicable entitlements are paused; a separate unpaused membership remains usable. Legacy account-wide pause-day records remain supported, but new schedules are membership-scoped. Booking/cart rules are unchanged.

The UI sends selections and renders backend previews/results, uses existing resource/client/modal components, prevents duplicate submissions, preserves idempotency keys on technical retry, refreshes membership data after success and clears read caches. Paused memberships remain visible rather than showing a no-membership purchase state.

## Deployment and verification

Migration `6eb14f5a7c93` follows `5da03e4f6b82`. It adds plan policy fields, original expiry and membership pause periods. Applied to the confirmed local development MySQL database. Before/after fingerprints verified existing membership dates/status, wallet balances/ledger, check-ins and prices unchanged. Original expiry was backfilled; zero policies enabled, zero pauses created. Backend and frontend proxy expose the contracts; anonymous eligibility requests return 401.

For other environments, back up the database and apply the migration before serving the new application. MySQL DDL is not transactional. Do not downgrade with scheduled pauses: removing enforcement/history would lose the schedule even though extended expiry is retained.

Verification uses disposable SQLite and opt-in temporary MySQL databases. Browser suites use isolated intercepted responses, not live business mutations. Physical-device and live authenticated end-to-end acceptance remain separate. No new frontend library or router was added. External payments remain disabled.

MySQL concurrency tests exposed fractional wallet activation timestamps rounding ahead of current time. Activation now uses second precision matching stored DATETIME precision; competing purchase tests pass. No price/payment-policy change was made.

## Changed files and purpose

All paths below are absolute. Existing unrelated workspace modifications are not part of this feature.

### Backend models/contracts
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\alembic\versions\6eb14f5a7c93_membership_pause.py` — migration/backfill.
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\models\membership.py` — plan policy, original expiry and scoped pause records.
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\models\platform_membership.py` — platform policy fields.
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\schemas\membership_pause.py` — strict policy/request/preview/eligibility/history schemas.
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\schemas\membership.py` — plan policy and original-expiry fields.
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\schemas\platform_membership.py` — platform policy input/output.
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\schemas\access.py` — paused access code.
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\schemas\profile.py` — current policy documentation.

### Backend services/routes
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\services\membership_pause_service.py` — eligibility, preview, transaction and status authority.
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\services\membership_entitlement.py` — scoped pause exclusions.
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\services\membership_service.py` — owner policy and cancellation locking.
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\services\platform_membership_service.py` — Admin policy and catalog mapping; older clients don't erase existing policy.
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\services\membership_wallet_service.py` — original expiry/terms, paused overlap and timestamp precision.
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\services\access_service.py` — issuance/check-in/calendar enforcement.
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\routers\memberships.py` — customer endpoints and effective membership status.
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\routers\gym_owner.py` — policy response mapping.
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\routers\profile.py` — actual pause usage/status and legacy issuance checks.
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\routers\checkins.py` — structured paused rejection.

### Frontend
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\services\membershipPauseService.ts` — typed shared-client calls.
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\components\membership\MembershipPause.tsx` — allowance, modal, preview, result and history.
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\pages\membership\MembershipPausePage.tsx` — existing pause route implementation.
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\pages\membership\MembershipOverview.tsx` — per-membership controls, status and refresh.
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\pages\CustomerApp.tsx` — lazy pause page wiring.
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\components\membership\MembershipUI.tsx` — removes unavailable placeholder.
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\components\membership\MembershipPlanCard.tsx` — backend allowance benefit.
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\utils\membership.ts` — paused cards stay visible.
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\membership.css` — pause/history styling.
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\admin\MembershipPlans.tsx` — Admin policy editor.
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\admin\membershipPlanService.ts` — editable policy mapping.
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\owner\Operations.tsx` — Owner policy editor.
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\screens\GymOwner\api.ts` — owner policy types.
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\screens\GymDetails\api.ts` — public policy type.
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\services\platformMembershipService.ts` — platform policy type.
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\services\client.ts` — safe business-error messages.

### Tests/documentation
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\tests\test_membership_pause.py` — API, ownership, lifecycle, rollback, migration and scanner response tests.
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\tests\test_membership_pause_mysql.py` — real locking/concurrency tests.
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\tests\test_access_service_regressions.py` — isolated schema update.
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\tests\test_platform_memberships.py` — fixture/schema and policy response expectations.
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\tests\test_membership_wallet_mysql.py` — temporary schema update.
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\scripts\membershipPause.test.mjs` — service and backend-authority tests.
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\scripts\membership-pause-browser.mjs` — Customer/Admin/Owner responsive flows and screenshots.
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\scripts\membership.test.mjs` — paused-state and preview expectations.
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\scripts\membership-browser-fixtures.mjs` — new contract in existing regressions.
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\scripts\auth-account-browser.mjs` — pause-route empty membership fixture.
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\MEMBERSHIP_PAUSE.md` — operations and file manifest.
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\MEMBERSHIP_WALLET_MVP.md` — current pause availability references.
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\MEMBERSHIP_IMPLEMENTATION.md` — supersedes historical pause limitation.