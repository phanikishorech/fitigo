# Revenue-sharing editor — local testing activation

## Authorized scope and result

User requested: “please implement the changes and activate for testing.”
Activated the implemented configuration editor on the existing local development
application, frontend port 5173 and backend loopback port 8000. Payment configuration
remains test mode. No external production deployment or provider calls were made.

Open **Admin → Runtime settings → Revenue-sharing agreements**, select
**Sandbox / test**, then expand **Schedule a new version / adjust revenue sharing**.
The stored proposal contains booking 85/15, no-show 70/30, Single-Gym 85/15,
settlement terms and INR 500 minimum. Multi-Gym rates/caps remain not configured.

The editor is enabled, but **no agreement was automatically scheduled or made
effective**. Supply a future IST start, reference and reason, review, then save a
test version. Test saving uses the real configuration tables and retains audit
history. Do not select Production/live for sandbox experiments.

This is configuration editing only: commission postings, owner payouts and statutory
financial reporting remain disabled. No customer balances, bookings, payments,
membership entitlements or historical financial transactions were changed.

## Backup and migration

- Backup: `C:\Users\ckishor\AppData\Local\FitiGo\releases\agreements-20261114-143532\fitigo-before-agreements.sql`
- Size: 124145 bytes. Dump completion marker and SHA-256 checked; verification
  metadata is in `backup-verification.json` in the same private directory.
- Directory ACL restricted to the Windows user and SYSTEM. Temporary database
  credential file removed. No secrets printed or passed in process arguments.
- Stopped only verified FitiGo backend launcher tree PID 36020. MySQL and frontend
  were not stopped.
- Applied migration `c35d6fa89157` → `d46e70ba9268`.
- Counts and deterministic row-content hashes verified unchanged for **52 existing
  data tables**, excluding intentional Alembic version change.
- Added two standard proposal scopes (test/live) and zero agreement versions.
- Restarted using `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\scripts\start-dev.ps1`.
- Runtime logs: `C:\Users\ckishor\AppData\Local\FitiGo\runtime\backend-20261114-143551-1c7c4f39`.
- No restore rehearsal performed. A backup restore after subsequent activity would
  lose that activity and requires explicit approval; prefer forward fixes. Migration
  downgrade refuses removal once agreement history exists.

## Actual verification

- Disposable MySQL agreement tests: **32 passed** in 111.56 seconds.
  `C:\Users\ckishor\AppData\Local\Temp\fitigo-isolated-609cdedaa046abd7-3bi3_5jl\pytest.log`
- Frontend unit tests: **464 passed**; TypeScript passed; production build passed.
- Mocked browser before/after migration: proposal/edit/percentage validation/review/
  save/history/gym scope/missing-schema guard, 360/768/1440px, passed.
- Actual backend health, DB health and frontend API proxy passed.
- Actual authenticated admin configuration GETs in test/live scopes returned
  `available=true`, correct stored proposals, version 0, no effective agreement,
  `posting_enabled=false`, `statutory_reporting_enabled=false`.
- Anonymous GET returned 401; non-admin GET returned 403.
- Local authenticated smoke used short-lived in-memory tokens and GETs only. No
  passwords/session versions were modified; no real agreement was saved for testing.
- General full backend suite was not rerun for this activation; the previous
  implementation full regression checkpoint was 946 passing.

Frontend evidence:
`C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\agreement-activation-unit-results.txt`
`C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\agreement-activation-build-results.txt`
`C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\agreement-activation-browser-results.txt`

Private release directory also contains `data-before.json`, `data-after.json`,
`migration-verification.json`, `migration.log`, and `api-smoke.json`.

This report supersedes only the not-locally-activated statement in
`C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\ADMIN_REVENUE_SHARING_CONFIGURATION.md`.
All documented configuration-only limitations remain. No application source changes
were needed for activation; changes in this step are migration/deployment and release
documentation/evidence. No commit/tag or external deployment was performed.