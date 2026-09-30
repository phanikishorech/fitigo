# FitiGo Owner Portal — implementation contract

## Repository audit

- React 18 / TypeScript strict / Vite; no routing, chart, camera, or state libraries installed.
- Reuse the existing History API router, token store, `services/client.ts`, `useResource`, `useMutation`, common UI and icon components. Customer and admin routes must remain intact.
- Existing owner models and service exports live in `src/screens/GymOwner/api.ts`; extend and migrate these to the shared request client, not a second HTTP client.
- API base is same-origin `/api/v1`; development proxy and `/uploads` proxy target localhost:8000. Production requires a same-origin reverse proxy. No frontend secrets.
- Shared customer green is #15803D. Owner surfaces use #F8FAFC, white, slate borders, and the same typography, controls and icons.

## Verified API-to-screen mapping

All paths below are relative to `/api/v1`. Audited against backend router, schema and service source, not the possibly stale OpenAPI snapshot.

| Screen | Existing contract |
| --- | --- |
| Login/register/verify | POST `/auth/login`, `/auth/register/gym-owner`, `/auth/email/send-otp`, `/auth/email/verify-otp`; GET `/users/me`, `/users/me/roles` |
| Session logout | POST `/auth/logout` with refresh token |
| Owner summary/revenue/analytics | GET `/gym-owner/dashboard/summary` — **all owned gyms**, fixed last-30-day revenue; no selected-gym/date filters |
| Gym selector/list | GET `/gym-owner/gyms` |
| Create/details/edit | POST `/gym-owner/gyms`; GET/PUT `/gym-owner/gyms/{id}` |
| Approval | POST `/gym-owner/gyms/{id}/submit`; only DRAFT submission supported |
| Photos | POST multipart `/gym-owner/gyms/{id}/images?is_cover=...`; PUT `/gym-owner/gyms/{id}/images/{imageId}/set-cover`; JPEG/PNG/WebP, 5 MiB maximum |
| Facilities | GET `/facilities`; PUT `/gym-owner/gyms/{id}/facilities` |
| Hours | PUT `/gym-owner/gyms/{id}/operating-hours`; Monday=0 |
| Membership plans | GET/POST `/gym-owner/gyms/{id}/membership-plans`; PUT/DELETE `/gym-owner/membership-plans/{id}`; POST `/{id}/activate` |
| Classes/slots | GET/POST `/gym-owner/gyms/{id}/slots`; PUT/DELETE `/gym-owner/slots/{id}`. Classes are slot entities, not a second resource. |
| Booking list/detail | GET `/gym-owner/gyms/{id}/bookings?date=&status=&limit=&offset=`; GET `/gym-owner/bookings/{id}` |
| Booking mutations | POST `/gym-owner/bookings/{id}/cancel`, `/mark-attended`, `/mark-no-show` |
| Staff | GET `/gym-owner/gyms/{id}/staff`; POST `/{id}/staff/invite`; DELETE `/{id}/staff/{userId}` |
| QR/check-in | POST `/checkins/validate` with `{gym_id, qr_token}` — validates AND records check-in atomically; GYM_STAFF + gym assignment required |
| Staff gym selector | GET `/gym-staff/gyms` |
| Notifications | GET `/notifications/me?limit=&offset=`; delivery status is NOT unread status |
| Profile | GET `/users/me`; editing not available |

## Explicit backend gaps / release blockers

No mock business data or substitute backend is introduced. Unsupported features display capability explanations rather than fabricated empty success states.

- No owner member directory, membership history, recent check-in list, selected-gym revenue, membership-sales metrics, historical trend series, or account/preferences update APIs.
- Owner summary revenue uses the backend MVP payment implementation; not settlement/accounting data.
- Booking responses do not include allowed actions/cancellation policies. Mutations are integrated at the service layer, but UI actions fail closed unless the backend provides explicit allowed actions. This deliberately leaves attendance/cancellation acceptance blocked rather than inventing eligibility. Existing backend attendance can overwrite prior attendance; backend concurrency/state protection is needed.
- QR endpoint rejects owner-only accounts. Do not grant roles or assign owners automatically. Assigned staff can use the scanner; owners see the permission limitation.
- No image delete/reorder, draft delete, gym type write field, map-search API, rejection reason, or submission timestamp in owner gym response. Do not infer these from updated_at.
- Staff list returns IDs/role only, no names, invite status or last-active. Invitation creates assignments directly and may return a temporary password. Do not claim an email invitation was delivered or display/log credentials.
- Slot owner responses omit schedule/trainer/description/availability. Creation supports date/repeat_days; edits preserve hidden schedule by omitting it. No invented booked/available values.
- Public `GET /gyms/{id}/slots?date=` provides authoritative **slot** availability for approved active gyms, and is now used by Slot Management. It is not the separate customer class-session availability contract.
- **Class synchronization blocker:** slot creation generates separate GymClass/ClassSession rows, but slot edit/deactivation does not update those rows. Repeating creation generates only the next 30 days. The UI explicitly warns about this; fixing backend synchronization is outside this frontend-only task.
- OTP delivery and production authentication/payment security require deployment verification; registration does not enforce verification backend-side.
- Native camera scanning is progressive enhancement; browser support and HTTPS matter. A QR-token paste fallback uses the same validation endpoint, never a member-ID bypass.

