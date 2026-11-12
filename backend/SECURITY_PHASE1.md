# Phase 1 — Authentication and authorization hardening

## Scope and operational status

This phase changes authentication/configuration enforcement, removes anonymous identity substitution, and adds boundary regressions. It does not certify the application production-secure. No working/production database records were changed, no credentials were rotated, no real messages/payments were sent, and nothing was committed, deployed, or deliberately restarted.

The six pre-existing Home membership banner files were preserved byte-for-byte. The audit report at `C:/Users/ckishor/AppData/Local/Temp/fitigo-application-audit/AUDIT.md` was accessible and reviewed.

**Manual local action required:** the existing local `.env` still contains an insecure signing configuration. It was deliberately not edited. API startup/reload now rejects it. A previously running worker may retain old imported code until replaced; a listening port is not evidence that the new configuration has been deployed. Keep existing development servers private. Do not restore an insecure default to recover startup.

## Signing requirements

- `JWT_SECRET` has no hardcoded/default value and is represented as `SecretStr`, redacting settings representations.
- Startup validates the configuration both in `create_app()` and lifespan. Turning lifespan off does not bypass validation.
- The policy applies to every environment, so an environment typo or copied development configuration cannot bypass it.
- Supported signing algorithms: HS256, HS384, HS512. Required key-string lengths: respectively 32, 48, 64 UTF-8 bytes. Blank/padded values, common placeholder patterns and trivially repetitive values are rejected.
- These checks are a minimum policy, not a measurement of entropy. Generate an independent random value, for example with Python `secrets.token_urlsafe(64)`, and provision it privately. Never print it in CI logs, tickets, chat, browser configuration, or a `VITE_` variable. Never commit it.
- Generate one stable value per environment, NOT one per worker/startup. Every instance must use the same secret-manager version, algorithm, database/session state and compatible code. Development, staging, tests and production must not share signing material.
- Settings precedence remains process environment over backend `.env` over root `.env`. Resolve conflicting settings during deployment. No secret-discovery or distribution service was added.
- Automated pytest collection injects a new test-only random key before importing the API, overriding any inherited real key. The application has no runtime test-key fallback.

Unchanged compliant keys preserve existing valid access/refresh sessions and password hashes. JWT shape remains compatible: `sub`, `type`, `exp` and optional `version`; missing version still means zero. No issuer/audience rollout or signing-key ring was introduced. Access/refresh validation now requires an expiry and valid positive signed-BIGINT user subject, rejects invalid claim types and unknown token types, and converts malformed claims to 401 instead of an integer-conversion error. Existing per-user version, active-account, stored refresh-token and database-role checks remain in force.

## Affected endpoints and compatibility

| Endpoint family | Enforcement / behavior |
| --- | --- |
| `/api/v1/auth/login`, `/refresh`, `/session`, all JWT-protected routes | Shared strict JWT parser; actual roles loaded from DB, never trusted from JWT/browser role claims. Valid login and refresh still work. |
| `/api/v1/profile`, `/profile/membership`, `/profile/activity`, `/profile/favorites`, `/profile/membership/pass` | Required authenticated identity; no demo fallback. Existing customer-only subroutes remain customer-only. |
| `/api/v1/cart/*` | Required authentication at router and handler boundary, before checkout business checks. Existing cart ownership predicates retained. Dead demo lookup removed. |
| `/api/v1/wallet/balance`, `/wallet/transactions` | Required authentication; only current user's balance/ledger. Dead demo lookup removed. No spending/top-up policy changed. |
| `/api/v1/gyms/{gym_id}/booking-options`, `/validate-booking`, public discovery/details with optional identity | Anonymous browsing remains available with no member identity/discount. Supplied malformed/invalid authentication returns 401 rather than silently becoming anonymous. |
| `/api/v1/gyms/{gym_id}/access-bookings` | Requires CUSTOMER authentication; missing credentials 401, wrong role 403. Subject comes from authenticated account. |
| `/api/v1/checkins/validate` | Existing assigned-staff/own-gym-owner policy retained. Out-of-scope scanner request now returns HTTP 403 with `detail.code=GYM_NOT_ALLOWED`, instead of HTTP 200. Customer QR business failures remain their existing structured rejections. |

