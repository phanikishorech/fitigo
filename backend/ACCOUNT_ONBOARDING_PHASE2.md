# Phase 2 — Account onboarding, OTP and recovery

## Status and safety

Implemented against the existing FastAPI/SQLAlchemy/MySQL and React/TypeScript architecture. No SDK/dependency additions. Phase 1 enforcement remains in place. No working/production database changes, credential rotations, real messages/payments, deployments, commits, or intentional server restarts were performed.

The prior audit was accessible at `C:/Users/ckishor/AppData/Local/Temp/fitigo-application-audit/AUDIT.md`. Existing user changes were inspected before editing. Among files already changed before this phase, only these received targeted additions: `.env.example`, backend configuration, test isolation configuration, and the frontend shared error client. The six Home membership banner files and the other Phase 1 changes were preserved.

**Not yet operationally accepted:** local SMTP is unconfigured. Twilio credentials/sender configuration are not supplied. Real email/SMS delivery remains unverified. The new migration has NOT been applied to the working database. The Phase 1 strong-JWT startup requirement still applies; no insecure fallback was reintroduced.

## Staff workflow

1. An authenticated owner submits the existing `POST /api/v1/gym-owner/gyms/{gym_id}/staff/invite` request. Gym ownership is checked before any invitation work.
2. A new account is persisted as `PENDING_INVITATION` only if the email provider accepts the invitation and the transaction commits. It has no usable known password, no staff role and no gym assignment yet. Existing active accounts remain unchanged pending acceptance. Inactive/suspended accounts cannot be invited into activation.
3. A cryptographically random single-use capability is emailed; only SHA-256 of the high-entropy token is stored. It is scoped to the saved user/email, owner and gym with configurable expiry. The email never contains a permanent password.
4. `/auth/accept-invitation#token=...` captures the token into component memory and removes the fragment from browser history. Tokens are submitted only in POST bodies, never query strings or local/session storage. Reopen the email after a page reload.
5. New staff choose their own password. Existing account holders must confirm their current password; supplying `new_password` cannot reset an existing account. Existing users who lack a usable password use normal email recovery first.
6. Acceptance rechecks token validity, owner status/role, current gym ownership and unchanged recipient email under row locks. Only the stored gym assignment and GYM_STAFF role are granted. Client-supplied role/gym/user fields are rejected. The token is consumed atomically. New-account activation follows the existing token-version/session-revocation policy.
7. The user signs in normally. Existing roles/other gym assignments are preserved; pending invitations for other gyms must be accepted separately. No access is granted just by receiving email or logging in with OTP.

### Owner management

- Existing invite POST is also the resend operation for the same email/gym. It replaces the token only after provider acceptance; the previous token then stops working. Cooldowns/limits apply even to failed attempts. If a resend fails, a previously valid link remains valid until its original expiry/revocation.
- `GET /api/v1/gym-owner/gyms/{gym_id}/staff/invitations`: scoped pending/expired invitations, no tokens/passwords.
- `DELETE /api/v1/gym-owner/gyms/{gym_id}/staff/invitations/{invitation_id}`: revoke a pending invitation. Accepted invitations must be handled with existing staff-removal functionality.
- Owner Staff page offers **Manage invitations**, resend and revoke. Invitation errors remain actionable; no success toast on failure.
- Public `POST /api/v1/auth/staff-invitations/inspect` returns gym name, expiry and whether current-password confirmation is needed, only for a valid capability.
- Public `POST /api/v1/auth/staff-invitations/accept` consumes the capability. Neither endpoint returns a session token or invitation credential.

**Compatibility:** invitation responses no longer contain `temp_password`, `staff_user_id` or an immediately usable `assignment_id`. They return invitation ID, expiry and `delivery_status=PROVIDER_ACCEPTED`. Integrators must stop assuming immediate assignment. Both current and legacy owner screens no longer expose generated passwords. Existing accepted assignments are not migrated or revoked.

## OTP workflow