## Validation

Use existing `npm test`, `npm run typecheck`, `npm run build`, plus owner-specific route/service contract tests. Browser checks and remaining limitations are recorded after implementation.

### Results — September 30, 2026

- TypeScript strict check: passed.
- Production Vite build: passed; owner pages are lazy-loaded independently.
- Frontend automated suite: **100 passed** (62 existing + 38 owner route/service tests).
- Existing backend regression suite: **36 passed**. Existing datetime deprecation warnings remain; backend source was not changed.
- Real API/browser suite (isolated headless Chrome; no mocked HTTP): passed owner login, authenticated navigation, empty states, permission-aware owner check-in restriction, gym switching, seven-step draft persistence, plan create/edit/deactivate/reactivate, slot create/edit/deactivate, approval-dialog cancellation, server logout and token cleanup.
- Dashboard overflow checks passed at **360, 390, 430, 768, 1024, 1280, 1440 and 1920px**. Other owner screens/forms were checked at mobile, tablet and desktop widths. No uncaught JS exceptions or React console errors in the completed live suite.
- Login/register/verify forms rendered and validated. Registration was exercised through the actual API by the local QA bootstrap; email OTP delivery and verification were **not** completed because the local OTP delivery infrastructure is not configured.
- Actual camera hardware, successful member check-ins, photo uploads, staff invitation/removal and populated booking detail/attendance were **not end-to-end browser verified**. QR rejection/concurrency semantics remain covered by the existing backend tests, not claimed as camera-device testing.
- Browser-only QA used separate real local owners #3784, #3785 and #3786. Draft gyms #1629–#1636 were created during iterative checks; the final test draft has a QA membership plan and an inactive QA slot. No approvals, purchases, production invitations or existing account password changes were made. These records remain because there is no owner draft-delete API. Generated passwords were kept in process memory, not saved to source or logs.

### Acceptance disposition

Implemented against existing contracts: responsive shell/navigation, registration/password login/OTP forms, multi-gym selection, dashboard, draft wizard/save/edit/submit integration, approval state display, gym details/photos/cover/facilities/hours/day-pass pricing, membership plan CRUD/status, owner class/slot CRUD/status, public slot availability, paginated booking list/detail, staff assignment CRUD, permission-aware atomic QR validation, portfolio revenue/overview, profile display, notifications, logout, safe errors/loading/empty/unauthorized/not-found states.

Not complete / backend-blocked: owner-only QR authorization; membership directory and histories; recent check-in list; active member/attendance/day-revenue metrics; selected-gym/date-range revenue; financial trend charts; booking action eligibility and cancellation-policy metadata; rejection reason and submission timestamp; image delete/reorder; gym delete; fully synchronized customer class management; custom staff roles/delivery; profile/preferences/password updates. Today/all-dates bookings are supported; true server-side upcoming/past/search/payment/class filtering requires additional contract support. Current search/status/payment filters explicitly apply to the loaded page.

Booking mutation service functions and confirmation components exist, but action controls deliberately remain hidden for current responses with no `allowed_actions`. This is **not** a claim that attendance/cancellation works end-to-end in the new UI. Do not mark the user's full production acceptance checklist complete until the backend supplies authoritative action metadata and the remaining release blockers are resolved.

### Deployment requirements

Use HTTPS and an SPA fallback for `/owner/*`; proxy `/api/v1` and `/uploads` before that fallback. Retain the existing shared authentication contract, but review localStorage token handling, backend authorization, real OTP delivery, payment implementation and cross-tab/session expiry behavior before public release. The portal does not introduce a mock server, credentials, additional runtime packages, backend schema changes or financial estimates.