The scanner client explicitly maps only the known 403/GYM_NOT_ALLOWED result to its rejection display. It does not turn 401, other 403 responses, network errors or 5xx into success. Integrators using the scanner endpoint must handle the changed HTTP status.

Role denials use 403. Ownership-filtered object lookups deliberately retain 404 to avoid disclosing another user's booking, gym, plan, order or membership. This is not a permission bypass. Disabled users retain the existing 403 behavior; deleted users/revoked sessions receive 401.

## Authorization review

- Customers: booking detail/cancel/reschedule/visitor assignment/QR queries bind both record ID and authenticated user ID; membership listing/cancel/pause, profile visits/reviews, cart entries, notifications and payment history are scoped to the authenticated user.
- Owners: gym CRUD, images, facilities, hours, slots, membership plan mutations, staff assignments, booking actions, dashboard and analytics use owner-scoped queries. A supplied gym ID narrows scope; it never grants access.
- Staff: assigned gym IDs are resolved server-side before booking listing, attendance and QR validation. Owner-only APIs reject staff roles. Owners can scan only their own gyms unless they also have an applicable staff assignment.
- Admin: admin and platform-catalog administration require ADMIN/SUPER_ADMIN backend dependencies. Customer/owner/staff tokens with forged role claims remain denied. Registration cannot select an admin role.
- Payments: checkout ownership is checked before read/verify/refresh/cancel. Booking sources and platform orders belong to the purchasing customer; plan/gym matching, accepted quotes and prices are server-validated. Browser-supplied booking payment amounts/identity fields are rejected. Wallet top-up amount is an explicitly validated requested recharge amount, not a trusted entitlement.
- Webhooks intentionally do not use user JWTs; existing provider signature/amount/order verification remains unchanged and covered by provider regression tests.
- QR credentials are existing opaque tokens, not session JWTs. Their purchase/membership eligibility and single-use checks were not weakened.

No new membership-directory endpoints or permission features were added. The review and tests cover these boundaries but are not an exhaustive penetration test or concurrency certification.

## Development tooling

`C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/scripts/start-dev.ps1` now binds to loopback instead of all interfaces. This affects future launches only; it does not reconfigure existing processes.

Both entry points in `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend/app/scripts/seed_dev.py` require parsed `settings.environment == 'development'`, explicit process `FITIGO_ALLOW_DEV_SEED=1`, a loopback database host and a private process `DEV_SEED_PASSWORD` of at least 12 characters. No default password remains. The seeder was NOT run. It is still a state-changing developer tool, not a safe reconciliation tool; never aim it at existing working data.

## Files changed by this phase

Configuration / authentication:
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/.env.example`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend/app/core/config.py`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend/app/core/security.py`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend/app/core/dependencies.py`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend/app/main.py`

Routes / tools:
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend/app/routers/profile.py`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend/app/routers/gyms_public.py`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend/app/routers/cart.py`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend/app/routers/wallet.py`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend/app/routers/checkins.py`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend/app/scripts/seed_dev.py`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/scripts/start-dev.ps1`

Frontend authorization-error compatibility:
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/frontend/src/services/client.ts`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/frontend/src/owner/services.ts`

Tests:
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend/tests/conftest.py`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend/tests/test_security_configuration.py`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend/tests/test_security_boundaries.py`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend/tests/test_security_payment_boundaries.py`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend/tests/test_booking_access_qr.py`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/frontend/scripts/securityScanner.test.mjs`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/frontend/scripts/owner-scanner-browser.mjs`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/frontend/scripts/role-session-browser.mjs`

Documentation:
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/README.md`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend/SECURITY_PHASE1.md`

## Validation actually performed

