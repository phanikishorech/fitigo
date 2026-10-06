# Central role-based session and routing

## Existing destinations

| Backend role | Fallback home after login |
| --- | --- |
| CUSTOMER, USER | `/home` (existing Customer Home, unchanged) |
| GYM_OWNER, GYM_STAFF | `/owner/dashboard` (existing owner workspace) |
| ADMIN, SUPER_ADMIN | `/admin/dashboard` |

Staff reach the existing staff-workspace content at the owner dashboard route, not owner-only financial/management content. Existing backend staff assignment checks still apply to check-in.

For accounts with multiple supported backend roles, default-home precedence is admin, then owner/staff, then customer. This is navigation precedence only: the guard permits the portals for roles actually assigned by the backend. Missing, malformed or unknown roles fail closed; no role is inferred from email, URL, local storage, or decoded JWT claims.

## Session architecture

- Password login responses now include `user` and `roles` alongside existing tokens. Email/mobile OTP responses expose the same role information.
- `GET /api/v1/auth/session` returns the current active user's identity and database role assignments, protected by the existing authentication dependency. No migration is needed for this change.
- `src/session/store.ts` consumes login identity and restores/revalidates sessions through the shared API client. Tokens retain their existing persistence mechanism; roles are held only in memory and reloaded on refresh.
- `src/session/policy.ts` owns role/home and route-access policies.
- `src/session/SessionGuard.tsx` guards the application before role-specific pages mount. Portal shells consume the shared identity instead of independently fetching/checking roles.
- Login entry points remain available at `/login`, `/auth`, `/auth/login`, `/auth/otp`, `/owner/login`, and `/admin/login`. `/login` reuses the existing Customer sign-in UI, not a new home or duplicate login design.
- Successful login first restores a validated, role-authorized return intent. Home is only the fallback for missing, expired, invalid, or unauthorized intent. See `RETURN_INTENTS.md` for the generic action registry and integration details.
- Public discovery and gym previews remain available anonymously. Authenticated accounts are restricted to their assigned portals. Booking forms and account/checkout/member pages now require a verified session.

## Failure handling and logout

- No token: anonymous; protected routes capture path/query/hash and redirect to `/login`.
- Session restoration: loading UI, without mounting protected content.
- Bad password: existing inline login error, not a session-expiry redirect.
- HTTP 401 on an authenticated request: preserve current route context, clear tokens and show expired-session sign-in at `/login?expired=1`. Successful sign-in restores the authorized location; it does not replay uncertain payments or check-ins.
- HTTP 403 during session validation: account-access-denied state.
- Missing/unsupported roles: distinct access-denied guidance and a check-again action.
- Network/server/timeout failures: retry session verification, retaining credentials; never silently treat these as anonymous.
- Focus revalidates roles without unmounting a successfully verified page while the request is pending. Stale identity responses and stale 401s cannot overwrite a newer login.
- Logout is centralized, attempts existing refresh-session revocation, clears tokens/identity/read caches, and redirects to `/login` even if the server cannot be reached. Cross-tab token changes trigger re-verification or sign-out.
- Access-token expiry requires fresh sign-in; this change does not introduce automatic refresh-token rotation. Backend authorization remains mandatory. Server-side access-token revocation semantics on ordinary logout are unchanged.

## Validation

- `npm test` (session policy/store and existing feature tests)
- `npm run typecheck`
- `npm run build`
- `node scripts/role-session-browser.mjs`
- `node scripts/auth-account-browser.mjs`
- `node scripts/admin-browser-fixtures.mjs`
- `node scripts/membership-browser-fixtures.mjs`
- `node scripts/owner-scanner-browser.mjs`
- Backend: `python -m pytest tests/test_role_sessions.py tests/test_password_recovery.py -q`

Browser fixtures use isolated Chrome storage contexts because real cross-tab authentication propagation now intentionally signs out other tabs. They exercise real UI with intercepted API responses, not live business mutations. Deploy both backend and frontend together: the frontend requires the session endpoint. Existing authentication storage/security deployment limitations remain unchanged.