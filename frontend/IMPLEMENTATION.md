# Customer application implementation

## Existing architecture
React 18, TypeScript, Vite 6, CSS Modules, native History API router. No router, icon, state, UI, payment or query libraries are added. Existing owner/admin screens remain separate. Existing bearer-token storage is preserved; production cookie authentication requires a backend contract change and is not simulated here.

## Verified API map (prefix /api/v1)
| Feature | Existing endpoint |
| --- | --- |
| OTP | POST /auth/email/send-otp, /auth/email/verify-otp, /auth/mobile/send-otp, /auth/mobile/verify-otp |
| Password login | POST /auth/login (email + password; token response uses existing session handler) |
| Account | GET /users/me, /users/me/roles, /profile |
| Location | GET /meta/locations?search= |
| Discovery | GET /gyms/discover; /meta/gym-types; /facilities |
| Gym | GET /gyms/{id}/details |
| Booking configuration | GET /gyms/{id}/booking-options, /operating-hours?date=, /class-sessions?date= |
| Legacy slot availability | POST /gyms/{id}/validate-booking (requires gym_slot_id; NOT a class_session_id) |
| Cart | GET /cart/items; POST /cart/items/gym, /cart/items/class; DELETE /cart/items/{id} |
| Payment | POST /cart/checkout/wallet |
| Wallet | GET /wallet/balance, /wallet/transactions; POST /wallet/topup |
| Membership | GET /memberships/gyms/{id}/plans; POST /memberships/gyms/{id}/purchase; GET /memberships/me, /profile/membership |
| Visits | GET /profile/bookings?status=upcoming\|past\|cancelled |
| Booking detail/cancel | GET /bookings/{id}; POST /bookings/{id}/cancel |
| Access | GET /customer/access-calendar?year=&month=, /customer/access/today |
| Staff | POST /checkins/validate |
| Reviews | GET, POST /gyms/{id}/reviews |

## Contract limitations / release blockers
- No save/remove favorite endpoints. /profile/favorites is computed from attended visits, not saved favorites. Do not represent it as persistent heart selections.
- Discovery has no day-pass price and supports rating/distance/recommended sorting only. No fabricated prices, ratings, review counts, trainer names, or amenities.
- New cart endpoints perform authoritative availability validation on add and payment. The legacy validate-booking endpoint cannot validate the newer cart model without a real slot ID. No invented availability endpoint.
- Cart has no update endpoint: users can remove an item and create a new booking; do not silently delete an item while editing it.
- Wallet topup is direct credit, not a payment gateway. Membership purchase uses MVP payment. New customer UI exposes these only in Vite development mode and labels them. A real payment backend is required before production transactions.
- No profile update, coupon, cancellation-policy, or dedicated review-eligibility endpoint. Unsupported operations must be explained, not mocked.
- Some existing backend endpoints fall back to a development customer without authentication. Frontend route guards do not fix server-side authorization; backend hardening is required before public deployment.
- Backend daily access/calendar use UTC. Never substitute local dates for the access contract.

## Verification
Baseline: TypeScript check passed; six existing QR encoder tests passed. Run `npm run typecheck`, `npm test`, and `npm run build` after each phase. Manual release checks must include authenticated booking, payment races, OTP delivery, staff scanning, and actual device/accessibility testing.

### Verified September 30, 2026
- TypeScript check and production build pass.
- 58 frontend tests pass: routes, login return-path safety, protected route classification, real class status values, minor-unit wallet comparisons, review eligibility, safe errors, invalid-token fallback prevention, read-cache behavior, and existing QR encoder tests.
- 14 existing backend access regression tests pass. Backend code was not modified. Existing UTC deprecation warnings remain.
- Read-only live API smoke checks returned HTTP 200 for health, gym types, locations, facilities, discovery, gym details, booking options, and membership plans.
- Isolated headless Chrome checks pass for home at 360, 390, 430, 768, 1024, 1280, and 1440px, with no page-level horizontal overflow.
- Browser checks pass for login modal, mobile filter sheet, gym details at mobile/desktop widths, access-to-schedule navigation, unauthenticated protected screens, direct login URL, and not-found state. No uncaught browser exceptions were observed.
- Browser testing caught a gym-detail intrinsic-grid-width overflow; fixed and rerun successfully.
- Customer, owner, and admin routes are code-split. Initial production JS is approximately 182 KB (59 KB gzip); initial CSS approximately 34 KB (8 KB gzip).

### Not verified / not complete
- Authenticated OTP delivery, cart-to-payment, insufficient-balance/recharge, membership activation, cancellation/refund behavior, and review submission have not been exercised end-to-end against a dedicated test customer. Do not interpret route tests as payment verification.
- Physical camera scanning, real phone/tablet browsers, screen readers, and full accessibility audits are not verified.
- The specification's price filters, persistent favorites, editable profile setup, coupon flow, per-visit reviewed status, cart edit action, and real production recharge/purchase cannot be completed against the current contracts. No fake data or invented endpoints were introduced.
- Home provides a real discovery grid and workout categories, not separate API-backed popular/classes/offers carousels. The new flow uses native date/time inputs rather than a fully availability-annotated booking calendar. Authentication remains a reusable modal, with URL aliases for login/OTP, rather than separate persisted OTP routes.
- Booking selection is centralized in memory and survives SPA login/navigation, but resets on a full browser refresh. Payment and booking status stay server-authoritative rather than persisted client-side.
- Calendar check-in history comes from the existing aggregated profile booking feed; review eligibility excludes synthetic negative membership check-in IDs because the review backend requires a real attended booking.
- There is no new fake payment service, mock customer data, or backend modification.

### Browser smoke runner
`C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\scripts\browser-smoke.mjs` uses native Node 24 WebSocket and an isolated Chrome debugging session on port 9229. It performs public reads and navigation only; it does not send OTPs, debit wallets, buy memberships, or write bookings. Run it with the frontend/backend already running. Screenshots are written to the OS temporary directory, not committed to the repository.

### OTP / password sign-in update — September 30, 2026
- Added an accessible OTP/Password selector, existing-account password form, show/hide control, form submission via Enter, readable login errors, and duplicate-request protection. Passwords remain in component memory and are cleared on successful login or form unmount.
- OTP email/mobile endpoints and post-login return intent are preserved. The modal explains the local OTP-delivery limitation.
- All 62 frontend tests pass. Browser checks verified switching methods, mobile OTP controls, 360px password layout, empty-submit prevention, wrong-password retry, and successful real password login returning to `/cart`.
- Optional `FITIGO_TEST_EMAIL` and `FITIGO_TEST_PASSWORD` environment variables enable the browser runner's authenticated checks; no credentials are hardcoded in the script or printed.
- The default seed customer password was rejected by the running database. One isolated local customer named `UI Password Test` was registered using the existing registration API to verify successful login. No existing user password, booking, membership, or wallet balance was modified.