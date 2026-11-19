# Versioned admin revenue-sharing configuration

## Delivered scope

**Local activation update:** the user subsequently authorized testing activation.
Migration `d46e70ba9268` is now applied locally and the admin editor can save
test-mode versions. No agreement was automatically scheduled. See
`C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\ADMIN_AGREEMENTS_LOCAL_RELEASE.md`
for backup, unchanged-data checks and actual API smoke results. This supersedes
the historical not-activated statements below; posting/statutory limitations remain.

Added an editable **Revenue-sharing agreements** card under the existing
**Admin → Runtime settings** page. No new sidebar item or global design change.
This implements the requested admin-adjustable agreement configuration, not a
settlement engine, accounting journal or wallet FIFO implementation.

**Not activated on the working database.** Apply migration `d46e70ba9268` in a
separately authorized backup/migrate/restart release before saving real agreements.
Until then, the panel explains the missing migration and does not offer a save form.
No real agreements, payouts, commissions or customer records were changed.

## Editable fields

For each independently selected sandbox/test or production/live environment:

- Standard agreement for all gyms without a currently effective override.
- Full gym-specific agreement overrides.
- Attended individual booking gym/FitiGo percentages.
- No-show gym/FitiGo percentages.
- Single-Gym membership gym/FitiGo percentages.
- Multi-Gym fixed amount per verified visit.
- Multi-Gym visit and payout caps **per member, per gym, per calendar month**.
  This configuration scope is explicitly labelled. Platform-wide per-member caps
  and their interaction with per-gym caps need a separate policy before allocation.
- Booking and Multi-Gym settlement cycles: weekly or monthly.
- Monthly, quarterly, half-yearly and yearly Single-Gym entitlement treatment:
  next applicable settlement cycle or full gym entitlement upfront.
- Minimum payout threshold.
- Effective start, optional exclusive end, agreement reference and mandatory reason.
- CA review pending, or an administrator-recorded CA approval reference.
- A gym can schedule a new INHERIT version to return to the standard agreement.

The form requires explicit review/confirmation before saving. It displays the
currently effective agreement, scope of inheritance, scheduled versions, history,
administrator identity, time, reason, contract reference and supersession boundaries.
History is paginated, 20 versions per page.

## User-supplied initial proposal

The migration stores these as **database proposal data**, separately for test/live:

| Setting | Gym | FitiGo |
|---|---:|---:|
| Attended individual booking | 85% | 15% |
| No-show | 70% | 30% |
| Single-Gym membership | 85% | 15% |

- Booking cycle: weekly; Multi-Gym cycle: monthly.
- Monthly Single-Gym: next cycle; quarterly/half-yearly/yearly: upfront entitlement.
- Minimum payout: INR 500.
- Multi-Gym per-visit amount and caps: **null / Not configured**, because no actual
  payout amount or limit was supplied. Blank never means zero or unlimited.

There are **no active agreement versions seeded**. An administrator must review,
supply a reference/reason and future effective date, and confirm the proposal.
Neither frontend nor runtime business logic contains 85/15, 70/30 or INR 500 as a
fallback. Those values exist only in migration proposal data and test fixtures.

Contractual invariants captured in terms, not freely switchable policy shortcuts:
sharing after discounts excluding separately collected tax; actual gateway fees
tracked separately; wallet uses the same agreement; unit-priced group recognition
uses attended visitors; agent/marketplace model proposed; admin payout approval
required. Membership recognition remains NOT_APPROVED. Changing these semantics
needs a reviewed policy/workflow change rather than toggling an unsupported option.

## Effective dates and immutability

- Create-only immutable versions, no update/delete API.
- Effective start must be strictly future at save time, with explicit timezone and
  whole-second precision; UI dates are IST and stored dates normalized to UTC.
- New start must be strictly after the latest scheduled start in that scope.
  Inserting/backdating an earlier replacement or reusing the same start is rejected.
- A new commenced version supersedes the previous version at its start. The old
  row is untouched; `applies_until` is calculated from the explicit end or next start.
- Expiry never revives an older override. An expired/INHERIT gym override falls back
  to the effective standard agreement. An expired standard with no successor means
  **no agreement**, not an invented default.
- Currently scheduled future versions cannot be cancelled/reordered through this
  editor. A later version can supersede them from its own future start. An audited
  scheduled-version cancellation workflow is a possible future enhancement.
- Historical reads resolve the version effective at the requested instant, not the
  newest version regardless of time. A future posting service must pin version ID
  and source event evidence when creating immutable allocations.
- No existing transaction is repriced by this change: payment/booking/membership
  and reporting calculations do not yet use these settings to post commission.

## API and validation

- `GET /api/v1/admin/financial-agreements?mode=test|live&gym_id=...&limit=20&offset=0`
  returns availability, server time, proposal, effective version, latest version,
  gym options, immutable history and configuration-only flags.
- `POST /api/v1/admin/financial-agreements` schedules a version; requires an
  `Idempotency-Key`, expected latest version, terms/reference/reason/effective dates.
- ADMIN and SUPER_ADMIN only; anonymous/other roles are rejected. No personal
  customer or payment secrets are returned. Responses are `Cache-Control: no-store`.
- Decimal percentages 0–100 with at most two decimals, sum exactly 100 in each pair.
- Nonnegative finite money with at most two decimals. Caps/visit counts validated;
  booleans/fractions cannot masquerade as integer visit limits or version numbers.
