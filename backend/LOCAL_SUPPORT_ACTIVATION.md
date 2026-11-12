# Local support activation — backed up and verified

## Scope

The user approved the proposed backed-up local activation of support. This
operation does not define new staff permissions or gym archival rules. Financial
features and external messaging remain disabled. No existing records/photos were
deleted, no support fixtures were inserted into working data, and no real messages,
payments or refunds were executed.

## Target and result

- Target verified before operations: local MySQL `localhost:3306`, database `fitigo`,
  version 26.7.0, same expected server UUID as the prior verified deployments.
- Revision advanced from `ef192bd45713` to **`f02a3ce56824`**.
- Migration completion timestamp: `2026-11-11T17:38:42.008570+00:00`.
- Both support tables, required unique indexes, foreign keys and secondary indexes
  were checked. Tables remained empty after verification.
- `SUPPORT_WORKFLOWS_ENABLED=true` was the only application configuration change.
  Operational audit/in-app notifications stay enabled; notification email stays off.
  No signing/provider credentials were changed or printed.
- FitiGo backend restarted on 8001; frontend remains on 5173. Unrelated port-8000
  application and existing MySQL service were not stopped.

The owned FitiGo process-tree termination initially reported access denied for
the top-level launcher after its children exited. Before proceeding, process
enumeration confirmed all four owned PIDs absent and no port-8001 listener. No
other process was killed to work around that result.

## Backup and restore rehearsal

Private directory outside source control:
`C:/Users/ckishor/AppData/Local/FitiGo/backups/support-activation-20261111-230713`

Directory permissions restrict access to the current Windows user and SYSTEM.
It contains database dump, source/configuration snapshot, pre-activation .env,
data/DDL hashes, media archive, isolated restore artifacts and machine-readable
verification results. **Configuration snapshots contain secrets: do not share or
commit these artifacts.**

- **47 tables** backed up via single-transaction mysqldump. All were InnoDB;
  no views/triggers/routines/events were present.
- Database dump: 307,360 bytes; SHA-256:
  `2b24d5e831e87622be49dd2be272e95a2d33d53ab1b8042080c035ea6368e342`
- **13 media files, 1,972,717 bytes** archived and restored separately; every
  restored file matched its source fingerprint.
- Media archive SHA-256:
  `7fb3c6cecc62ae0d5cf55936890ec32a412baef32fc3ea9873595119e3f2617f`
- Database restored into a fresh loopback-only MySQL process/datadir with generated
  credentials, a distinct UUID/port and matching server version. All 47 table
  inventories/data hashes/counts and normalized DDL matched before rehearsal.
- Rehearsal upgraded that restored copy successfully. Source migration hashes,
  database identity, original revision, backup checksum and media hashes were
  rechecked before migrating the working target.
- After working migration and read-only smoke, all **46 pre-existing business
  tables** still matched the pre-maintenance snapshot, including schema. All media
  remained identical. Only Alembic version and additive support schema changed.
- Original source/configuration preserved in private backup; accumulated Git
  modifications retained. No reset/stash/commit/push was run.

Restore/test servers stopped; private datadirs retained for review. No broad
filesystem cleanup was executed. Media directory ACL/link review was repeated.

## Validation

Fresh pre-deployment isolated support/API/MySQL concurrency/migration/safeguard
selection: **25 passed**, zero failures/errors/skips.
Artifacts: `C:/Users/ckishor/AppData/Local/Temp/fitigo-isolated-4c6bb50302d92a29-0xm9zjmt`.

Frontend rerun: **402 tests passed**, TypeScript and production build passed.
Prior implementation full regression remains **694 passed**, with **32 final
targeted checks** documented in SUPPORT_READINESS_PHASE.md; application code was
not changed during this deployment.

After activation:
- **27 authenticated GET checks returned 200**, covering support lists, filtered
  lists, admin readiness, existing notification/photo-status/account/booking/report
  endpoints. Database-enforced READ ONLY transactions and a SQL allowlist prevented
  test mutations. Ephemeral short-lived tokens remained in memory.
- Customer and owner access to the admin support queue returned expected **403**.
- Unauthenticated support requests returned **401**, directly and via frontend.
- Direct/proxied health, DB health and support-capability endpoints returned 200.
- Readiness CLI returned exit **0**: schema/support checks pass. It still correctly
  reports email/SMS disabled and scheduling/external acceptance as manual checks;
  `production_certified` remains false.
- No working tickets/messages were created to demonstrate success. Create/reply/
  resolution behavior is covered by isolated API and mocked browser tests.

Runtime logs:
`C:/Users/ckishor/AppData/Local/FitiGo/runtime/backend-20261111-230842-27391bf7`.
Verification JSON/logs are in the private backup directory above.

## Use and remaining boundaries

Refresh `http://localhost:5173` and sign in normally:
- Owners/staff: Help & support, then My support requests.
- Customers: Account settings, Support.
- Administrators: Support requests and Readiness checks in admin navigation.

Support content is private application data. Authorized admins must monitor the
queue and establish retention/handling responsibilities; no response-time SLA,
email forwarding or attachment service is promised. Support contact email remains
unset rather than invented.

Recovery: disable only the support flag if necessary, retain tables/history, and
restore compatible application code. Do not downgrade nonempty conversations.
Any destructive database/media restore requires a separate verified plan; the
dump contains DROP TABLE statements and must not be blindly imported over newer
data. No automatic rollback occurred.

Next product decisions remain staff authorization and gym archival/closure policy.
Overnight schedules, manual attendance exceptions, external message acceptance,
orphan/legacy reconciliation and production infrastructure verification are not
silently included. Refunds, gateway rescheduling, wallet spending and gateway
offers remain unavailable as requested.