# Generic post-login return and route authorization

The existing session store, router, login UI, home pages and backend authorization are reused. No backend or business-rule changes are required.

## Behavior

- Anonymous protected-page navigation and existing auth-triggering actions save a per-tab return intent and enter `/login`.
- A verified backend identity decides access to the saved route. CUSTOMER/USER fall back to `/home`; GYM_OWNER/GYM_STAFF to `/owner/dashboard`; ADMIN/SUPER_ADMIN to `/admin/dashboard`.
- Existing staff restrictions are preserved. The actual owner report routes are `/owner/revenue` and `/owner/analytics`, not `/owner/reports`; staff cannot access owner finances. No invented routes or additional staff permissions were added.
- Return intents preserve pathname, query and hash, survive reload in sessionStorage, expire after 30 minutes, and are cleared after authorized route restoration or action claim. Logout clears them immediately.
- Direct login without an intent goes home. Already-authenticated visits to login use the same return priority. Legacy `?returnTo=` values are validated centrally for all portals.
- Session expiration preserves the current location. Technical session errors retain the intent and show retry, not a false logout. Invalid roles still fail closed.
- Normal discovery remains public. Backend authentication, ownership, eligibility and transaction checks remain the security boundary.

## Safety

Only recognized internal routes can be returned to. External/protocol-relative URLs, encoded paths, backslashes, dot-segment normalization, unknown routes and auth-loop destinations are rejected. URLs containing explicitly sensitive credential/payment fields are not persisted; fallback Home applies. Do not put personal information or secrets into route query parameters.

Action metadata is centrally allowlisted to non-sensitive entity identifiers. Never include tokens, QR values, passwords, payment amounts, quotes or form contents. An unregistered, invalid or unauthorized action cannot execute. A restored intent is bound to the verified user ID and checked again before consumption.

`consumeReturnIntent` atomically claims the action before invoking its existing handler. StrictMode/rerenders/refresh cannot replay it. The existing page owns backend validation, errors and retry after the claim; automatic mutation retries are not introduced.

## Generic integrations

`requestAuthentication()` captures the exact current location. Optional overrides specify a target route when the existing flow is already continuing there. Existing `openAuthModal` callers now enter the existing login page; on login routes it still opens the existing modal.

```ts
requestAuthentication({ action: 'BOOK_VISIT', metadata: { gymId: String(gymId) } })
// In the existing Gym page's flow hook:
usePendingAction('BOOK_VISIT', () => book())
```

`definePendingAction` supplies central roles, allowed metadata keys, a route/ID matcher and `resume: 'handler' | 'page'`. Add a handler registration through `usePendingAction` for future non-navigation actions; its readiness guard can wait for existing query data. Do not build a second business-flow implementation.

Implemented handler examples:
- BOOK_VISIT: reruns the existing backend eligibility check and popup/paid-routing decision.
- ADD_TO_CART: uses the existing booking draft and validation/service. Drafts remain in their existing in-memory store, never serialized in auth intent. If the page is refreshed and selections are lost, existing form validation asks the user to select them again rather than guessing.

Page continuations include VIEW_MEMBERSHIP, EDIT_GYM, EDIT_PROFILE and VIEW_REPORT. Plain page return requires no action registration at all.

PAYMENT, CHECK_IN and destructive actions are not automatically replayed. Their pages return normally, with existing confirmation, quotes, permissions and scanning rules. An interrupted operation might already have succeeded on the server; blindly replaying it would be unsafe.

## Exact files changed for this feature

### Session/navigation
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\session\returnIntent.ts` — new per-tab storage, sanitization, TTL, capture, login resolution and one-time consumption.
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\session\pendingActions.ts` — new generic action definition registry, role/route/metadata guards.
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\session\usePendingAction.ts` — new hook to claim and resume existing page handlers once they are ready.
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\session\policy.ts` — centralized allowed-role metadata and known-route validation reusing existing route parsers.
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\session\store.ts` — post-login resolution, expiration capture and logout cleanup.
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\session\SessionGuard.tsx` — captures protected locations, resolves authenticated login visits, consumes page returns and restores anchors.
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\authUi.ts` — adapts existing authentication triggers to centralized continuation.
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\App.tsx` — tracks fragment changes without remounting pages when a reset-token fragment is removed.
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\router.ts` — subscribes to hash navigation alongside existing history events.

### Existing flow adapters
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\pages\CustomerApp.tsx` — login delegates return policy to the shared layer.
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\components\navigation\CustomerShell.tsx` — sign-in preserves full location; avoids overriding saved anchor scrolling.
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\hooks\useBookVisit.ts` — registers BOOK_VISIT without duplicating backend decision logic.
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\pages\booking\BookingPage.tsx` — registers ADD_TO_CART using the existing validated add handler.

### Verification/documentation
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\scripts\returnIntent.test.mjs` — new storage, authorization, tampering, action and URL safety tests.
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\scripts\session.test.mjs` — updates session dependency harness; retains role/session regression tests.
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\scripts\role-session-browser.mjs` — expanded real-UI fixture coverage for all portal returns, refresh, actions, error recovery, expiry, logout and loop prevention.
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\scripts\auth-account-browser.mjs` — checks requested route after signup/login instead of forced Home.
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\scripts\admin-browser-smoke.mjs` — checks saved admin destination before dashboard regression checks.
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\ROLE_ROUTING.md` — updates previous always-Home documentation.
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\RETURN_INTENTS.md` — this implementation and exact change manifest.

## Validation commands

Run from `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend`:

```text
npm test
npm run typecheck
npm run build
node scripts/role-session-browser.mjs
node scripts/auth-account-browser.mjs
node scripts/membership-browser-fixtures.mjs
node scripts/admin-browser-fixtures.mjs
node scripts/owner-scanner-browser.mjs
```

Browser tests use the running app with isolated intercepted API fixtures, not real payments/check-ins/account changes. Physical-device and live authenticated backend verification are separate. No new dependencies, router, authentication system, pages or Home UI were introduced.