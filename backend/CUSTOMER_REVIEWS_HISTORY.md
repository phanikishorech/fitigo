# Customer bookings, membership visit history and gym feedback

## Delivered

- Profile removes the duplicate Check-in history item.
- Upcoming visits is renamed My bookings, with All bookings / Upcoming / History
  tabs. Only BOOKING_ACCESS records appear, not membership-backed bookings or
  synthetic membership scan records. Zero price alone is no longer used to
  classify a booking as membership access.
- Membership visit history is shown in profile when any membership record exists,
  including past/expired memberships so previous visits remain accessible.
  `/profile/visits` and the old `/profile/history` alias now render the same
  paginated membership-only check-in history (month selection, IST).
- Reviews use the existing one-review-per-customer-per-gym table and public
  rating aggregation. Customers can rate 1–5 stars, add up to 2,000 characters of
  feedback, load/edit their existing review and see its moderation status.
- Successful submission invalidates cached gym details so updated ratings can
  load. Repeated submissions update the same review rather than inflate counts.
- Customer edits preserve HIDDEN status; only existing admin moderation routes
  can republish hidden reviews.

## Eligibility and access rules

Review submission and read-only eligibility use a shared SQL predicate:
customer-owned BOOKING_ACCESS booking, CONFIRMED, not NO_SHOW, PAID payment,
and at least one successful BOOKING_ACCESS check-in for the same booking, gym
and purchasing user. Manual ATTENDED alone, pending/failed/refunded payments,
cancelled visits and membership-only check-ins do not qualify. Group bookings
follow existing booking-level completion: one successful visitor check-in is
enough for the purchaser to submit one gym review; no extra guest accounts or
per-visitor reviews are invented. There is no checkout/exit event to validate.

The server revalidates on every POST. Optional booking_id binds new UI submissions
to that particular purchase; existing clients without booking_id must still have
an eligible individual booking at that gym. User-row locking serializes review
upserts; database gym/user uniqueness remains unchanged.

Membership history selects only SUCCESS check-ins with MEMBERSHIP_ACCESS and a
membership owned by the requesting customer. Individual bookings/check-ins cannot
leak into that list. Legacy rows without a linked authoritative membership are
not inferred as membership visits. Membership calendar and QR policies are unchanged.

## API changes (no migration)

- GET `/api/v1/profile`: adds `has_membership_history`.
- GET `/api/v1/profile/bookings`: accepts `source=individual` and optional
  `booking_id`; adds can_review/review_id/review_rating/review_status. Customer
  authentication is now explicit for this endpoint (no dev-user fallback).
  Default source=all remains for old callers; the updated customer UI always
  requests individual. Completed display status requires a successful check-in.
- GET `/api/v1/profile/bookings/{booking_id}/review`: owner-scoped eligibility,
  gym label and the customer's existing gym review, no-store.
- POST `/api/v1/gyms/{gym_id}/reviews`: existing route; optional booking_id,
  strict integer rating validation, no unexpected privilege fields, server-side
  successful-check-in eligibility. Same response/table/public-review routes.
- GET `/api/v1/profile/membership-visits?year=2026&month=10&limit=20&offset=0`:
  authenticated customer, no-store, successful membership check-ins only.

No new dependencies, schema changes, live review submissions or scanner changes.

## Validation actually run

- 136 backend tests passed: new review/history cases, moderation API regression,
  booking QR, direct My Access, membership pauses, Razorpay/Cashfree and safe errors.
- Separate strict-mode disposable MySQL concurrent review test passed, along
  with a 56-test review/access regression run.
- 367 frontend unit tests passed; TypeScript check and production build passed.
- Mocked Chrome test passed: conditional profile link, membership history,
  individual My bookings, eligibility rejection, required rating, comment,
  create/edit/pre-filled values, error retry, and no overflow at 360/768/1440px.
- An unrelated existing customer booking-detail test was also attempted and
  failed with BOOKING_TIME_PASSED because it schedules today's already-past time.
  It was not changed to bypass booking rules; the full repository suite is not
  claimed green. The old review/moderation test was converted from a real-DB,
  time-sensitive manual-attendance fixture to disposable actual-scanner coverage.

Commands:

```powershell
Set-Location 'C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend'
python -m pytest tests/test_customer_reviews_history.py tests/test_reviews_public_and_admin_hide.py tests/test_booking_access_qr.py tests/test_my_access_direct_qr.py tests/test_membership_pause.py tests/test_razorpay_payments.py tests/test_cashfree_payments.py tests/test_safe_errors.py -q --disable-warnings
$env:FITIGO_MYSQL_DASHBOARD_TESTS='1'
python -m pytest tests/test_reviews_mysql.py -q
Remove-Item Env:FITIGO_MYSQL_DASHBOARD_TESTS
Set-Location 'C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/frontend'
npm.cmd test
npm.cmd run typecheck
npm.cmd run build
# With Vite and isolated Chrome DevTools on 9231:
node 'C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/frontend/scripts/customer-reviews-browser.mjs'
```

## Files

- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend/app/services/review_service.py`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend/app/schemas/review.py`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend/app/schemas/profile.py`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend/app/routers/profile.py`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend/app/routers/gyms_public.py`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend/tests/test_customer_reviews_history.py`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend/tests/test_reviews_public_and_admin_hide.py`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend/tests/test_reviews_mysql.py`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/frontend/src/pages/profile/ProfilePage.tsx`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/frontend/src/pages/booking/BookingsPage.tsx`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/frontend/src/pages/booking/BookingDetailPage.tsx`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/frontend/src/pages/access/MembershipVisitHistory.tsx`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/frontend/src/pages/reviews/ReviewPage.tsx`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/frontend/src/pages/CustomerApp.tsx`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/frontend/src/services/accountService.ts`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/frontend/src/services/bookingService.ts`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/frontend/src/utils/booking.ts`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/frontend/scripts/customer.test.mjs`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/frontend/scripts/customerReviews.test.mjs`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/frontend/scripts/customer-reviews-browser.mjs`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend/CUSTOMER_REVIEWS_HISTORY.md`