The existing email/mobile send and verify routes remain in place. Both are passwordless LOGIN flows, not an arbitrary-purpose verification API.

- Six-digit codes use `secrets.randbelow`; challenges are shared database records rather than per-process dictionaries.
- Codes use domain-separated HMAC-SHA256 with a random nonce and the configured server signing secret; a database dump alone cannot enumerate codes. Signing-key rotation invalidates outstanding OTPs.
- Challenges bind channel, normalized destination, purpose, existing user ID and token version. Email/phone change, password change, inactive/pending account, expiry, consumption or exhausted attempts prevents login. A challenge issued before another process creates that account cannot log into the new account.
- Valid new-user OTP sign-in retains the existing customer-registration behavior. Browser roles are never accepted. Mobile-only accounts retain a non-deliverable internal email placeholder; response schemas permit this persisted string, while real email inputs still use email validation. Session responses now preserve actual email/phone verification flags.
- Attempts and consumption are persisted transactionally. Failed guesses survive HTTP errors; a successful code cannot be reused. Resend replaces the previous code on confirmed submission. Wrong destinations/purposes cannot reuse a code.
- `GET /api/v1/auth/otp/options` reports configured channel availability, expiry and cooldown (configuration readiness, not a delivery guarantee).
- Send endpoints return success only after transport acceptance. Configuration/provider errors return safe 503 codes. The UI does not advance to code entry on failure and uses the returned resend cooldown.

## Password recovery

- Email is the existing supported identifier. Public reset URL comes from explicit public frontend configuration, not the request Host header or a hardcoded localhost default.
- Recovery waits synchronously for SMTP acceptance; the old background-success-before-delivery behavior was removed.
- To avoid revealing application account existence through acceptance/failure responses, the same conditional recovery template is submitted for known, unknown and inactive addresses. Only active accounts receive a stored, usable reset token. Unknown/inactive links are nonfunctional and never create accounts. This has deliberate email-cost/abuse tradeoffs; limits and provider monitoring are required.
- Provider acceptance and rejection responses do not vary based on registration status. Expiry is configurable. Only hashed, single-use reset tokens are stored.
- Successful reset increments token_version and revokes refresh sessions and outstanding reset tokens using the existing account design. Current-password changes retain the same policy. Pending staff accounts cannot bypass invitation acceptance via recovery.
- The existing recovery UI now says the provider accepted the request, not that inbox delivery is guaranteed; it displays configured expiry and explicit delivery failure.

## Delivery architecture and configuration

SMTP uses Python's existing standard-library transport, certificate-verified STARTTLS or implicit TLS, and checks refused-recipient results. SMS uses the already installed `httpx` client against Twilio's fixed HTTPS Messages endpoint, with bounded timeout, no redirects, and validation of HTTP 201 plus accepted/queued/sent state. No console, fixed-code, or production test transport exists. Tests inject transport fakes only in test fixtures.

Provider acceptance is not inbox/handset delivery. Bounces/carrier rejections may arrive later; this phase does not add delivery-receipt webhooks or a durable outbox. A timeout/lost acknowledgement is reported as unconfirmed, never successful. A provider may already have accepted a message when a later commit/connection fails; the received credential may be unusable. Retry after the cooldown and use the newest valid link/code. No automatic retry loop is added.

Configure server environment variables using the existing process/root/backend `.env` conventions. Process environment overrides file configuration. No secrets belong in frontend `VITE_` variables.

