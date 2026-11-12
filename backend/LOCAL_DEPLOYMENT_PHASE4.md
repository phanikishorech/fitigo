# Phase 4 local deployment — completed after explicit user approval

Operation timestamp recorded by the local machine: November 11, 2026.
Migration completed at `2026-11-11T05:06:56.335218+00:00`.

## Scope and result

The user approved the proposed backup, restore verification, pending forward
migration, local port alignment and restart. This approval did not include
orphan repair, accidental-fixture deletion or legacy class linkage.

Verified target: local MySQL `localhost:3306`, database `fitigo`, server version
26.7.0. The server UUID and datadir were checked before backup and migration.
Revision changed from `acf58d9e1037` through `bdf69ea12480` to `cef70fb23591`.
The two new onboarding tables and class provenance columns/FK are present.
Existing slots are LEGACY and existing sessions remain unlinked: no guessed
associations were introduced.

## Backup and tested recovery

Private backup directory (outside the repository):
`C:/Users/ckishor/AppData/Local/FitiGo/backups/phase4-20261111-103407`

Its Windows ACL restricts access to the current user and SYSTEM. Contents include:
- `working.sql`: logical database backup, 284,697 bytes.
- `backup.json`: SHA-256, migration-source hashes and backup metadata.
- `before.json`, `restored.json`, `after.json`: table column inventories, row
  counts, canonical data hashes and DDL; no plaintext rows are included.
- `source-before.zip`: accumulated modified/untracked source plus local config.
  **Contains secrets in .env; do not share or commit.**
- Restore/rehearsal/migration logs and machine-readable results.
- Retained isolated restore datadirs, also sensitive. Their servers are stopped.
- One-off deployment/recovery-verification scripts with fixed target checks.

Dump SHA-256:
`ff2503fe7110c12d2fdd63e06b7c69fd547ebbd08cbad5ecb77fe262dfa8d12e`

The FitiGo backend was stopped before the dump. All 41 tables used InnoDB; no
views/triggers/routines/events were present. A single-transaction mysqldump
included routines/events/triggers options, with GTID mutation and tablespace
statements disabled. Temporary credential files were removed after use;
credentials were not placed on command lines or printed.

The dump was restored into a new loopback-only MySQL process with an owned
private datadir, distinct port/UUID and generated password. Every table's
columns/count/data hashes matched. DDL comparison normalized only redundant
`CHARACTER SET utf8mb4` wording before the identical `utf8mb4_unicode_ci`
collation; types/constraints were not ignored. Initial strict textual comparison
stopped on this wording difference; no working schema changes occurred until
the clarified comparison and migration rehearsal both passed.

The restored copy successfully migrated to `cef70fb23591`. Existing columns'
values in all 40 business tables remained identical. Before working migration,
the dump checksum, migration file hashes, source server identity/revision and
full source-data snapshot were rechecked. After migration and read-only smoke,
all original business-table hashes/counts still matched. Only the intended
schema additions and Alembic version changed.

Recovery plan: keep applications stopped, verify this dump's checksum, restore
to a new empty isolated schema/server and verify against `before.json`, then
review compatible code/config and approve any target switch or working restore.
Do not blindly import over the working schema: the dump contains DROP TABLE
statements and a pre-migration schema is incompatible with current class code.
No automatic rollback/downgrade or destructive restore was performed. This is a
database/source/config backup, not a backup of uploaded media or MySQL users/
global server configuration. No uploads or server accounts were modified.

## Runtime alignment and safety

- Only the verified FitiGo port-8000 Python launcher and children were stopped.
  The unrelated listener on 8000 was preserved.
- Backend started on `127.0.0.1:8001` using the existing local application config.
- Both Vite proxies now target `127.0.0.1:8001`. The existing frontend reloaded
  its config; direct and proxied health/API requests succeeded.
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/scripts/start-dev.ps1`
  now defaults to 8001, probes port availability and refuses busy ports instead
  of killing arbitrary processes. `-CheckOnly` performs a non-starting check.
- Script parser, free-port check and busy-port rejection were verified. The busy
  port's process survived, and the actual backend startup succeeded.
- Runtime logs:
  `C:/Users/ckishor/AppData/Local/FitiGo/runtime/backend-20261111-103730-41b8c7ca`
- User-facing frontend remains `http://localhost:5173`; API docs are at
  `http://127.0.0.1:8001/docs`.

No new plaintext credentials were written to source. Previous accumulated
uncommitted changes remain; no git reset/stash/commit/push was performed.

## Validation

Live HTTP, both direct backend and frontend proxy:
- Health and database health: 200.
- OpenAPI: 200, application title FitiGo.
- OTP options: 200 (no OTP sent).
- Bookings without credentials: expected 401.
- Deliberately nonexistent upload: expected 404, not proxy failure.

Authenticated in-process GET smoke used the current app and existing users,
short-lived access tokens kept only in memory, and DB-enforced READ ONLY
transactions plus a SQL read allowlist. There was no login/refresh insertion,
password mutation or HTTP credential disclosure. All 11 routes returned 200:
- Customer session, bookings, past/upcoming profile bookings.
- Owner session, slots, gym bookings, dashboard summary.
- Admin session, booking search, dashboard summary.

These route checks establish the former missing-column queries work; they do
not certify a user's actual password/browser session. No password was requested
or guessed. The remaining user acceptance step is normal browser sign-in and
bookings review. No real messaging, checkout, refund, QR issuance or staff
invitation was performed.

After port/script changes: frontend 385 tests passed, TypeScript check passed,
production build passed, git diff whitespace check passed. The backend
application code was unchanged in this operation; prior isolated Phase 4
regression result remains 626 passed. No plain pytest ran against working data.

## Still separate / not repaired

- Accidental fixture user 3862, its role mapping and DRAFT gym 1668 remain.
- The 11 orphan ledger entries/accounts and orphan staff assignment remain;
  cause/ownership still require evidence and separate remediation approval.
- Legacy schedule edits intentionally require reviewed provenance reconciliation.
- Existing warnings/deprecations, broad production acceptance and real provider
  testing are not claimed complete.
- Backup/restore datadirs are retained; no broad filesystem cleanup was run.

No additional user input was required for migration. Ask the user to sign in
normally and report any remaining UI error; do not request passwords in chat.