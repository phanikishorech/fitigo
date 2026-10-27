# Owner dashboard: metric contract and implementation report

Current booking revenue rule: require verified payment AND a successful check-in
for the same confirmed, non-no-show booking/gym. Upcoming/unscanned and cancelled
bookings contribute zero. Membership payments still count once without visits.
Purchase-date filtering and the existing test/live mode remain. Group booking
payments count once after the first visitor check-in, never per scan. This
supersedes older paid-but-unattended revenue descriptions below.

Current correction: revenue follows the existing effective payment mode, not a
hardcoded live-only filter. Test includes test payments only; live includes live
payments only. Summary, charts, refund breakdowns and transactions share that
scope. No new flags were added. The live-only descriptions below describe the
original implementation and are superseded by this rule; see
`C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend/OWNER_ANALYTICS_REPORT.md`.

## Scope and compatibility

Existing FastAPI/SQLAlchemy aggregation and React/Vite owner UI are extended.
The font, green/white palette, sidebar, header, gym selector, date picker and QR
scanner are retained. No database/schema changes or new dependencies.
No scanner/payment/membership-fulfillment behavior is replaced.

Existing APIs:
- GET `/api/v1/gym-owner/dashboard/summary`: existing fields retained; adds
  `attendance`, `generated_at`, and revenue components/exclusions. No-store.
- GET `/api/v1/gym-owner/gyms/{gym_id}/attendance`: now successful check-ins only,
  matching visit totals, not manual attendance flags. No-store.
- GET `/api/v1/gym-owner/gyms/{gym_id}/bookings`: adds optional
  `attendance_category`, applied before pagination using the dashboard's SQL rule.

All require the existing gym-owner role. All-gym queries filter Gym.owner_user_id;
selected gym and booking lists reject foreign/nonexistent gyms. No frontend
download-and-sum aggregation is used. The owner-wide query does not rerun solely
because the selected gym changes.

## Four sections

1. Overall Metrics: All Gyms — all owned gyms, visits, booking categories and revenue.
2. Selected Gym: Visits — four reconciling visit cards.
3. Selected Gym: Bookings and Attendance — disjoint categories, filtered booking
   links, existing booking preview and successful attendance list.
4. Selected Gym: Revenue — separate membership/booking sales and total, with
   expandable calculation/exclusion notes.

## Visit definitions

Only Checkin.status=SUCCESS records within the IST reporting range count.
Membership categories use the access type recorded at the door, falling back to
the linked membership type. Each successfully scanned booking visitor counts once,
not the reservation quantity. Existing scanner uniqueness and transactional replay
protection remain authoritative. Manual ATTENDED flags alone no longer add visits.
Cancelled or NO_SHOW booking rows are excluded, even with inconsistent historical
check-in data. Expired memberships retain their historical successful visits.

`total completed visits = multi-gym + single-gym + individual booking visits`.
Creating, confirming or paying for a booking cannot create a completed visit.

## Booking definitions

Date basis: scheduled slot_date, inclusive selected range, in IST.
Classification precedence is shared by dashboard and paginated booking filters:

1. CANCELLED booking -> cancelled.
2. CONFIRMED and explicitly NO_SHOW -> no_show.
3. CONFIRMED with at least one successful check-in -> attended (one booking).
4. CONFIRMED without a scan, with a future or still-open scheduled window -> upcoming.
5. PENDING_PAYMENT -> pending_payment; EXPIRED -> expired.
6. Remaining records -> unresolved, including old manual-attendance-only records.

The window comparison handles overnight slots. Past unmarked bookings are not
invented no-shows. A partially checked-in group is one attended booking but only
its checked-in people are visits. Legacy bookings.upcoming now uses the same
range/category rule instead of the former unbounded pending+confirmed count.
The UI explicitly exposes excluded/unresolved counts rather than making the four
featured categories appear to exhaust all reservations.

## Revenue definitions and assumptions requiring owner/accounting approval

**Not a cash-receipts, earned-revenue, net-settlement or gym-payout report.**
The schema has no immutable paid_at and no persisted partial-refund amount.
Payment.updated_at and checkout.updated_at are unsuitable: later reconciliation
can change them. Therefore both featured revenue components use the same
immutable checkout.created_at purchase-date cohort and current payment state.
The UI states this basis beside the range and in calculation notes.

- Single-Gym: sum UserMembership.paid_amount once per gym-linked Single-Gym sale.
- Individual bookings: sum Payment.amount once per booking (existing unique FK).
  A multi-booking checkout is NOT summed again; only each booking allocation is.
- Require both record PAID and linked checkout PAID, live mode, an external payment
  ID, supported Razorpay/Cashfree provider, and INR. Prices are authoritative final
  sale amounts, including discounts already applied at purchase.
- Total = Single-Gym membership component + individual booking component.
- Full refunds excluded and their original sale amounts reported separately.
- Partial refunds excluded entirely, with a count: exact remaining net is unknown.
- Sandbox, DUMMY, wallet test credits, unlinked legacy paid records and payments
  awaiting review are not treated as verified live business revenue. Exclusion
  counts make these omissions visible. This conservative policy needs confirmation
  if historical offline receipts or wallet funds should be recognized as real income.