| Variable | Meaning/default |
| --- | --- |
| `EMAIL_PROVIDER` | `smtp` or `disabled`; example file uses disabled until configured |
| `SMTP_HOST`, `SMTP_PORT` | Actual provider host and port; default port 587 |
| `SMTP_SECURITY` | `starttls` or `ssl`; no plaintext transport |
| `SMTP_USERNAME`, `SMTP_PASSWORD` | Provider credentials; password redacted with SecretStr |
| `SMTP_FROM` | Approved sender identity |
| `PUBLIC_FRONTEND_URL` | Actual public origin/base URL; required for invitations and default recovery URL |
| `PASSWORD_RESET_FRONTEND_URL` | Optional legacy explicit reset-page override; empty by default |
| `PASSWORD_RESET_EXPIRY_MINUTES` | 30; range 5–120 |
| `INVITATION_EXPIRY_HOURS` | 48; range 1–168 |
| `INVITATION_RESEND_SECONDS` | 60; range 30–3600 |
| `OTP_EXPIRY_SECONDS` | 600; range 60–900 |
| `OTP_RESEND_SECONDS` | 60; range 30–600 |
| `OTP_MAX_ATTEMPTS` | 5; range 1–10 |
| `OTP_SEND_LIMIT` | 5 requests per destination/channel per 15 minutes; range 1–10 |
| `SMS_PROVIDER` | `disabled` by default; set `twilio` to enable |
| `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN` | Account credentials; auth token is redacted |
| `TWILIO_FROM_NUMBER` | Approved SMS-capable sender in international format |

Public links require HTTPS outside development; local development HTTP requires a loopback host. Embedded user credentials, query strings, fragments, whitespace and backslashes are rejected in configured links. Provider readiness is validated before submission and is exposed as unavailable, not simulated success. Disabled channels do not prevent the rest of the API from starting.

Additional persistent limits: OTP sending 20/IP/15 minutes; verification 40/IP and 15/destination/15 minutes; invitation creation/resend 20/owner/hour and 5/destination/hour; acceptance 20/IP and 5/token/15 minutes; inspection 30/IP/15 minutes. Recovery retains 20/IP and 3/email/15 minutes and 20 reset attempts/IP/15 minutes. Trusted proxy configuration remains required; arbitrary forwarded IP headers are not trusted by application code. These are not a replacement for ingress/provider spend controls.

MySQL rate-limit row creation now uses an atomic upsert before locking, fixing an observed concurrent-first-request gap-lock deadlock without weakening limits.

## Migration — not applied to working data

Revision `bdf69ea12480`, parent `acf58d9e1037`, adds only `account_otps` and `staff_invitations`. Existing users, assignments, wallet/payment records and password hashes are not rewritten. Both tables are imported through existing auth/staff models. Upgrade tolerates a table already created by partially committed MySQL DDL.

Downgrade checks BOTH tables for records before any drop. If either contains records it refuses and requires explicit archival; no invitation or security history is silently deleted. Empty-schema upgrade/downgrade/upgrade passed on disposable MySQL, and SQLite tests verified preservation and refusal with nonempty tables. The older wallet downgrade defect remains outside this phase.

Deploy code only after an authorized migration/backup plan. The working database was not changed; these endpoints need the new schema. Do not run legacy full-suite tests on the working database.

## Tests actually executed

- Baseline account tests before changes: **29 passed**.
- Final targeted account/security/profile/staff/safe-error selection: **187 passed**.
- New MySQL concurrent invitation acceptance and OTP verification tests: **2 passed**, repeated three times after fixing the discovered rate-limit race. These use separate disposable schemas and mock mail, not live messages.
- Final full backend run on a freshly migrated disposable MySQL database, with opt-in MySQL suites: **550 passed, 23 failed, 2 setup errors** (575 cases). No new nonpassing cases compared with Phase 1. The old staff onboarding test now exercises actual invitation acceptance/login and passes; its stale same-day booking fixture was corrected to a future day.
- Remaining full-suite failures are the prior time-sensitive/obsolete membership and wallet expectations plus in-process migration logging interference. The two setup errors remain the pre-existing wallet downgrade index/FK-order issue. The full repository suite is NOT certified green.
- Frontend: **379 tests passed**, TypeScript check passed, production build passed.
- Mocked browser checks passed: new/existing/expired staff invitation, fragment cleanup, no role/gym acceptance payload, responsive layout, OTP/recovery failure handling and resend cooldown; existing account/recovery UI; existing owner staff identity/removal UI.
- Provider contract tests cover TLS, refused SMTP recipients, Twilio acceptance/rejection and safe error responses. No real provider credentials, inboxes or handsets were used.

