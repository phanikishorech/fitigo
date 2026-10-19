# Shared membership and booking QR access

## IST-only business time (October 9, 2026)

All booking selections, gym/class operating times, access windows, customer/staff
displays, membership daily reset, pause dates, and booking/report day filters use
**India Standard Time (Asia/Kolkata, +05:30)**. This supersedes the initial UTC
business-time convention. A selected 18:00 remains 18:00 IST; stored DATE/TIME
booking and gym-hour values are not shifted or rewritten.

Booking options return `booking_timezone: "Asia/Kolkata"` and `server_now` with
`+05:30`. Booking, membership, QR and check-in timestamp responses serialize in
IST. Frontend formatting is pinned to Asia/Kolkata regardless of device timezone.
Calendar exports include an Asia/Kolkata timezone definition. Daily membership
access and pause transitions happen at midnight IST, not midnight UTC.

Existing absolute audit timestamps keep their original storage meaning. UTC
normalization remains **only at the legacy database/audit boundary** and for
protocol-level security timestamps, not as a selectable/display/business timezone.
Relabelling historical audit values as IST would corrupt payment/check-in history.
No data migration, customer debit, refund, or booking-time rewrite was performed.

Reopen Show Booking QR after deployment: old credentials retain their original
issued bounds; fresh credentials use IST booking windows. Old membership QR codes
also remain subject to the current IST access date and the normal short expiry.

Verified: 146 isolated backend tests, 316 frontend tests, two disposable MySQL
concurrency/migration tests, TypeScript and production build; browser checks for
booking selection on a foreign-timezone device, booking QR, and My Access.
Read-only live API checks confirmed Asia/Kolkata/+05:30 and unchanged booking dates.

## Deployment

Apply migration `7fc25a6b8d04` before starting the updated API. The application
database was not migrated during initial implementation; the local database was
subsequently upgraded during the October 8, 2026 recovery described below.
Back up each deployment database first.

```powershell
Set-Location 'C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend'
& .venv\Scripts\python.exe -m alembic upgrade head
```

The migration extends `access_qr_tokens`, `checkins`, `bookings`, and `cart_items`;
it creates no parallel access/check-in tables. Existing membership check-ins get
their membership reference backfilled; historical scanner identity stays unknown.
Downgrading refuses to discard booking access records. Archive those explicitly
before attempting a downgrade.

### Local recovery: October 8, 2026

The local `fitigo` database was one revision behind, causing the profile bookings
query to fail on `bookings.visitor_names`. A full database backup was saved to
`C:\Users\ckishor\.cline\data\backups\fitigo\before_booking_qr_20261008_230634.sql`.

MySQL initially blocked the upgrade because QR row 221 referenced missing daily
access 201. That QR expired October 2, 2026, was unused, and had no check-in
references. It was archived to
`C:\Users\ckishor\.cline\data\backups\fitigo\orphan_qr_221_before_booking_qr.json`
before that single unusable row was removed. No bookings or check-ins were deleted.
Foreign-key checks were not disabled.

The migration now checks existing access foreign keys before DDL and resumes
partially applied MySQL upgrades by inspecting columns and constraints. It does
not automatically delete corrupt records or stamp an incomplete schema as current.
After recovery, all required columns were verified, Alembic reported
`7fc25a6b8d04 (head)`, and the previously failing profile bookings handler succeeded.
Regression checks: 37 focused tests and 2 disposable MySQL concurrency/migration
tests passed, including partial-DDL recovery and orphan preflight rejection.

## Contracts and business separation

- Existing cart, wallet checkout, booking creation/payment, cancellation, and
  membership QR routes remain in use.
- `POST /api/v1/bookings/{id}/qr` authorizes the purchaser and returns opaque
  visitor QR tokens, server-provided validity timestamps, and access source.
  Responses are `no-store`. Each explicit opening rotates the token reference;
  older screenshots fail. Only hashes are stored in the database.
- `POST /api/v1/bookings/{id}/visitors` permits one-time visitor assignment for
  older unnamed confirmed bookings, by their purchaser only.
- Booking detail and profile booking responses expose backend `qr_available`,
  status/message, visitor pass statuses, and check-in timestamps. Frontend code
  does not infer payment/access eligibility or construct trusted payloads.
- The existing `POST /api/v1/checkins/validate` resolves the QR source server-side.
  Assigned staff and the scanning gym's owner are authorized. Other owners/staff
  cannot scan for that gym. Business rejection is a normal response, not HTTP 500.
- `MEMBERSHIP_ACCESS` retains the existing daily entitlement rules and
  Single-Gym/Multi-Gym scope. Membership-covered legacy bookings explicitly remain
  membership access; they cannot mint an extra paid-booking entry.
- `BOOKING_ACCESS` has its own confirmed/paid booking, visitors, slot, and one-time
  entries. Booking check-ins do not consume membership access or appear as
  membership calendar usage. Free wallet bookings are not inferred to be memberships.

## Visitors and consumption

The old Book for Others contract supplied only a quantity. The existing scheduling
form now collects a name for each actual visitor and carries names through cart
and checkout. The purchaser remains `Booking.user_id`. Guest names are not silently
linked to arbitrary registered accounts.

One token record is created per paid place in the same transaction that confirms
payment. A group booking therefore has one QR per visitor, not one reusable group
QR. Each successful scan creates a shared check-in with booking/source/visitor,
QR, gym, scanner identity, and timestamp. The booking becomes `ATTENDED` after all
places have checked in; its existing booking status remains `CONFIRMED`.

