# Dashboard date-range contract

Both owner and admin dashboard summaries accept inclusive `date_from` and `date_to` ISO dates. Defaults remain today in IST. A complete pair is required when either field is supplied; at most 366 days are allowed. Owner APIs continue to accept legacy `date`, but it cannot be combined with a range.

## Metrics

- `bookings.in_period`: all booking statuses scheduled between the selected dates.
- `bookings.confirmed_in_period`: currently CONFIRMED bookings scheduled between the selected dates.
- `revenue.in_period`: sum of currently PAID booking payment amounts for scheduled dates in range, consistent with the daily booking report. This is not settlement or payment-receipt-date accounting.
- Owner `visits`: successful check-ins and manual attendance in the range, with existing category and deduplication rules. Timestamps use UTC storage boundaries calculated from IST midnight. Manual records without timestamps fall back to scheduled date.
- Admin `users.in_period` and `gyms.in_period`: records created between IST midnight on the first day and exclusive midnight after the last day.
- Existing `today`, `upcoming`, `on_date`, `last_30d` and all-time counts remain for backward compatibility; their definitions do not change. New dashboard views use the explicit range fields.

Owner `gym_id` remains optional for the overall summary and is ownership-validated when supplied. Attendance requires a gym. Owner/admin booking lists also support the range before pagination. The daily report uses the same scheduled-date bounds; the frontend requests up to one row per selected day.

## Verification

Run the disposable tests from the backend directory:

```powershell
& .\.venv\Scripts\python.exe -m pytest tests/test_dashboard_date_ranges.py tests/test_owner_dashboard_metrics.py tests/test_booking_access_qr.py tests/test_access_service_regressions.py tests/test_my_access_direct_qr.py -q --disable-warnings
```

Frontend unit tests include preset calendar arithmetic, custom-range validation and API parameter propagation. The isolated Chrome fixture scripts `dashboard-ranges-browser.mjs` and `owner-dashboard-browser.mjs` cover both portals and owner scope/attendance behavior without changing live data.