Private logs: `C:/Users/ckishor/AppData/Local/Temp/fitigo-account-phase2`. Raw legacy test output/XML can contain disposable fixture tokens; do not publish it.

## Main affected files

- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend/app/services/account_delivery.py`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend/app/services/staff_invitation_service.py`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend/app/services/staff_service.py`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend/app/services/otp_service.py`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend/app/services/password_service.py`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend/app/core/config.py`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend/app/core/errors.py`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend/app/models/auth.py`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend/app/models/staff.py`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend/app/routers/auth.py`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend/app/routers/gym_owner.py`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend/app/schemas/staff.py`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend/app/schemas/otp_auth.py`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend/app/schemas/user.py`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend/alembic/versions/bdf69ea12480_account_onboarding.py`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/frontend/src/pages/auth/StaffInvitationPage.tsx`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/frontend/src/owner/StaffInvitations.tsx`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/frontend/src/owner/Operations.tsx`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/frontend/src/screens/GymOwner/api.ts`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/frontend/src/screens/GymOwner/GymOwnerGymPage.tsx`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/frontend/src/services/authService.ts`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/frontend/src/services/client.ts`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/frontend/src/components/AuthModal/AuthModal.tsx`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/frontend/src/components/AuthModal/OtpVerifyPanel.tsx`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/frontend/src/components/AuthModal/PasswordRecovery.tsx`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/frontend/src/customerRoutes.ts`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/frontend/src/session/policy.ts`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/frontend/src/pages/CustomerApp.tsx`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/.env.example`

Tests added under `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend/tests`: account_onboarding, account_delivery, account_onboarding_migration and account_onboarding_mysql test modules. Existing recovery/role/staff tests were updated for the intended secure contract, and conftest explicitly isolates delivery settings from real credentials. Browser harness: `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/frontend/scripts/account-onboarding-browser.mjs`; recovery harness copy was updated for provider-acceptance wording.

## Remaining manual setup and acceptance

1. Keep the Phase 1 strong JWT configuration shared across workers. Provision separate environment-specific SMTP/SMS credentials privately; do not reuse test credentials or print them.
2. Configure an approved SMTP sender/domain and the provider-required DNS records and credentials; allow outbound TLS connectivity. Set the actual public frontend URL and ensure the application serves `/auth/accept-invitation` and `/auth/reset-password` directly over HTTPS without stripping fragments before the client loads.
3. If mobile OTP is required, configure a Twilio SMS-capable sender and credentials, enable the intended destination countries and complete any provider/country-specific sender/template registration. Confirm trial-account recipient restrictions and spending limits in the provider dashboard. Do not enable a generic console/test sender in production.
4. With separate authorization, back up and apply migration `bdf69ea12480` to the intended environment, then deploy/restart all instances with the same configuration. No working-database migration was performed here.
5. With explicit permission to send real messages, test: owner invite -> received email -> acceptance -> password login -> assigned gym only; resend/expired/duplicate invitation; email OTP and SMS OTP -> received code -> one successful login -> replay rejected; forgot password -> received link -> reset -> old access/refresh sessions rejected. Repeat through different workers.
6. Confirm delivery failure/error UX by safely disabling a channel in staging and using controlled provider rejection tests. Verify no token, code, password, phone/email body, or provider credential appears in access logs, proxy body logging, error trackers or analytics. Disable session recording on credential entry pages.
7. Monitor provider bounces/carrier failures and application 429/503 rates. Define retention/archival for used/expired invitations, OTPs and rate-limit records without deleting required audit data. No cleanup job or destructive reconciliation is included.

This phase stops at implementation and isolated validation. Real delivery, deployment acceptance, other audit phases and an overall production-security assessment remain outstanding.