Booking locks and unique booking/visitor constraints prevent double admission.
Cancellation, refund/failure, manual attended marking, and rescheduling are
serialized with scans. Cancellation/refund revokes unused QR records; validation
also rechecks authoritative booking/payment state. Rescheduling rotates old
references; partially or fully used bookings cannot be rescheduled.

## Important operating limits

### Preferred gym visits and early entry

The active gym booking form uses hour/minute dropdowns with quarter-hour starts
(`00`, `15`, `30`, `45`) and a read-only one-hour end time. The gym cart API derives
the end time when omitted and rejects non-quarter starts or a supplied end time
that differs from start + one hour. Both checkout routes revalidate the policy;
older custom-duration cart items must be removed and selected again. A complete
one-hour visit must fit inside the day's configured operating hours. This does
not change scheduled class durations or existing purchased booking records.

Paid gym QR entry runs from **max(preferred start minus one hour, opening time)**
until **closing time**, with closing exclusive. Special hours override weekly
hours. Missing, closed, or unsupported overnight operating hours fail closed,
rather than inventing a closing time. The current same-day booking convention
and IST timezone apply; scheduled classes retain their session window
and membership access retains its daily rules.

Example: 18:00–19:00 preferred visit, gym closes at 22:00 → one entry allowed
from 17:00 until 22:00, provided the gym is open. QR issuance and booking details
return these server-calculated validity timestamps. Validation rechecks current
hours and payment/status/one-time rules. Existing QR screenshots keep their issued
validity bounds: reopen Show Booking QR to receive the new window. No database
migration or bulk change to customer bookings is required.

### Past-time purchase protection

Booking creation, gym/class add-to-cart, both cart checkout routes, pending-booking
payment (including admin confirmation), and changed reschedule targets require a
strictly future IST start time. An already-started visit is not purchasable even
if its end time is still in the future. QR check-in remains a separate policy:
previously purchased visits can still be scanned within their allowed window.

Checkout rechecks time after lock waits and before committing. If any basket item
becomes stale, the transaction rolls back wallet debit, transaction/payment rows,
capacity, bookings, and QR creation. The API returns `BOOKING_TIME_PASSED`; the UI
keeps the customer on checkout and displays that no payment was taken. Cart items
remain available to remove and replace with a future visit.

The booking form receives `server_now` and `booking_timezone` from booking options,
labels inputs IST, advances its minimum start time, disables past class sessions,
and checks again on submit. These are UX checks, not substitutes for server checks.
No schema migration is required for this protection.

This change does **not** retroactively refund previously charged bookings. In
particular, existing cancellation code changes payment status to REFUNDED without
issuing a wallet credit; do not mistake that status update for reimbursement.
Booking 1245 and its INR 150 payment were inspected read-only and left unchanged.

Validation: 112 focused backend tests, 307 frontend tests, TypeScript checking,
and isolated browser coverage for past-date/time prevention and future cart flow.

- Existing unnamed bookings cannot safely be assumed to represent the purchaser.
  They show an Add Visitor Details action before QR issuance. Older eligible paid
  bookings are lazily backfilled on assignment/issuance, rather than inventing names.
- Guest identity is name-based because no saved visitor/account-link model existed.
  Staff must verify that the person at the door matches the displayed visitor.
  Owner-only issuance blocks accessing someone else's booking through its ID;
  possession of a copied QR is not physical identity verification.
- Booking windows interpret slot/date selections in IST. There is no per-gym timezone
  model. Paid gym early-entry policy is described above. The QR contains no name, booking ID, or
  customer details. Server time and current booking/slot state are authoritative.
- Payment integrations are unchanged: existing wallet and DUMMY payment behavior
  remains MVP behavior, not a new real payment gateway integration.
- Existing manual attendance remains available; it blocks later QR entry but is
  not falsely recorded as a QR scan. Dedicated history/report screens are not added.

## Verification

87 focused isolated backend tests cover booking QR, migration, access regressions,
My Access, membership pause, platform membership and wallet behavior. The new
booking suite covers payment timing, wallet rollback, group visitors, ownership,
scanner authorization, expiry/date/window/gym checks, cancellation/refund,
replay, rotation, rescheduling, admin confirmation, and membership separation.

Two opt-in MySQL tests create uniquely named disposable databases, apply actual
Alembic migrations (including upgrade/downgrade/upgrade), and test simultaneous
same-visitor and distinct-visitor scans. The databases are removed afterward.

```powershell
Set-Location 'C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend'
& .venv\Scripts\python.exe -m pytest tests/test_booking_access_qr.py tests/test_booking_access_migration.py -q
$env:FITIGO_MYSQL_BOOKING_QR_TESTS = '1'
& .venv\Scripts\python.exe -m pytest tests/test_booking_access_mysql.py -q
Remove-Item Env:FITIGO_MYSQL_BOOKING_QR_TESTS
```

Frontend verification includes 300 Node tests, TypeScript checking, production
build, and isolated browser fixtures for booking QR, the continuous scanner, and
Single-Gym/Multi-Gym My Access. Browser suites intercept APIs; they do not create
live bookings. They require the existing local Vite server and debugging browser.
Physical camera/phone testing and a real payment-provider end-to-end run remain
deployment checks. The full legacy backend suite was not run because some of its
tests write directly to the configured application database.