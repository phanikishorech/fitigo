# FitiGo Admin Portal

## Controlled wallet MVP update

Gym details now include **Multi-Gym participation** with admin-only opt-in/disable confirmation. Only approved active gyms can be enabled. Backend eligibility and QR validation respect that setting; disabling participation blocks subsequent scans. No existing gym was automatically enrolled. Membership Plans notices now describe development test-credit checkout, not universally disabled membership payment. External payments and pause configuration remain unavailable. See `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\MEMBERSHIP_WALLET_MVP.md`.

## Entry points and scope

- Login: `/admin/login`
- Dashboard: `/admin` and `/admin/dashboard`
- Users: `/admin/users`, `/admin/users/:id`
- Gyms: `/admin/gyms`, `/admin/gyms/:id`, `/admin/gyms/:id/review`
- Bookings: `/admin/bookings`, `/admin/bookings/:id`
- Multi-Gym plans: `/admin/membership-plans`, `/admin/membership-plans/new`, `/admin/membership-plans/:id`, `/admin/membership-plans/:id/offer`
- Daily reports: `/admin/reports`
- Account events: `/admin/notifications`
- Read-only identity: `/admin/profile`
- Access denied/session expiration: `/admin/access-denied`, `/admin/session-expired`
- Unknown admin routes render a 404 inside the authenticated workspace.

Record statuses are backend-driven states of detail pages, not separate routes.
The original portal did not change the backend. The subsequent membership-plan screens use the authorized catalog APIs and add an admin-only offer configuration read endpoint. No additional database migration or payment behavior change is required for these screens.
No production mock data, invented metrics or new dependencies were added.
Legacy admin page components remain in the repository but are no longer routed or bundled.

## Membership Plans management

Open **Membership Plans** in the sidebar or mobile navigation. ADMIN and SUPER_ADMIN can create plans (inactive by default), edit base prices, durations, names, codes, descriptions, benefits, badges and display order, and show/hide plans in the customer catalog. Existing memberships are not changed.

Manage Offer configures percentage/fixed discounts, title, enabled state and schedule. The editor loads scheduled, expired and disabled offers, not just effective promotions. Times are explicitly UTC, with India offset guidance. Offers can be disabled with confirmation; no stacking or delete action is introduced. Pause configuration and payment activation remain unavailable.

Forms require confirmation and prevent duplicate pending submissions. Version conflicts retain form edits and require a fresh read; reloading prompts before discarding edits. Currently saved prices are backend values, not a frontend prediction of unsaved discounts. Reads and mutations use the existing admin resource hooks, shared API client and UI components.

The new `GET /api/v1/admin/membership-plans/{plan_id}` returns plan, offer_configuration, backend-evaluated offer state and server_time. It requires existing admin authorization, adds no database fields and exposes no private configuration in customer responses.

Validation: 192 frontend tests, 33 isolated backend/access tests, TypeScript and production build passed. New browser fixtures covered creation, pricing, scheduled/disabled offers, conflict reload, duplicate prevention, role denial, loading/empty/errors and eight viewport widths. Existing admin browser regressions passed. Live read-only checks verified endpoint registration, anonymous rejection, customer catalog health and disabled payments. Live prices and offers were not changed during testing.

## Architecture

Implementation root: `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\admin`

- `AdminApp.tsx`: lazy route modules, strict current identity, role check and backend admin authorization probe.
- `AdminLayout.tsx`: persistent sidebar, mobile dialog navigation, scoped platform search, account navigation and logout.
- `UI.tsx`: shared admin presentation primitives built on existing FitiGo buttons, modal, images, skeletons and links.
- `hooks.ts`: existing resource/state architecture, safe errors, search debounce, URL-based filters and pagination.
- `services.ts`: auth orchestration, daily report and notification contracts, supported public gym preview and admin summary lookup.
- Existing `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\screens\Admin\api.ts`: consolidated typed admin endpoints through the existing shared request client.

The root application reuses the existing history/navigation event system. Customer and owner entry points are unchanged.
Operational booking, identity and mutation responses are not cached. Lists refetch on navigation and after mutations. Dashboard widgets own independent resource loads.
Mutations use synchronous duplicate-submission locks, explicit confirmation, sanitized errors, success toasts and server reloads. No optimistic business-state or refund changes occur.

## Verified API mapping

| Capability | Existing endpoint | Notes |
| --- | --- | --- |
| Password login | `POST /api/v1/auth/login` | Existing auth service and token storage |
| Identity/roles | `GET /api/v1/users/me`, `/users/me/roles` | Only ADMIN/SUPER_ADMIN accepted |
| Server authorization | `GET /api/v1/admin/ping` | Required before mounting protected workspace |
| Logout | `POST /api/v1/auth/logout` | Refresh token revocation attempted; local credentials/cache cleared even on failure |
| Summary | `GET /api/v1/admin/dashboard/summary` | Total users, total gyms, today's bookings, last-30-day revenue |
| User list/detail | `GET /api/v1/admin/users`, `/admin/users/:id` | Search name/email/phone; role/status; offset/limit |
| User access | `POST /api/v1/admin/users/:id/status` | Status only; UI does not claim an audit reason is persisted |
| Gym list | `GET /api/v1/admin/gyms` | Name/city search, status, owner ID; offset/limit |
| Approve/reject | `POST /api/v1/admin/gyms/:id/approve`, `/reject` | Backend validates state; rejection reason 3–500 characters |
| Public gym preview | `GET /api/v1/gyms/:id` | Only APPROVED and enabled gyms are publicly readable |
| Booking list/detail | `GET /api/v1/admin/bookings`, `/admin/bookings/:id` | Name/email/gym/city search; date, gym ID, owner ID, status, payment status |
| Administrative cancellation | `POST /api/v1/admin/bookings/:id/cancel` | Optional reason, maximum 500 characters; detail reloaded afterward |
| Booking activity/report | `GET /api/v1/admin/reports/bookings/daily` | Date range, at most 366 reported dates; scheduled-date grouping |
| Account events | `GET /api/v1/notifications/me` | Paginated events; no invented unread counts/read action |

