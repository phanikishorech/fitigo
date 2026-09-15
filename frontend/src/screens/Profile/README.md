# Profile Screen

Implements the multi-gym membership user dashboard.

Data is loaded from backend endpoints:
- `GET /api/v1/profile`
- `GET /api/v1/profile/membership`
- `GET /api/v1/profile/activity`
- `GET /api/v1/profile/bookings?status=upcoming|past|cancelled`
- `GET /api/v1/profile/membership/pass`

The QR code is currently displayed as an opaque payload string with a placeholder QR block.
If/when we add a QR generation library, replace the placeholder with an actual QR image.
