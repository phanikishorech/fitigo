# Customer notifications, cart badges and visit editing

## Behavior
- Customer header (including Home): notification bell with unread count and cart icon with unpaid visit-draft count. Counts are visits, not the number of people. Zero badges are hidden; values above 99 display 99+ with the full accessible label.
- `/notifications`: existing inbox, read actions and recorded-event history. Settings retains email preferences only. No notification delivery channels or account preferences are automatically enabled/changed.
- Counts load only after session verification, clear on sign-out/account change, refresh after relevant mutations, on focus/visibility, and every 60 seconds while visible. Cross-tab invalidation signals carry no account data. Failed count reads do not prevent navigation.
- Cart and pre-payment checkout show **Edit Visit** for editable drafts. `/cart/items/:id/edit` reuses the booking form, prefilled from the authenticated backend item. Change date/time or class session, number of people and visitor names; save updates the same item. Cancel makes no backend changes. Editing cannot change the gym or access type.
- Payment-pending, confirmed, removed and checkout-linked items cannot be edited. This feature does not reschedule paid bookings. Cancel/review an existing payment through its existing flow first.

## Backend
- Added authenticated `GET /api/v1/cart/summary` (active, checkout-unlinked item count).
- Added owner-scoped `GET /api/v1/cart/items/{id}` and `PUT /api/v1/cart/items/{id}`.
- Cart responses include `can_edit` and `updated_at`. Update requests require `expected_updated_at` to reject stale writes. Existing MySQL timestamp second precision is accounted for.
- Edits lock gym → cart → class session, validate future start, one-hour gym duration, hours, class eligibility/capacity and visitor names; recalculate prices from database values. Duplicate destination drafts return a conflict. No delete/recreate, payment, capacity reservation or QR issuance occurs during edits.
- Cart routes use `Cache-Control: no-store`. Existing authorization remains enforced.
- No database migration, new dependency, global typography or theme-token changes.

## Main files
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\components\navigation\CustomerActivity.tsx`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\components\navigation\customerActivity.css`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\components\navigation\CustomerShell.tsx`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\components\common\NotificationCenter.tsx`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\pages\profile\NotificationsPage.tsx`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\pages\profile\SettingsPage.tsx`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\pages\booking\EditCartVisitPage.tsx`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\pages\booking\BookingPage.tsx`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\pages\booking\CartPage.tsx`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\components\payments\CheckoutVisitCard.tsx`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\services\customerActivity.ts`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\services\bookingService.ts`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\services\paymentService.ts`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\utils\cartEdit.ts`
- Routes/types updated in `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\customerRoutes.ts`, `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\pages\CustomerApp.tsx`, `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\screens\GymAccess\types.ts`.
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\routers\cart.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\schemas\cart.py`

## Tests
- Frontend suite: 438 passed; typecheck and production build passed.
- Backend isolated runner: cart-edit, MySQL concurrent-edit, booking-time, current-checkout, class-sync and notification regression suites passed (83 tests). Tests do not write working accounts.
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\scripts\customer-activity-browser.mjs`: mocked Chrome integration passed for Home badges, read updates, Settings separation, edit prefill/save/cancel/conflict, no duplicate item, count add/remove, checkout protection and anonymous privacy; widths 360/768/1024/1280/1440 verified without horizontal overflow.
- Existing `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\scripts\notifications-browser.mjs`: owner/admin notification regression passed.
- New unit tests: `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\scripts\customerActivity.test.mjs`, `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\tests\test_cart_edit.py`, `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\tests\test_cart_edit_mysql.py`. Existing customer-review/payment service test loaders were updated to mock the new invalidation helper.