- Pre-change isolated security-related baseline: 49 passed.
- Final targeted backend security/auth/QR/profile/staff/platform/provider/wallet/analytics/safe-error regression selection: **283 passed**.
- Full suite on a freshly migrated disposable local MySQL schema, including opt-in MySQL fixtures: **513 passed, 24 failed, 2 setup errors** (539 cases). The disposable schema was removed. No new failing case names versus the prior audit's 26 nonpassing cases.
- Frontend: **377 passed**, TypeScript application check passed, production build passed.
- Mocked browser suites: account/recovery UI passed; scanner passed including new HTTP 403 behavior; Home/membership entry passed.
- Role browser: after correcting the stale dashboard fixture and honoring the isolated origin, six role/login/guard/logout/continuation sections passed. The complete script remains blocked by an older booking test expecting two time inputs; the current booking UI uses hour/minute selects and visitor fields. This is not reported as a fully passing browser suite. No navigation assertions were deleted or weakened.
- Existing migrations were inspected; no migration/model changes were needed. Fresh upgrade to head passed. Existing password-recovery migration upgrade/downgrade test passed in its disposable fixture. The known wallet downgrade foreign-key/index ordering failure still blocks two MySQL QR setup cases and was deliberately not fixed in this security phase.
- The 24 failures retain the baseline categories: nine time-sensitive booking fixtures, six obsolete membership-purchase fixtures, one legacy wallet status expectation, eight in-process Alembic logging/capture failures. Safe-error tests pass in the isolated targeted run. This phase does not claim the full backend suite is green.

Private run artifacts: `C:/Users/ckishor/AppData/Local/Temp/fitigo-security-phase1`. Do not publish raw failure/XML logs: older assertions can include disposable test credentials. Browser tests intercept APIs and do not prove real SMTP/payment/device acceptance.

## Controlled signing-key rotation / deployment — manual, NOT executed

1. Obtain approval, identify every API worker/host/background token issuer and ingress, and schedule a maintenance window. Back up configuration references and the database under the normal backup policy; never export raw secrets into this repository.
2. If the existing production key is compliant and uncompromised, deploy this hardening with the **same** key/algorithm to preserve sessions. Do not rotate solely because code was updated. The known local placeholder is not compliant and cannot be retained.
3. If a default/compromised key must be replaced, generate one independent random value in an approved secret manager and assign a versioned reference. Provision that exact reference and algorithm on all instances. Use an independent key for staging/development. Do not auto-generate per instance.
4. Drain ingress and stop all old workers/token issuers before switching traffic. This application has no dual-key verification window; mixed old/new workers cause inconsistent authentication. Do not accept a compromised key as a temporary fallback.
5. With separate explicit authorization for the production action, invalidate sessions using the existing schema: increment each user's token_version and mark unrevoked refresh_tokens revoked_at in a controlled transaction; if incident scope warrants, invalidate outstanding password-reset tokens too. Verify affected counts/backups first. Rotation alone also makes old JWT signatures fail; persisted revocation prevents old sessions being resurrected by an accidental key rollback. No such transaction was run in this phase.
6. Deploy/restart every instance with the same code/key version/algorithm and appropriate production environment. Run the configuration check privately (`settings.validate_security()`), recording only pass/fail and secret-manager version identifiers, never key values or raw environment dumps. No Phase 1 database migration is required.
7. Before restoring traffic, verify startup/health on every instance, then use approved staging/test accounts to verify login on one instance and authenticated request/refresh through every other instance. Verify a pre-rotation JWT is rejected and wrong-role/cross-owner requests are denied. Do not log tokens. This multi-instance deployment acceptance remains manual; isolated tests only prove equal settings interoperate and unequal keys fail.
8. Restore traffic and monitor sanitized 401/403/error rates. Tell users to sign in again after a rotation. If rollback is needed, retain the new secure key and compatible code; never restore the compromised/default key or decrement token versions. Pause traffic if safe compatibility cannot be established.

Remaining release work includes all non-security audit phases, real external-service acceptance, deployment configuration/credential review, rate-limit and infrastructure review, and the known full-suite failures. This phase alone is not production-security approval.