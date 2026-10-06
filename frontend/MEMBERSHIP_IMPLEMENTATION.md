# Customer membership and daily access implementation

## Direct My Access QR update

`/my-access`, `/access/qr` without generation parameters, and `/profile/access/today` now show a read-only personal access overview. Backend calendar scope determines Single-Gym versus Multi-Gym; membership summary, owned records, assigned gym details and existing pause eligibility supply display information. Unknown/incomplete availability and failed requests show an error/retry, never a no-membership fallback.

Generate Visit QR explicitly opens `/access/qr?generate=1`. The existing QR hook rechecks read-only status, then calls the existing `/customer/access/today` endpoint without requiring a gym selection. Single-Gym shows its backend-assigned gym; Multi-Gym offers Find a Gym as a secondary link to the existing discovery flow. Existing gym-specific confirmation/QR links remain supported. Tokens stay in memory and are hidden on use, expiry, lost connectivity or hidden tabs; polling does not mint tokens. Pause changes during issuance retain the rejection and reload existing pause information.

The QR screen includes customer name, backend-issued membership scope, assigned gym or eligible-partner description, expiry and access status. No booking, cart or companion actions were added. Scanner, booking and backend business rules are unchanged.

Validation: `node scripts/my-access-browser.mjs`, `node scripts/membership-browser-fixtures.mjs`, frontend unit tests/typecheck/build, and isolated backend tests in `tests/test_my_access_direct_qr.py`, `tests/test_access_service_regressions.py`, `tests/test_membership_pause.py`, and `tests/test_membership_wallet_mvp.py`. Browser fixtures intercept all APIs; backend tests use disposable SQLite, not live customer records.

## Current membership pause update

Pause is now implemented for both membership types. Existing Owner/Admin plan editors configure policy; Customer membership cards/details and `/membership/pause` use verified eligibility, server preview, atomic scheduling, history and backend-derived status/expiry. Paused memberships remain visible. Future periods are scheduled, not immediately paused. Access/QR validation enforces the period and automatically resumes afterwards. No frontend limits or expiry calculations are authoritative.

Migration `6eb14f5a7c93` is applied locally; all existing plan policies remain disabled until configured. See `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\MEMBERSHIP_PAUSE.md` for the exact changes and operations. This supersedes historical pause-unavailable descriptions below.

## Current wallet MVP update

Membership checkout now supports backend-gated development wallet test credits for Single-Gym and Multi-Gym plans. Shared confirmation UI displays balance, current backend price, explicit test-credit limitations, safe errors and refresh/review after price changes. Single-Gym submits plan ID, server quote fingerprint and idempotency key; Multi-Gym submits its order and accepted fingerprint. Neither submits an authoritative price. Successful backend activation navigates to My Membership; Multi-Gym record/details handle null gym IDs using purchased terms. Recharge preserves membership-checkout return navigation.

Admin gym details now include explicit Multi-Gym participation opt-in. Discovery and QR validation share backend partner eligibility. Multiple Single-Gym plans do not grant entry to unrelated gyms. External payments remain unavailable; pause scheduling is covered by the current update above.

Migration `4c9f2d3e5a71` was applied to local development without changing existing balances, memberships, wallet transactions or check-ins. No partners were enabled automatically. See `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\MEMBERSHIP_WALLET_MVP.md` for current operational details. The remaining sections retain earlier implementation history; payments-disabled and count-based entitlement limitations described there are superseded by this update.

## Scope and architecture

The customer implementation extends the existing React 18 / TypeScript / Vite application and reuses its history router, shared API client, bearer-session handling, resource/mutation hooks and shared components. The initial access/booking UI work did not modify the backend. The subsequently authorized Multi-Gym catalog phase adds backend catalog, pricing and unpaid order APIs; it leaves existing entitlement and paid-booking behavior unchanged. No dependencies were added.

Implementation locations:

- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\pages\membership\MembershipOverview.tsx`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\pages\membership\FindGymPage.tsx`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\pages\access\ConfirmVisitPage.tsx`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\pages\access\AccessPage.tsx`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\pages\access\MembershipCalendar.tsx`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\components\membership\MembershipUI.tsx`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\hooks\useAccessQr.ts`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\hooks\useMembershipResource.ts`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\utils\membership.ts`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\membership.css`

Existing services in `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\services` were extended rather than replaced. Existing membership purchase behavior and production payment restrictions are preserved.

## Connected routes

### No-active-membership choices

The overview now uses explicit backend membership statuses, not an empty-array check or client-side expiry calculations. Active records take priority over historical records. Known non-active statuses show the Multi-Gym and Single-Gym paths; existing records remain accessible underneath, including paused records. Unknown statuses do not silently become a no-membership state. API failures still show retry.

