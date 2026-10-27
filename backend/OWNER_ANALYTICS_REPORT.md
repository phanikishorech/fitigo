# Compact owner dashboard and Analytics & Reports

## Booking revenue check-in gate (current rule)

Verified payment alone no longer recognizes individual-booking revenue. A booking
must be CONFIRMED, not NO_SHOW, and have a successful BOOKING_ACCESS check-in at
its own gym. Upcoming/unscanned, cancelled, no-show and manual-only attendance
contribute zero, even when payment is PAID. Membership payments retain their
existing one-time recognition without requiring a visit. The existing effective
test/live mode filter remains; no flags or schema changes were added.

The common sales projection uses EXISTS, not a join that multiplies payments:
a group booking is attended after the first successful visitor check-in and its
full payment is recognized once. Additional visitors/duplicate scans never add
the payment again. This is booking-level recognition, not per-person allocation.

The date basis remains purchase date for both categories. A later check-in makes
that booking eligible in its original purchase-date period; it does not shift
income to the check-in-date period. UI descriptions disclose this explicitly.
Transaction rows retain the paid amount and show zero recognized amount with
NO_ELIGIBLE_CHECKIN when attendance is the blocker. Summaries, charts and gym
breakdowns share this rule. Older descriptions permitting unscanned/cancelled
paid booking revenue below are superseded by this section.

## Payment-mode correction (supersedes live-only descriptions below)

Revenue now uses the existing `settings.gateway_mode`: PAYMENT_ENV=sandbox maps
to test, production maps to live; when PAYMENT_ENV is absent, PAYMENT_MODE is used.
No new environment flags, UI toggles, database columns or credentials were added.
Test mode includes only test checkout sales; live mode includes only live sales.
This applies to summary totals, time-series charts, per-gym breakdown, refunds and
transaction pages. Unlinked legacy rows remain visible for audit but contribute
zero revenue. Other-mode linked payments are outside the report entirely.
The response's revenue.mode echoes this existing configuration for accurate UI
labels, including “No real money” in test mode. Payment verification, refund,
purchase-date, owner-scope and Multi-Gym allocation rules are unchanged.

Verification for this correction: 76 backend reporting tests passed (including
real disposable MySQL strict-mode tests in test and live modes); 352 frontend
tests, TypeScript checking and production build passed. No application data or
environment configuration was modified.

## Delivered

- Default dashboard: exactly three metrics per owner-wide/selected-gym section:
  Visits completed, Upcoming visits, Total revenue. Two independent accessible
  expand/collapse controls reveal compact secondary metrics already in the summary
  response. Expanding or collapsing does not request data.
- Removed dashboard booking tables, attendance lists, detailed revenue panels and
  gym-management cards. Detailed metrics link into the appropriate Analytics section,
  preserving date range and reporting gym.
- Reused `/owner/analytics` and its single existing sidebar item, now labeled
  Analytics & Reports. `/owner/revenue` uses the same reporting implementation in
  revenue-only mode. No duplicate navigation routes.
- Analytics: existing date presets/custom range, All Gyms/selected-gym reporting
  selector, explicit refresh, scope/updated-time labels, complete metrics, visits
  and revenue line charts, outcome distribution, gym revenue breakdown, paginated
  booking/attendance/payment records and server-side record filters.
- Existing font, green/white branding, shell, mobile navigation, date controls and
  Scan member QR action retained. No scanner, payment fulfillment or DB changes.

## Backend API contract

Existing `/api/v1/gym-owner/dashboard/summary` retained; adds `upcoming_visits`.
The existing booking/attendance routes are unchanged.

New GET endpoints (all require the existing GYM_OWNER role and use no-store):

| Path | Response / extra filters |
|---|---|
| `/api/v1/gym-owner/analytics` | Summary, daily/weekly series, revenue by gym |
| `/api/v1/gym-owner/analytics/bookings` | `{items,total}`; `category` |
| `/api/v1/gym-owner/analytics/attendance` | `{items,total}`; successful check-ins |
| `/api/v1/gym-owner/analytics/transactions` | `{items,total}`; `category`, `payment_status` |