- A cancelled booking with an unrefunded verified payment remains paid revenue;
  cancellation is not evidence of a refund.
- No membership revenue is added by visits. Multi-Gym sales have no existing
  gym-allocation model, so neither all-gyms nor selected-gym revenue allocates them.
- Non-INR records are not converted or combined into INR.

For settlement-date revenue, exact partial-refund net amounts, historical offline
receipts or Multi-Gym payouts, introduce a separately reviewed accounting contract
and durable paid/refund/allocation fields. This task does not fabricate them.

## Refresh and responsiveness

Shared owner-report hook refreshes visible reports every 30 seconds and on focus/
visibility return, skips refresh while a request is loading, and cleans listeners.
Navigating back from the scanner or booking mutations remounts fresh reports.
Cross-device check-ins and server webhooks appear on the next visible poll; this is
bounded polling, not a claim of instantaneous push updates. Existing resource keys
discard stale gym/date responses. Errors never silently become zero totals.

Cards use existing UI components and brand tokens; totals have a light green
emphasis. Four-column desktop grids reflow to two columns, with one column at very
narrow widths. Revenue cards stack on mobile. Existing mobile navigation and
booking-card rendering remain; tables have a bounded overflow container.

## Tests actually run

### MySQL strict-mode regression fix

The initial SQLite coverage missed MySQL error 1055 for the attendance query's
repeated `GROUP BY CASE` expression containing a correlated `EXISTS`. The fix uses
conditional `COUNT(CASE ...)` aggregates over the same category rule, without a
GROUP BY. No metric definitions, schema, or server SQL modes changed.

The new disposable MySQL tests reproduced HTTP 500 before the fix on both empty
and populated data. After the fix, the owner dashboard/business/date-range suite
and MySQL cases passed: **60 passed, pytest exit 0**. Tests explicitly enable
ONLY_FULL_GROUP_BY on each test connection and verify API responses, all/selected
gym counts, category-list reconciliation, empty owners and ownership checks.
The temporary database is dropped afterward; application data is not modified.

```powershell
Set-Location 'C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend'
$env:FITIGO_MYSQL_DASHBOARD_TESTS='1'
python -m pytest tests/test_owner_dashboard_mysql.py tests/test_owner_dashboard_metrics.py tests/test_owner_business_metrics.py tests/test_dashboard_date_ranges.py -q --disable-warnings
Remove-Item Env:FITIGO_MYSQL_DASHBOARD_TESTS
```

Requires a local development MySQL account with CREATE/DROP DATABASE permission.
New test file:
`C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend/tests/test_owner_dashboard_mysql.py`.

### Original dashboard implementation checks

- 133 backend tests passed (pytest exit 0): owner metrics, new business rules,
  date ranges, booking QR/scanner, Razorpay and Cashfree regression tests.
- 349 frontend Node tests passed.
- TypeScript typecheck and Vite production build passed.
- Python compileall and git diff whitespace check passed.
- Mocked Chrome owner-dashboard test passed, exit 0: overall/selected counts,
  category links, four sections, gym changes, stale responses, custom dates,
  loading/empty/error/retry states and no page overflow at 320, 360, 390, 768,
  1024 and 1440 px. Browser API data is fixture-only, not a production-data test.
- Scanner integration regression performs a real application QR validation in a
  disposable database, then repeats it and verifies dashboard visits remain one.
- The entire backend repository suite was not rerun for this task. No claim that
  unrelated legacy tests or live production accounting were certified.

Reproduce:

```powershell
Set-Location 'C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend'
python -m pytest tests/test_owner_dashboard_metrics.py tests/test_owner_business_metrics.py tests/test_dashboard_date_ranges.py tests/test_booking_access_qr.py tests/test_razorpay_payments.py tests/test_cashfree_payments.py -q --disable-warnings
Set-Location 'C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/frontend'
npm.cmd test
npm.cmd run typecheck
npm.cmd run build
# Requires Vite and an isolated Chrome DevTools instance listening on 9231:
node 'C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/frontend/scripts/owner-dashboard-browser.mjs'
```

## Files changed

- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend/app/services/owner_dashboard_service.py`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend/app/services/owner_metric_rules.py` (new)
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend/app/services/booking_service.py`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend/app/routers/gym_owner.py`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend/tests/test_owner_dashboard_metrics.py`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend/tests/test_owner_business_metrics.py` (new)
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend/tests/test_dashboard_date_ranges.py`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/frontend/src/owner/Dashboard.tsx`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/frontend/src/owner/Bookings.tsx`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/frontend/src/owner/UI.tsx`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/frontend/src/owner/useOwnerReport.ts` (new)
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/frontend/src/owner/owner.css`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/frontend/src/screens/GymOwner/api.ts`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/frontend/scripts/owner.test.mjs`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/frontend/scripts/owner-dashboard-browser.mjs`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend/OWNER_DASHBOARD_METRICS.md` (this report)