The two-option section preserves the page heading and calendar link, uses two columns on desktop, and stacks on mobile. Single-Gym selection links to existing `/explore` discovery, gym details and gym-specific plan selection; no gym plan catalog is fetched on the empty overview.

**Multi-Gym catalog integration is now implemented with the authorized backend expansion.** `/membership/multi-gym/plans` consumes `GET /memberships/plans?membership_type=MULTI_GYM`. It renders real server ordering, pricing, active offers, badges, durations and benefits through reusable plan/price components. No pause allowance is advertised before pause enforcement exists. Loading, empty, safe error/retry and offer-boundary refresh are implemented.

Choose Plan posts only `plan_id` with an idempotency key to `/memberships/orders`, then opens the existing `/membership/checkout?orderId=…` route in an unpaid review mode. It shows refreshed backend prices and clearly states that no price is reserved, eligibility is not confirmed, payments are unavailable and no membership is activated. Payment initiation is blocked server-side as well as in the UI. Single-Gym checkout and paid-visit cart flows are unchanged.

Deployment requires the additive migration and backend plan configuration import described in `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\MULTI_GYM_FOUNDATIONS.md`. These operations have now been applied to the local development database to resolve the missing-table HTTP 500; the backend and frontend-proxied catalog return HTTP 200 with four configured plans and payments disabled. Other environments still require deployment. Backend pricing changes are picked up on navigation, page focus/visibility, active offer expiry, periodic visible-page refresh, and order creation/review; React never calculates discounts.

| Route | Behavior |
| --- | --- |
| `/membership`, `/profile/membership` | Real membership records, reported multi-gym summary, current access, history/calendar links |
| `/membership/:id` | Single-gym record from the authenticated membership list |
| `/membership/:id/details` | Available plan, scope, duration, dates, status and payment fields |
| `/gyms`, `/membership/gyms` | Protected membership gym selection using server-side INCLUDED filter, search, open-now/nearby filters and pagination |
| `/gyms/:id/visit` | Personal My Access alias; `?entry=book` renders the gym page and resumes its eligibility check/popup after login |
| `/my-access?gymId=:id` | Personal membership access only: selected gym, status, Generate Visit QR and membership information; no paid booking or companion actions |
| `/gyms/:id/book/schedule?for=others` | Existing BookingPage with additional-people count; member excluded from paid cart |
| `/access/qr?gymId=:id`, `/access/qr?generate=1` | Backend credential issuance and real-state QR lifecycle; direct generation requires no gym selection |
| `/access/qr`, `/my-access`, `/profile/access/today` | Read-only personal access overview with explicit Generate Visit QR; no automatic QR issuance |
| `/profile/access` | Monthly server-supplied account access calendar |
| `/profile/visits`, `/profile/history` | Actual validated membership visits by month; separate All access activity view |
| `/membership/pause` | Honest unavailable state; no fake date picker, preview, confirmation or success |

Existing profile, gym, booking and membership purchase links remain reachable. Mobile navigation is Home / Explore / Memberships / Profile. All new membership/access routes require the existing verified session guard. Browser back navigation uses the existing history system.

## Verified API contracts

Prefix: `/api/v1`.

| Purpose | Existing API | Important behavior |
| --- | --- | --- |
| Membership records | `GET /memberships/me` | Gym-bound records; no individual-detail endpoint needed |
| Account membership summary | `GET /profile/membership` | Backend-reported SINGLE_GYM/MULTI_GYM scope |
| Plans | `GET /memberships/gyms/:id/plans` | Existing public plans; an inactive historical plan may be absent |
| Eligible discovery | `GET /gyms/discover` | `membership_access=INCLUDED`, `search`, `open_now`, geo/sort, `page`, `page_size` |
| Fresh eligibility/details | `GET /gyms/:id/details` | Strict identity verified first; no cached eligibility used for QR requests |
| Read-only access and history | `GET /customer/access-calendar?year=&month=` | Explicit TODAY, qr_available and qr_status; all access dates use UTC |
| Credential issuance | `GET /customer/access/today` | Returns a backend-minted short-lived token or USED/PAUSED/EXPIRED/NO_ACCESS |
| Staff validation | `POST /checkins/validate` | Existing staff flow; never called from customer UI to simulate entry |

## QR and state safeguards