All accept optional `gym_id` and paired inclusive `date_from`/`date_to`. Omitted
gym means all gyms owned by the authenticated owner, never every platform gym.
Foreign/missing gyms return 404, invalid scopes/ranges/filter enums return 422.
Date range maximum remains 366 days. Tables accept limit 1–100 (default 20),
offset >= 0; the UI uses pages of 10 with stable ordering and server total counts.
Record filters narrow tables, not the period-wide charts/summary; date/gym scope
applies to every report. Customer names are limited to authorized booking records.
No gateway credentials or checkout sessions are exposed in reporting responses.

## Shared metric definitions

Existing successful-check-in categories, cancelled/no-show exclusions and
scanner replay safeguards are retained. Manual attendance is not substituted
for a successful check-in. Total visits = Multi-Gym + Single-Gym + individual
booking visitor check-ins, using actual check-in timestamp within IST boundaries.

New `upcoming_visits` is the SUM of visitor quantity for future scheduled starts
in the selected period, where booking is CONFIRMED and BOOKING_ACCESS, payment
is PAID, customer is active, gym is approved/active, slot is active, booking is
not NO_SHOW and there is no successful check-in for the booking. This is a
reporting estimate of currently eligible reserved places, not a promise that a
future scan will pass every time-dependent access policy. It does not pre-book
membership daily access. Check-in-time validation remains authoritative.

Upcoming **bookings** remains the established disjoint reservation classification:
confirmed, no scan, future or still-open scheduled window. It can differ from
future paid **visitor places**. Attendance distribution includes pending, expired
and unresolved to avoid implying the four featured outcomes exhaust all bookings.
All booking categories use scheduled date and the same SQL classifier as lists.

Revenue preserves the previously documented conservative accounting contract:
- Purchase-date cohort (immutable checkout.created_at), current verified live paid
  status in both payment record and checkout, supported provider and external
  payment ID, INR only. NOT payment-settlement-date receipts or gym payouts.
- Single-Gym membership sale once, plus allocated booking payment rows once.
  Checkout totals are not added again. No sale is recognized at each member visit.
- Multi-Gym sales have no gym allocation and are excluded.
- Full refunds, partial refunds, sandbox/test-credit, unlinked legacy and
  review-required payments are excluded with disclosures. Exact partial-refund
  net amounts and immutable payment-success dates are not stored.
- Cancelled but genuinely paid/unrefunded sales remain revenue.

The shared `owner_revenue.sales_query` projection now powers summary, time series,
per-gym breakdown and payment records. The sum of recognized table amounts, chart
buckets and gym breakdown reconciles to summary revenue under the same scope.
Separate HTTP requests can naturally observe newer data if a payment/check-in
changes between requests; there is no claim of cross-request snapshot isolation.

## Charts and performance

**Chart library: none.** Existing React and native SVG render the line charts;
HTML meter elements render the compact booking-outcome distribution. No package
or lockfile changes. Charts offer hover/focus/tap exact values, keyboard focusable
points, axis labels, accessible data tables, and empty states without sample data.

Ranges <= 90 days use daily aggregation; longer ranges use seven-day buckets
anchored to the selected start date, with a clipped final bucket. Zero buckets
come from real SQL counts/sums, not interpolated or placeholder data. Backend
aggregation returns at most 90 daily/53 weekly points, never raw check-ins just
for frontend totals. MySQL strict mode remains enabled.

Dashboard uses one summary request per scope, not detail requests. Analytics
uses one overview and one request per displayed paginated table. Expanding
dashboard panels makes no requests. Existing report hook refreshes on visible
30-second polling/focus and guards in-flight refreshes. Returning from scanner or
mutation pages loads fresh reports. Explicit Analytics refresh updates all data.
No long-lived metrics cache. Loading, errors, retry, zero-data and stale-scope
response protection use existing hooks/components.