- Unknown fields rejected; no request can enable statutory reporting.
- Exact idempotent request retries return the original version even after its start;
  changed payload or different actor with the same key returns conflict.
- Stable per-environment default-scope row lock serializes writers, including
  simultaneous first gym overrides. Current locking reads avoid stale MySQL
  repeatable-read snapshots. Optimistic version check prevents lost admin changes.
- Each immutable version is mandatory financial configuration evidence, independent
  of the optional operational audit deployment flag. Read history in this panel;
  this release does not merge it into the existing general audit feed.
- ORM update/delete guards preserve application immutability; direct privileged
  database writes are outside those guards and must be restricted operationally.

## Database migration

Revision `d46e70ba9268`, parent `c35d6fa89157`:

- `financial_agreement_scopes`: unique mode + standard/gym scope; nullable gym FK;
  initial proposal stored only on standard scopes.
- `financial_agreement_versions`: immutable terms JSON, version, dates, action,
  actor, CA status/reference, reason/reference, idempotency key/hash and created time.
- Unique scope/version, scope/start and scope/request key constraints.
- No wallet, payment, booking, membership, attendance or settlement rows changed.
- Downgrade refuses to remove any agreement version audit history.
- Migration tested on disposable MySQL, not applied to the working database.

## CA approval and accounting boundary

`statutory_reporting_enabled=false` and `posting_enabled=false` remain explicit
even when a CA reference is recorded. That is an admin attestation, not independent
verification or a switch enabling statutory accounts.

Remaining work from the wider business rules:

- Immutable per-event commission/owner allocation ledger, reversals and approved
  recognition rules; pin agreement versions instead of recomputing historical totals.
- Per-attended-visitor group value recognition in the accounting posting layer.
  Existing analytics first-admission gross-value projection is not silently changed.
- Multi-Gym verified-visit allocation, caps/budget interaction and unused-value policy.
- Settlement approval/transactions, cutoff weekday/time, failed/reversed payout
  handling and historical adjustment evidence. Configured cycle is not a scheduler.
- Actual separately collected tax and provider fee evidence, gateway settlement imports.
- FIFO wallet credit lots/debit allocations; promo expiry/restrictions; authorized
  adjustment workflow; historical reconciliation. No wallet expiry setting is
  pretended to work without the missing credit-lot engine.
- Membership recognition policy, service-period adjustments, renewal lineage,
  membership-viewer event tracking and utilization denominators.

Accordingly existing financial totals that depended on an allocation or recognition
ledger remain unavailable. Saving a percentage alone must not make those totals
look certified or retroactively assign commissions to completed purchases.

## Verification

- Initial isolated MySQL agreement tests: **29 passed** (94.60s).
- Full backend regression checkpoint: **946 passed**, zero failed, in 982.03s.
  Log: `C:\Users\ckishor\AppData\Local\Temp\fitigo-isolated-a04a45aa2648cc85-87ibyexb\pytest.log`.
  The run started before the final date-range validation and three additional tests.
  Final affected agreement suite rerun: **32 passed**, zero failed, in 121.73s.
  Log: `C:\Users\ckishor\AppData\Local\Temp\fitigo-isolated-8d2d4143842fb543-bufjuw1f\pytest.log`.
  Both isolated runners exited 0 and stopped their owned MySQL servers. Counts are
  overlapping runs, not additive. Existing datetime deprecation warnings remain.
- Frontend: **464 tests passed**; TypeScript passed; production build passed.
- Mocked browser: passed proposal loading, edits, invalid percentage sum, review,
  save, history, gym override selector and missing-migration guard, at 360/768/1440px.
- All browser mutations were intercepted fixtures. No real configuration saved.
- All 15 changed source/test/report files were verified for existence, nonempty
  contents and conflict markers; Python AST parsing and JavaScript syntax passed.

Backend commands, from `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend`:

```powershell
.\.venv\Scripts\python.exe scripts\run_isolated_tests.py --mysql-bin 'C:\Program Files\MySQL\MySQL Server 26.7\bin\mysqld.exe' --test-timeout 3600 tests -q
.\.venv\Scripts\python.exe scripts\run_isolated_tests.py --mysql-bin 'C:\Program Files\MySQL\MySQL Server 26.7\bin\mysqld.exe' --test-timeout 900 tests/test_financial_agreements.py -q
```

Frontend commands, from `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend`:

```powershell
npm test
npm run typecheck
npm run build
node scripts\agreements-browser.mjs
```

Frontend artifacts:
`C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\agreement-unit-results.txt`
`C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\agreement-build-results.txt`
`C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\agreement-browser-results.txt`

## Files changed

- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\models\financial_agreement.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\models\__init__.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\alembic\versions\d46e70ba9268_financial_agreements.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\schemas\financial_agreement.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\services\financial_agreements.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\routers\admin_financial_agreements.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\routers\admin.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\tests\test_financial_agreements.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\admin\agreementService.ts`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\admin\RevenueSharingSettings.tsx`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\admin\agreements.css`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\admin\WorkflowSettings.tsx`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\scripts\agreements.test.mjs`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\scripts\agreements-browser.mjs`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\ADMIN_REVENUE_SHARING_CONFIGURATION.md`