- Opening membership, calendar, history or My Access does not mint credentials. The Generate Visit QR action enters the QR route, which verifies fresh access (and inclusion for gym-specific links) before calling the existing issuance endpoint. Direct Multi-Gym generation does not require selecting a gym.
- The browser renders the exact backend token using the existing QR component. It does **not** generate random credentials, validity or successful scans.
- Tokens exist only in component memory, never in URLs, storage, logs or a read cache.
- A single-gym token cannot be presented as a different gym's QR.
- Fifteen-second visible-page polling reads the calendar, not the token-minting endpoint. Check-in success requires backend-recorded use/check-in evidence after QR display. Preexisting use renders Already Used.
- QR is cleared on server-provided expiry, offline events, hidden-page events and failed status verification. Renewal requires another backend check; local time is never used to grant access.
- In-flight guards prevent duplicate issue requests and ignore stale responses. React StrictMode behavior is covered by a browser test.
- AVAILABLE requires explicit backend qr_available=true and ACTIVE qr_status for the backend's TODAY row. No membership date/count arithmetic decides access.
- VISITED, USED without visit details, NO_VISIT/consumed, PAUSED, EXPIRED, FUTURE and NONE remain distinct. Actual-visits history excludes consumed and paused days.
- Shared errors expose only allowlisted business codes; no structured/raw diagnostics are rendered. Known access and pause codes receive customer-readable messages. Unknown states fail closed.

## Backend gaps: intentionally not fabricated

1. **Pause scheduling is unavailable.** Both local routers and the running OpenAPI document expose zero pause endpoints. There is no allowance validation, preview, submission, cancellation of a pause, resume date, original expiry or updated-expiry contract. The existing summary returns fixed MVP pause values (60 remaining / 0 used), not verified plan-specific allowances. Those values are deliberately not presented as usable entitlements. Pause date selection, confirmation and success cannot be implemented truthfully against this backend.
2. **Multi-gym product contract differs from the specification.** The backend derives multi-gym access from more than one active gym-bound membership. It does not provide a distinct purchased multi-gym plan record. Summary scope is displayed as returned; individual purchased plans remain gym-bound records. Discovery/details mark individual memberships INCLUDED, while the scanner's multi-gym logic is broader. This inconsistency must be resolved on the backend before promising every partnered gym is eligible. The frontend allows only explicitly INCLUDED locations.
3. **No gym-bound multi-gym issuance.** The existing token endpoint accepts neither gym ID nor membership ID. Selected gym is presentation context; an account-wide token is not falsely described as a gym-bound reservation. The QR screen explains this.
4. **No pause/expiry reconstruction.** UI never calculates extended expiry, daily balances, days used/remaining, future pause allowance or a resume date. It does not label backend booking counts as daily entitlements.
5. **Account-level history only.** Calendar does not accept membership ID, so it is labelled account access activity, not per-plan history. The Actual visits tab reflects calendar check-ins; non-visited access days are separate. General bookings remain at `/bookings`.
6. **Membership status may differ from access state.** Raw membership status is rendered as returned. Calendar is authoritative for current access. No local date comparison relabels a record EXPIRED. “Next access tomorrow” is qualified by the need for backend eligibility; the API does not promise tomorrow's access.
7. **QR response is a token, not an image.** The existing tested renderer encodes that server credential into a QR. No new QR library or credential algorithm was introduced.
8. **No attached screen reference was available.** The only workspace WebP inspected was a gym photograph, not the membership UI reference. Visual work follows the written specification and existing FitiGo theme. A claim of screenshot-for-screenshot reference parity would be inaccurate.

## Validation and limits

Run from `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend`:

```powershell
npm run typecheck
npm test
npm run build
node scripts/membership-live-check.mjs
node scripts/membership-browser-fixtures.mjs
```

- 171 frontend tests pass, including 26 membership tests and 21 membership-aware booking routing, popup, isolation and contract tests.
- TypeScript and production build pass. New screens are lazy-loaded.
- Live read-only checks verified the current OpenAPI contracts, absence of pause endpoints, public discovery, available gym details and membership plans.
- Authenticated live checks are optional via `FITIGO_TEST_EMAIL` / `FITIGO_TEST_PASSWORD`; they were **not run with a dedicated customer account**. No accounts, balances, memberships, pause records or check-ins were created/modified for this work.
- Browser fixture suite passed widths 360, 375, 390, 430, 768, 1024, 1280, 1440 and 1920; no page overflow; desktop/mobile screenshots reviewed.
- Browser fixture suite covers single/multi membership, details, navigation, gym search/eligibility, confirmation, single QR issuance, polling without reminting, backend-reported successful check-in, already-used, paused, unavailable/ineligible, QR expiry, offline hiding/retry, calendar vs visits, no-membership, expired membership and sanitized network/server/business errors.
- Fixtures are exclusively in test scripts, never application imports or production assets. They verify UI behavior, **not** a real staff scan or backend authorization correctness.
- Actual device scanning, screen-reader audit and full authenticated live membership-to-staff-check-in testing remain release checks. Pause scheduling and exact multi-gym product semantics remain blocked by backend contracts.

