# Admin UI cleanup and business simplification

## Delivered

The everyday Admin app now has exactly seven primary navigation items, in order:
Dashboard, Gyms, Users, Bookings, Memberships, Reports, Commission Settings.
Dashboard remains the default Admin landing page. Profile, notifications and logout
remain ancillary account actions, not new primary modules.

### Removed from everyday UI (backend retained)

- Standalone Financial Reconciliation route, navigation and lazy mount.
- Financial operations dashboard, marketplace payout requests/transitions,
  source/evidence inspection, historical reconciliation, settlement review cards.
- Readiness/schema status, processing gate names, worker controls, correction
  execution, runtime settings, operational audit navigation and duplicate Analytics
  page. The old analytics URL renders the same Reports view for compatibility.
- Support/readiness/runtime/audit routes are not mounted by the everyday Admin app.
  Their existing backend APIs/services are retained; owner/customer support is intact.
- Separate Membership Plans primary item; plans remain a secondary action inside
  Memberships. Existing plan/offer forms and pricing behavior were not changed.
- Technical settlement editor, processing blockers and raw JSON history/review
  payloads in Commission Settings. Hidden settings remain in the saved payload.

Old technical components remain as unmounted source files, not a second normal Admin
workspace. No developer diagnostic route was introduced. Existing protected backend
diagnostic APIs remain available under their established authorization controls.

### Dashboard

- Overall completed visits, customer collections, active memberships, scheduled
  bookings and current registered user/gym counts.
- Separate Individual, Single-Gym and Multi-Gym verified-visit counts and chart.
- Customer collection categories and dated chart, distinct recorded gym gross
  entitlement and FitiGo net commission. No included-visit collection duplication.
- Wallet details expanded on demand: current unused ledger balance, period credits,
  usage and cancellation credits.
- Cancelled/no-show counts and percentages; no-show requires an explicit mark and
  timestamp, not merely a missing scan.
- Today, Yesterday, Last 7 days, Last 30 days, This month and Custom filters. The
  shared date component's default behavior for customer/owner pages is retained;
  only Admin business pages opt into the rolling seven-day preset.
- Gym and live/test payment selection remain explicit to prevent misleading mixed
  environments. Test data is visibly labeled.

### Other modules

- Gyms retain search/filter/detail/owner/review and membership participation. Added
  links to gym bookings/memberships/reports and exposed existing deactivate/reactivate
  actions using the existing endpoints, confirmations and status rules.
- Users retain search, roles, account status/details. Added read-only recent booking,
  membership and ledger-checked wallet details.
- Bookings retain existing search/status/payment/cancellation behavior. Added
  read-only verified visitor counts and explicit no-show status in details.
- Memberships now lists actual customer purchases rather than only plan definitions:
  search, Single-/Multi-Gym, active/paused/expired/cancelled/upcoming/unpaid status,
  purchase amount/date, validity and gym/customer links. Individual pay-per-visit
  purchases remain Bookings, not fabricated memberships.
- Reports has seven useful views: visits, revenue, gym performance, membership,
  bookings/cancellations, customers and wallet. Date/gym/environment filters and CSV
  exports reuse the existing CSV escaping utility. No native Excel library added.
- Commission Settings uses the existing gym-specific API and calculator-connected
  configuration; editable revenue/fee shares and Multi-Gym amount/divisor, effective
  date, actor, reason, confirmation, version checks, same-key retries and immutable
  history are preserved. No percentages or defaults hardcoded in the new UI.

## Read-only backend presentation additions

The existing API did not provide a membership purchase list or visit-category
summary, so four Admin-only GET endpoints were added under `/admin/business`:
`/summary`, `/memberships`, `/customers/{id}`, `/bookings/{id}/attendance`.
They use existing verified funding/admission, wallet and allocation read models.
No customer mutation, reconciliation/provider call, financial allocation, correction
or payout is performed by these endpoints. Tests spy for writes during GET.

No existing financial calculator, source producer, wallet, payment integration,
booking/access/cancellation or membership service was altered. No migration needed.

## Metric definitions and explicit limits

- Visits: successful source-linked check-ins inside QR validity, deduplicated by
  purchased visitor or membership daily access. Rejected/out-of-window scans do not
  increase totals. Gym/customer visit report counts use the same admission projection.
- Customer collections: currently verified, fulfilled and unrefunded purchase
  consideration, counted once on authoritative provider capture time or wallet debit
  completion. Includes wallet-funded consideration; excludes wallet recharges to
  prevent counting recharge and subsequent spend as two marketplace purchases.
- Membership included visits do not generate another collection.
- Missing/ambiguous capture dates produce unavailable totals/charts, never a guessed
  checkout-created date or misleading zero. A single unresolved dated cohort can
  make the filtered collection total unavailable. Historical gaps were not repaired.
- Cross-gym cart cash is not guessed for one gym; Multi-Gym collections are not
  assigned to a specific gym. These scopes may be unavailable.
- Recorded owner share/commission are existing ledger outputs, not percentages
  applied to collections in the browser. They may cover fewer transactions than
  collections. Unallocated Multi-Gym collections are never FitiGo earnings.
- Wallet balance comes from actual ledger balances reconciled with stored balances;
  discrepancies remain unavailable, never derived from booking totals.
- Cancellation percentage = cancelled / scheduled bookings in the selected range.
  No-show percentage = explicitly marked no-shows / (attended bookings + marked
  no-shows). The caption states these denominators.