## Validation actually executed

- **146 backend tests passed, exit 0**, covering new analytics endpoints,
  MySQL ONLY_FULL_GROUP_BY daily/weekly aggregation, owner scopes, table pagination,
  filters, chart/summary/gym/transaction reconciliation, IST boundaries, payment
  exclusions, upcoming visitor places, existing date/dashboard metrics, scanner
  replay and Razorpay/Cashfree regressions. MySQL tests create/drop disposable DBs.
- **351 frontend Node tests passed, exit 0**.
- TypeScript typecheck and Vite build passed, exit 0; Python compileall passed.
- Mocked Chrome compact dashboard test passed: six primary cards, independent
  expand/collapse without requests, no tables, gym/date changes, stale responses,
  error recovery, no page overflow at 320/360/390/768/1024/1440 px.
- Mocked Chrome analytics test passed: charts/tooltips, All Gyms/selected scope,
  record filters/pagination, refresh/error/empty states, no page overflow at
  320/360/768/1024/1440 px. Browser fixtures do not certify live business data.
- Full unrelated backend suite was not rerun. No actual payment was made and
  no application DB migration was run. Existing deprecation warnings remain.

Reproduce:

```powershell
Set-Location 'C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend'
$env:FITIGO_MYSQL_DASHBOARD_TESTS='1'
python -m pytest tests/test_owner_analytics.py tests/test_owner_dashboard_mysql.py tests/test_owner_dashboard_metrics.py tests/test_owner_business_metrics.py tests/test_dashboard_date_ranges.py tests/test_booking_access_qr.py tests/test_razorpay_payments.py tests/test_cashfree_payments.py -q --disable-warnings
Remove-Item Env:FITIGO_MYSQL_DASHBOARD_TESTS
Set-Location 'C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/frontend'
npm.cmd test
npm.cmd run typecheck
npm.cmd run build
# With an isolated Chrome DevTools instance on 9231 and Vite on 5173:
node 'C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/frontend/scripts/owner-dashboard-browser.mjs'
node 'C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/frontend/scripts/owner-analytics-browser.mjs'
```

## Files changed for this enhancement

Existing uncommitted dashboard work was preserved; this list covers this enhancement.

Backend:
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend/app/routers/gym_owner.py`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend/app/routers/owner_analytics.py` (new)
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend/app/services/owner_dashboard_service.py`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend/app/services/owner_metric_rules.py`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend/app/services/owner_revenue.py` (new)
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend/app/services/owner_analytics_service.py` (new)
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend/tests/test_owner_analytics.py` (new)
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend/tests/test_owner_dashboard_mysql.py`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend/OWNER_ANALYTICS_REPORT.md` (new)

Frontend:
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/frontend/src/owner/Dashboard.tsx`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/frontend/src/owner/Analytics.tsx` (new)
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/frontend/src/owner/analyticsService.ts` (new)
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/frontend/src/owner/ReportMetrics.tsx` (new)
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/frontend/src/owner/ReportChart.tsx` (new)
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/frontend/src/owner/OwnerApp.tsx`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/frontend/src/owner/OwnerLayout.tsx`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/frontend/src/owner/Account.tsx`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/frontend/src/owner/owner.css`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/frontend/src/screens/GymOwner/api.ts`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/frontend/src/components/common/DateRangePicker.tsx` (compatible initial-preset correction for linked ranges)
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/frontend/scripts/owner.test.mjs`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/frontend/scripts/ownerAnalytics.test.mjs` (new)
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/frontend/scripts/owner-dashboard-browser.mjs`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/frontend/scripts/owner-analytics-browser.mjs` (new)

Optional prior-period comparisons were not added: the page concentrates on
verified period metrics, category composition and drill-down records. No decorative
trend percentages or assumed payout allocations are displayed.