Browser fixture tests reuse the existing Chrome CDP setup on port 9231 and frontend port 5173. They clean test browser credentials and disable interception afterward. The live checker reads the actual backend on port 8000 and never issues access QR or calls staff validation.

## Finalized membership-aware Book a Visit flow

Gym Details retains Book a Visit and View Membership Plans. The earlier separate membership-access card/CTA was removed. Desktop and mobile Book a Visit buttons share one locked asynchronous handler, show loading until the access decision resolves, and show a retry without navigating on failure. Signed-out users authenticate through the existing modal with a return intent that rechecks access instead of preselecting paid booking.

The orchestration service at `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\services\visitAccessService.ts` composes existing fresh gym details and read-only daily calendar responses; it is not another API client. Explicit INCLUDED plus available daily access opens a popup on the gym page, with a server-reported single-gym association check where applicable. No navigation happens before the customer chooses. Explicit non-inclusion/paused/expired/no-access states route to the existing paid booking UI. **Already-used access also goes directly to normal paid booking when Book a Visit is clicked**, with no popup or My Access redirect. Unknown/incomplete states raise an error, not an assumed paid booking.

The popup title is “You have an active membership”, followed by “Choose how you want to continue.” It has exactly two buttons: **Use My Membership** and **Book for Others**. There is no Cancel or close-icon button. The existing native dialog provides focus containment, Escape/backdrop dismissal and focus restoration. It is centered on desktop and a bottom sheet on mobile. Other existing dialogs keep their close button by default.

Use My Membership opens `/my-access?gymId=:id`. Book for Others goes directly to `/gyms/:id/book/schedule?for=others`, without entering My Access. My Access contains no companion section, friend/family text or paid-booking links in available, unavailable or used states. Directly opening My Access after use still renders the personal USED state without QR or booking actions.

Book for Others appears **only in the gym-page popup**. It reuses `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\pages\booking\BookingPage.tsx`, existing people-count controls, time inputs, pricing, cart service, checkout, payment and confirmation. A thin eligibility wrapper protects direct companion URLs. Companion drafts are isolated from normal drafts, use the backend's TODAY date and gym/day-visit mode, and count **additional people only**. Access is rechecked before cart submission. If it has become used or unavailable, no companion POST is sent; the normal booking flow opens instead. No zero-price self item, discount, or extra member is sent to the cart. Self is shown as Covered by membership / not part of the paid cart, rather than inventing a ₹0 amount field that the backend does not return.

### Verified refinement behavior

- Fixture browser tests passed matching single-gym and included multi-gym popup behavior, incompatible-gym paid routing, paused/no-access/used direct paid routing, pending and failure/retry behavior.
- Popup tests verify exactly two buttons, no premature navigation, keyboard focus inside the dialog, Escape dismissal, both choices, and the post-login resumption path. My Access is verified to have no companion or paid-booking controls.
- Two companions submitted member_count=2 to the existing cart endpoint. The unchanged cart → checkout → wallet confirmation → booking confirmation path passed with test-only responses.
- A change to USED between loading the companion form and submitting it prevented the cart POST and opened normal paid booking, not My Access.
- Normal booking still submits its original member count and uses the same cart endpoint. Membership-plan navigation remains unchanged.
- Gym Details, the popup and My Access were checked at 360/375/390/430/768/1024/1280/1440; desktop modal and mobile bottom-sheet screenshots reviewed.

### Remaining contract limitations

- The existing cart supports anonymous people count, **not saved friend/family profiles or named attendee selection**. The UI uses the real count-based functionality rather than simulating a contact list.
- Cart records identify the purchaser and quantity, not individual companion entitlements. They do not return a separate covered-self price or companion allocation. Checkout remains accurate for the paid quantity, but the UI cannot claim individual named passes were issued.
- Companion eligibility checks and cart insertion are separate requests. The backend has no atomic membership-aware companion action/capability. Frontend checks are UX safeguards, not security guarantees; a server-side race or direct API request must still be handled by backend authorization/business rules.
- Existing cart deduplication replaces the quantity for an identical gym/date/time window. This behavior is preserved, not silently redesigned into additive companion cart lines.
- Existing multi-gym discovery vs scanning inconsistency and absence of gym-bound QR issuance remain as documented above. Real authenticated payment and staff-scan sign-off are still outstanding; fixture checkout is not proof of a live financial transaction.