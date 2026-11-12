# Local operations + notification completion

## Scope and disposition

The user requested remaining work and explicitly selected non-financial workflows,
keeping refunds, gateway rescheduling, wallet spending and gateway offers disabled.
Notification preferences/inbox, safe delivery intent processing and configured
support contact were implemented. Phase 6 operational features and the new inbox
were activated locally after backup/restore rehearsal. External email remains OFF.

This is not a declaration that every possible application gap is finished.
Custom staff roles, overnight schedules, manual attendance overrides, gym deletion,
complete security audit/immutable storage, editable global business policies,
push/SMS operational delivery and support ticketing remain separate extensions.
Orphan records, accidental fixtures and legacy class linkage remain untouched.

## Validation

- Full enabled backend run: **680 passed, zero failures/errors/skips**, 23,010
  existing/deprecation warnings; 404.05 seconds.
  Artifacts: `C:/Users/ckishor/AppData/Local/Temp/fitigo-isolated-0f6c45279d132720-uchtrs4n`.
- Subsequent fix: photo-cleanup GET used SELECT FOR UPDATE despite being read-only.
  Replaced it with an ordinary owner-scoped SELECT; mutation locks remain intact.
- Post-fix isolated safety/notification/MySQL selection: **39 passed**.
  Artifacts: `C:/Users/ckishor/AppData/Local/Temp/fitigo-isolated-7528491fb20e2d69-kziytyss`.
- Frontend **399 passed**, TypeScript and production build passed.
- Mock browser passed preference failure/success, read status, uncertain delivery,
  admin processing, owner/profile/photo regressions and widths 360/768/1440.
  Artifacts: `C:/Users/ckishor/AppData/Local/Temp/fitigo-notifications`.
- Final authenticated **20-route read-only smoke passed** against the local
  migrated data. DB-enforced read-only transactions and SQL allowlisting; temporary
  short-lived access tokens stayed in memory. No login/session insertion.
- Direct/proxied database health passed; no test MySQL processes remained.
- Git whitespace check passed. No assertion was deleted/skipped to claim green.

Initial failures were documented and fixed: one tuple-shaped fixture invocation,
MySQL timestamp rounding, and minimal password/gym-review fixtures missing new
tables. The slow first full run ended 675 passed/one fixture failure; it is not
counted as the final passing run. Browser first-load timing was made tolerant of
the busy local machine; failure/error assertions remain.

## Backup and activation evidence

Private directory:
`C:/Users/ckishor/AppData/Local/FitiGo/backups/operations-notifications-20261111-213214`

ACL permits current Windows user and SYSTEM. It contains database dump, source/
configuration snapshot, pre-activation .env backup, table hashes, media archive,
separate restore directories, rehearsal/results and one-off guarded deployment
scripts. These contain private data/secrets; do not commit, publish or share them.

- Database: **43 tables** restored to a separate loopback-only MySQL process and
  compared by column inventories/counts/canonical row hashes and normalized DDL.
- Uploads: **13 files, 1,972,717 bytes**, archived, restored separately and verified
  against SHA-256 manifests before and after activation.
- Working database identity confirmed as local `fitigo`, port 3306, same UUID and
  MySQL 26.7.0 as prior verified deployment.
- Restore copy rehearsed upgrade before the working migration. Existing data
  survived unchanged. Migration source hashes and backup checksum rechecked.
- Working revision moved from `cef70fb23591` through `df081ac34602` to
  **`ef192bd45713`**, completed `2026-11-11T16:09:51.049672+00:00`.
- All **42 original business tables** remained identical; only the Alembic version
  and intended new schema changed. Final smoke reconfirmed business/media hashes.
- All four new tables were empty after smoke: no synthetic preferences/events,
  photo removals or business mutations were inserted into working data.

Database dump SHA-256:
`e3dd8278834e004154adbc9fbc090128638de7c692469ad7f3ee1db97d62bc12`

Media archive SHA-256:
`7fb3c6cecc62ae0d5cf55936890ec32a412baef32fc3ea9873595119e3f2617f`

Upload-root ACL was reviewed: SYSTEM, Administrators, current application user;
no media symlinks/junctions were present. No existing file was deleted. Cleanup
and email workers were not executed or scheduled on working data.

Only the verified FitiGo 8001 process tree was stopped for maintenance and
restarted. The unrelated port-8000 listener was preserved. Frontend remains on
5173, API on 8001. Runtime logs:
`C:/Users/ckishor/AppData/Local/FitiGo/runtime/backend-20261111-213951-c6a10fe5`.

Private local `.env` flags now:
- OPERATIONAL_WORKFLOWS_ENABLED=true
- NOTIFICATION_WORKFLOWS_ENABLED=true
- NOTIFICATION_EMAIL_ENABLED=false

No signing/provider credentials were changed or printed. SUPPORT_EMAIL remains
unset: a real address must be supplied, never guessed. Other deployment targets
still need separate backup/migration/configuration review.

## Recovery

Do not downgrade populated audit/job/preference tables. Disable workflow flags
to stop generating new intents if needed, then restore compatible application
code. Keep external email off. For a database rollback, stop writers and restore
the verified dump into a separate target first; it contains DROP TABLE statements
and must not be blindly imported over newer working data. Media restoration must
be manifest-reviewed to avoid overwriting newer uploads. This operation did not
perform a destructive rollback or automatic cleanup of retained restore files.

## What still needs input / operational acceptance

1. Supply the intended support email privately/in configuration.
2. To enable notification email: approve sender configuration and verified test
   recipients, authorize actual sends, schedule/monitor the worker, validate SMTP
   acceptance and failure behavior, and define bounce/retention handling.
3. UNKNOWN sends are deliberately not retried. Investigate with provider evidence;
   do not manually mark sent or reset queue states without a reviewed repair plan.
4. Actual inbox/handset delivery, physical-camera scans and production acceptance
   remain manual. Current browser tests mock network mutations.
5. Financial features remain unavailable as chosen. No policy was invented.
6. Orphan/legacy reconciliation requires evidence and exact-record approval.

Implementation details:
`C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend/NOTIFICATION_WORKFLOWS.md`
and `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend/PHASE6_OPERATIONS.md`.
All accumulated source changes remain uncommitted; no reset/stash/push occurred.