## Important backend limitations / release blockers

1. **No admin gym detail endpoint.** Pending, draft, rejected and suspended gym submissions cannot be fully reviewed: description, photos, facilities, hours, pricing and saved rejection reason/history are unavailable. The UI explicitly warns before approval. It does not access owner-only APIs. Direct gym links locate the matching summary through paginated descending-ID admin lists; this is an O(number-of-pages) workaround, not a scalable replacement for a detail endpoint.
2. **Dashboard metric mismatch.** The summary does not expose active-gym count or today's revenue. The UI accurately labels total gyms and last-30-day revenue. It does not rename these values to the requested unsupported metrics. The summary's reporting day is controlled by the backend; the display date follows the browser, and the API does not expose a reporting timezone.
3. **No pagination totals.** UI shows returned windows and previous/next, never fabricated totals. The backend applies user-role filtering after pagination; role pages may be sparse or empty. A parallel unfiltered 21-row window determines whether another raw server page exists. This limitation is explained in the UI.
4. **Status differences.** Gyms use APPROVED, not ACTIVE; bookings expose PENDING_PAYMENT, CONFIRMED, CANCELLED and EXPIRED; payment states include INITIATED, PAID, FAILED and REFUNDED. Badges display actual values. No unsupported filter enums or synthetic FORCE_CANCELLED status are sent.
5. **Cancellation refund semantics.** Existing backend cancellation updates a paid payment record to REFUNDED. This is not proof that funds were returned through a real gateway/bank. Confirmation explicitly avoids claiming a settled financial refund. Production payment/refund integration must be verified independently.
6. **No per-record action eligibility contract.** Existing action controls submit administrator requests; the backend decides authorization and transition validity. The UI does not infer permissions from dates or record statuses. Backend hardening and allowed-action metadata would improve operational safety, particularly user-status changes.
7. **Unavailable features are not simulated.** Audit logs, settings editing, last-login/activity metrics, paid-at/refund timestamps, booking type filters, future/past booking filters and gym resubmission are not exposed by verified contracts. Planned audit navigation is noninteractive. Settings/audit URLs explain unavailability.
8. **Search limitations.** Booking list `q` does not search booking ID or owner name. Gym `q` searches name/city, not gym ID/owner name. Labels reflect supported fields. Direct numeric record URLs remain supported.
9. **Authentication remains the existing architecture.** Browser token storage is reused, not replaced. There is no newly invented password recovery, OTP-only flow or refresh-token policy. Security review of token storage, CSP, HTTPS, backend authorization and session lifecycle is still needed before deployment.
10. **Live authenticated QA blocked.** The documented development admin credentials were rejected by the running backend. No account was created, reset or elevated, and no real business data was mutated to bypass that blocker. Full live approval/cancellation testing requires a valid test administrator and dedicated backend test records.

## Validation

Working directory for all commands: `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend`

```powershell
npm run typecheck
npm test
npm run build
node scripts/admin-browser-smoke.mjs
node scripts/admin-browser-fixtures.mjs
```

- TypeScript and production build passed.
- Existing customer/owner tests and admin route/service contract tests passed (124 total).
- Live unauthenticated browser checks passed: login, guarded-route redirect, denied/expired pages, responsive widths 360/390/430/768/1024/1280/1440/1920.
- Isolated browser fixtures passed: dashboard at all eight widths; lists/details/reports/profile; mobile navigation and Escape; confirmation dialogs; debounced search and retained filters; empty/404 states; approval/rejection/user-status/cancellation refresh; duplicate-submit lock; conflict/500/network/403 errors and retry; 401 session expiration and non-admin rejection.
- Desktop/mobile screenshots were inspected. Screenshots of authenticated views use **test fixtures**, not real platform metrics.
- Browser fixtures live exclusively in `scripts/admin-browser-fixtures.mjs`, intercept only the test browser session, and are never imported by the application or production build. They validate frontend behavior, not real backend correctness.
- Existing backend integration tests were inspected but not executed because they create persistent users and business records in the configured database without cleanup.

Browser suites use the project's existing Chrome CDP setup on port 9231 and frontend port 5173. For authenticated **live** read-only checks, supply `FITIGO_TEST_EMAIL` and `FITIGO_TEST_PASSWORD` through the environment before running `admin-browser-smoke.mjs`. Never commit credentials. This suite cancels confirmation dialogs without performing real business mutations.

## Visual direction

No user-attached reference image was available in the conversation. Implementation follows the supplied hierarchy and existing FitiGo design language: green primary actions, white operational surfaces, restrained typography, 248px desktop sidebar, 72px header, responsive metric grid, mobile record cards and bottom-sheet filters. Login reuses the existing FitiGo gym visual asset. No generated screenshot is used as UI.