- User/gym/active-membership/unused-wallet figures are current inventory; visits,
  movements and scheduled bookings use selected dates. Membership sales reports
  retain their existing purchase-date basis, labeled separately from capture-dated
  collection reports. Gym booking values are service value, not net earnings.

### Existing capability limitations, not silently implemented

- General gym add/edit is currently an **owner onboarding/edit workflow**. There is
  no existing Admin general create/edit API. It was not invented in this UI-only
  task; Admin approval, deactivation, details and owner management remain available.
- CSV export is available; native XLSX export was not previously supported and no
  new export library was introduced. CSV can be opened in spreadsheet applications.
- New business summary currently composes existing financial read projections and
  examines verified purchase dates; large production datasets may need aggregate
  query optimization after profiling. No claim of production performance testing.
- Technical backend APIs were preserved, not deleted or weakened. Removing their UI
  does not resolve tax, configuration, settlement or payout blockers.

## Modified files

Workspace: `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo`.

New:
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\services\admin_business.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\routers\admin_business.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\tests\test_admin_business_cleanup.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\admin\BusinessOverview.tsx`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\admin\businessService.ts`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\admin\Memberships.tsx`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\admin\CustomerActivity.tsx`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\admin\BookingAttendance.tsx`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\admin\GymBusinessActions.tsx`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\scripts\admin-cleanup.test.mjs`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\scripts\admin-cleanup-browser.mjs`

Updated routing/presentation:
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\routers\admin.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\admin\AdminLayout.tsx`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\admin\AdminApp.tsx`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\admin\routes.ts`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\admin\Dashboard.tsx`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\admin\Account.tsx`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\admin\FinancialSettings.tsx`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\admin\Users.tsx`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\admin\Bookings.tsx`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\admin\Gyms.tsx`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\components\common\DateRangePicker.tsx`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\utils\dateRange.ts`

Updated test expectations/scripts:
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\scripts\admin-financial.test.mjs`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\scripts\gym-financial-settings.test.mjs`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\scripts\reconciliation.test.mjs`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\scripts\support.test.mjs`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\scripts\returnIntent.test.mjs`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\scripts\financial-settings-browser.mjs`

No fonts/colors/global CSS, backend commercial settings/defaults, calculations,
financial tables or migrations were changed or removed.

## Validation and reruns

Overlapping checkpoints, not a unique total or whole-backend-suite claim:

| Checkpoint | Result |
|---|---|
| Initial frontend | 475 passed / 8 failed: obsolete route/mounted-component expectations |
| Updated frontend navigation expectations | 483 passed |
| Final frontend with new cleanup tests | 489 passed, zero failed/skipped |
| TypeScript / production build | Passed |
| Initial backend metric/report run | 30 passed / 1 failed: duplicate scan fixture correctly rejected by unique constraint |
| Corrected backend + gym configuration isolation | 47 passed, 389.45s |
| Customer/owner/staff/date/metric regression | 53 passed, 176.55s |
| Expanded metric/report run | 34 passed / 2 failed: fixture inserted child funding before parent flush |
| Diagnostic split-only rerun before fix | 2 failed, 8 deselected; same fixture FK error |
| Final metric/report rerun after parent flush | 36 passed, 308.20s |

The failed expanded run reported 3035.85s despite the runner's 600-second bound;
the runner completed with pytest exit 1, not TimeoutExpired. This anomalous long
elapsed run is recorded rather than claimed to meet the bound. No financial
production logic was changed to satisfy the fixture errors.

Browser validation: initial attempts failed because the debug browser was not
running. Started an owned isolated headless Chrome profile, intercepted every API,
then validated all seven modules/default landing/date selection/CSV/removed routes
and 360/768/1440 layouts. Commission browser initially raced gym-option loading;
added an explicit wait, then passed edit/validation/review/same-key retry/history/
gym and environment isolation/missing-settings behavior. All writes mocked.

## Safety

No deployment, migration, worker/scheduler start, correction execution or payout.
Read-only before/after inventory compared **all 55 working tables**: every row count
and fingerprint matched. Working revision remains `d46e70ba9268`.
`source_evidence_enabled`, `marketplace_allocations_enabled`,
`marketplace_live_allocations_enabled`, and `marketplace_payouts_enabled` all remain
**false**. Financial backend services, APIs and source/audit protections remain intact.

Artifacts:
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\ADMIN_CLEANUP_BEFORE.json`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\ADMIN_CLEANUP_AFTER.json`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\admin-cleanup-tests.txt`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\admin-cleanup-build.txt`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\admin-cleanup-browser-results.txt`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\commission-cleanup-browser-results.txt`
- `C:\Users\ckishor\AppData\Local\Temp\fitigo-isolated-ae387854f903484a-y_ubt5v3\pytest.log` — 47 passed
- `C:\Users\ckishor\AppData\Local\Temp\fitigo-isolated-d3e541b0241a942a-f5a2ivdz\pytest.log` — 53 passed
- `C:\Users\ckishor\AppData\Local\Temp\fitigo-isolated-2497d3c5deb28917-1q52623m\pytest.log` — final 36 passed

Final frontend test/typecheck/build and seven-module browser flow were rerun after
the last UI adjustment and passed. Disposable MySQL servers were stopped by their
runners. No full backend-suite claim is made.