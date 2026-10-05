# Account creation and password management

## Customer

- Open the existing sign-in dialog and select **Create account**.
- Enter first/last name, email, optional phone, password and confirmation.
- Registration reuses `POST /api/v1/auth/register/customer`, then prompts password sign-in. It does not grant owner/admin roles or pretend email verification has occurred.
- **Forgot password?** is available in the dialog and on owner/staff sign-in. `/auth/forgot-password` is a public recovery page.
- Recovery links open `/auth/reset-password#token=...`. The UI immediately removes the fragment and retains the token only in component memory. Reloading after removal requires reopening the email link.

## Owners and staff

**Settings → Password → Change password**, available even with no assigned gym. Current password, new password and confirmation are required. Success clears the local session and returns to owner/staff login. The existing authentication dependency rejects old access tokens immediately, and refresh sessions are revoked.

## Backend endpoints

- `GET /api/v1/auth/password-reset/options`: reports whether SMTP/reset URL configuration is present, not whether a particular account exists or SMTP is reachable.
- `POST /api/v1/auth/forgot-password`: `{email}`; generic response for existing/unknown/inactive accounts. Delivery runs after the response in an application background task.
- `POST /api/v1/auth/reset-password`: `{token, new_password}`; 30-minute single-use tokens, only hashes persisted.
- `POST /api/v1/auth/change-password`: `{current_password, new_password}`; requires an active authenticated user. Applies to customers, owners and staff without changing roles.

Password updates invalidate all outstanding reset links and all existing access/refresh sessions. A per-user token version defaults to zero, preserving existing sessions until a password change. Refresh tokens have unique IDs to support multiple logins/rotation in the same second. Invalid supplied credentials no longer silently become an anonymous/dev-fallback identity.

## Email setup (required for real reset emails)

Set server environment variables in the existing root or backend `.env` (never in frontend `VITE_` variables):

```dotenv
SMTP_HOST=smtp.your-provider.example
SMTP_PORT=587
SMTP_SECURITY=starttls
SMTP_USERNAME=your-smtp-username
SMTP_PASSWORD=your-provider-secret
SMTP_FROM=no-reply@your-verified-domain.example
PASSWORD_RESET_FRONTEND_URL=http://localhost:5173/auth/reset-password
```

Use actual provider settings; the values above are placeholders, not credentials. Port 465 with `SMTP_SECURITY=ssl` is also supported. TLS certificate verification remains enabled. Outside development the reset URL must use HTTPS. It is configured by the server, never constructed from an untrusted Host header. Restart the backend after changing settings.

If SMTP is not configured, the frontend shows an unavailable message and sends no reset request. SMTP delivery failures do not leak account existence or raw diagnostics; they log a generic warning and roll back that token. No development shortcut returns recovery tokens or changes a forgotten password without verification.

## Migration / deployment

Run `python -m alembic upgrade head` from the backend directory before deploying code. Revision `5da03e4f6b82` adds `users.token_version`, `password_reset_tokens`, and `auth_rate_limits`. Existing password hashes and roles are unchanged. Restart all backend workers on deployment.

## Operational limits

- Forgotten-password requests: 3 per email and 20 per client IP per 15 minutes. Reset attempts: 20 per IP per 15 minutes. Current-password changes: 5 attempts per user per 15 minutes. Counters persist across workers.
- Configure trusted reverse proxies correctly for the client IP; do not trust arbitrary forwarded headers. An ingress/WAF rate limit remains recommended for registration/login and volumetric abuse.
- Background email delivery is not a durable queue. A process restart can drop delivery; users can request another link. Production deployment should add monitored durable email jobs and password-change notifications.
- Periodically prune expired reset records and rate-limit windows after the retention period. No tokens/passwords should appear in logs or analytics.
- Existing OTP email/SMS delivery remains unconfigured and unchanged by this feature; do not treat the OTP demo implementation as production-ready.
- Browser tests intercept API requests; SMTP tests use an isolated mail transport. Real inbox delivery requires provider configuration and an end-to-end deployment test.

## Validation

`python -m pytest tests/test_password_recovery.py -q`

Frontend: `npm test`, `npm run typecheck`, `npm run build`, and `node scripts/auth-account-browser.mjs` (isolated Chrome debugging session on port 9231).