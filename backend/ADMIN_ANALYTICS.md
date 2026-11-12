# Admin booking analytics

UI: `/admin/analytics`, linked from admin navigation, dashboard and Reports.
API: `GET /api/v1/admin/analytics`, ADMIN/SUPER_ADMIN only, Cache-Control no-store.
No migrations, additional dependencies, data seeding or provider requests.

## Filters and scope

- Inclusive `date_from` and `date_to`, at most 366 days; default last 30 IST days.
- `grain=day|week|month`; weeks start Monday, partial buckets clip to the range.
- Optional positive `gym_id`, and exact trimmed `country`, `state`, `city` filters.
  Empty location strings select missing values; absent parameters mean all.
- All activity uses scheduled booking DATE in IST, not purchase/capture timestamps.
- Previous period has identical length and ends the day before the current range.
- Current gym attributes are used; no historical location/status is inferred.

## Metrics

Bookings count reservations; places sum booked quantities across all statuses.
Unique customers count distinct purchasers, not visitors. Overall unique counts
are not the sum of per-gym counts. Confirmed/cancelled rates divide by all scoped
bookings; empty periods return null rates rather than invented percentages.

Attendance uses each booking's recorded ATTENDED/NO_SHOW status, not raw scan
counts. No-show is never inferred from missing attendance. These metrics do not
include separate membership daily access records.

Verified paid totals reuse `eligible_admin_payment`: matching verified PAID
gateway checkout/provider/customer, configured test/live mode, INR, positive
booking payment allocation and non-null gateway payment reference. Shared carts
are allocated per booking, never counted once per order on every booking.
Cancelled/no-show bookings still contribute while financially paid. Refunds,
partial refunds, review-required checkouts, wallet and unlinked legacy payments
are excluded from paid totals. These are not earned revenue or settlements.
Other payment-status counts include all modes and can overlap with review counts.

## Presentation and implementation

- Zero-activity gyms stay visible, and missing dates are zero-filled.
- Location rows distinguish the full country/state/city tuple.
- Summary, SQL gym/day aggregates, per-gym distinct counts and catalog options use
  a fixed number of queries, not one query per gym or a full booking-row download.
- Gym/location/period tables support search, descending metric/name sort and
  20-row display pages. CSV exports all matching table rows with date/mode scope.
- CSV escapes quotes and neutralizes spreadsheet formula prefixes.
- Plain React/CSS charts include an exact-values table and keyboard-scrollable
  regions. Responsive layouts preserve the existing admin colors/components.
- Financial/customer activity remains read-only. No reconciliation on report GET.

## Validation

Backend: run `tests/test_admin_analytics.py`, `tests/test_admin_financial_mysql.py`,
`tests/test_admin_financial_integrity.py` and `tests/test_dashboard_date_ranges.py`
through the fail-closed `backend/scripts/run_isolated_tests.py` runner only.
Tests cover both payment modes, grains, boundaries, previous periods, zero rows,
same-named cities, shared-cart allocation, authorization, no writes and strict MySQL.

Frontend: unit tests, typecheck/build and `frontend/scripts/admin-analytics-browser.mjs`.
Browser fixtures intercept all API requests; verify filters, CSV, pagination,
invalid dates, error/denied/empty states, keyboard use and 360/768/1440 layouts.
No browser fixture or sample booking is inserted into working data.