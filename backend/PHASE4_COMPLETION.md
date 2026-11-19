# Phase 4 completion — implementation and isolated validation, not deployment

> Subsequent user-approved local deployment is recorded in
> `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend/LOCAL_DEPLOYMENT_PHASE4.md`.
> The deployment boundary below describes the state before that operation.

## Final status

Final guarded backend run: **626 passed, 0 failed, 0 errors, 0 skipped** in 196.67 seconds. Existing warnings remain (20,831 warnings reported, predominantly legacy deprecations); no assertion was removed or failure skipped to reach this result. Frontend: **385 tests passed**, TypeScript application check and production build passed. Mocked class-policy browser check passed at 360/768/1440px.

Verified on the installed MySQL executable reporting **26.7.0**, in a completely separate process/data directory. This is not a claim that every MySQL 8.x/minor version was exercised. The FK-before-index DDL ordering is explicit and the actual local server round trip passed; deployments on another supported server version should repeat the isolated migration tests there.

No working-database migration or orphan cleanup was performed. The earlier accidental test writes are recorded in `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend/PHASE4_CHECKPOINT.md`: user 3862, one role mapping and DRAFT gym 1668. They remain untouched. This completion does not erase that incident or claim that the entire Phase 4 history was free of working-database writes. After the safeguard was installed, regression testing used only separate runner-owned MySQL instances and in-memory SQLite.

The original temporary audit report was unavailable during Phase 4; the prompt and repository handoffs supplied the baseline. Prior feature changes were preserved; no reset/stash/cleanup/commit/push/deployment was performed.

## Fail-closed test isolation

Files:
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend/conftest.py`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend/test_database_guard.py`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend/scripts/run_isolated_tests.py`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend/tests/test_database_safeguard.py`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend/app/core/config.py`

Plain pytest refuses collection before any application imports when the isolated configuration is missing/invalid. It does not turn database tests into skips or let legacy SessionLocal imports fall back to the working .env. Tests with application modules already imported before bootstrap also fail closed.

The runner does NOT consume the user's proposed `FITIGO_TEST_DATABASE_URL=.../dev_fitigo` values. It does not read application .env or administrative working-server credentials. Instead it:
1. Creates a unique private temporary directory and initializes a new MySQL datadir with `--no-defaults`.
2. Starts that owned process on loopback with a nonstandard free port and MySQL X disabled.
3. Generates credentials and verifies server datadir/port before creating the run's main schema.
4. Uses a test account granted privileges only for its generated schema namespace on that separate instance. Credentials are not printed or placed on the process command line.
5. Supplies an environment allowlist with a random JWT key and disabled real delivery/provider credentials, plus generated run ID/database URL/name. Application settings bypass dotenv in this child.
6. Applies migrations to the disposable main schema, then runs pytest with all existing MySQL test opt-ins enabled.
7. Stops only its own server process. The unique private data/log directory is retained for diagnostics; it does NOT recursively delete paths or drop arbitrary prefix-matching databases.

SQLAlchemy's pre-driver connection hook rejects other hosts/ports/users/credentials/schema names, positional/unsupported driver arguments, socket/default-file overrides, and file-backed SQLite. Existing test fixtures use run-scoped `disposable_name()` rather than independent naming prefixes. Their create/drop operations are confined to the separate server and exact fixture-created schemas. Existing fixture scopes and meaningful assertions remain.

These controls prevent accidental misconfiguration; they are not a sandbox against malicious test code with OS access. Do not bypass them by running test files as arbitrary scripts. Keep isolated-run data/logs private; fixture tokens can appear in legacy assertion output. The retained datadir consumes disk space; after reviewing the exact run and ensuring its process is stopped, an operator may approve removal of that specific directory. No broad automatic cleanup is included.

Command (no manual run-ID or database variables needed):

```powershell
Set-Location 'C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend'
& './.venv/Scripts/python.exe' scripts/run_isolated_tests.py --mysql-bin 'C:/Program Files/MySQL/MySQL Server 26.7/bin/mysqld.exe' -q --tb=short --disable-warnings
```

Pass specific test paths after `--mysql-bin` for targeted runs. A missing binary/startup/migration error fails before tests and reports private artifact locations; it does not fall back to the working database.

## Migration repair and data preservation

`C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend/alembic/versions/acf58d9e1037_wallet_gateway_history.py` now drops `fk_wallet_transaction_checkout` before `uq_wallet_transaction_checkout` and its column. MySQL had used the unique checkout index to support the foreign key, causing error 1553 with the old ordering.

Downgrade still refuses when payment attempts or checkout-linked ledger records exist. It additionally refuses if any wallet has non-null payment-mode metadata, rather than silently losing test/live classification. Empty guarded fields/tables can be removed; legacy balances and ledger rows survive round trip. No automatic financial archival or bypass is supplied. This protects data even when an operator requests a rollback; other older migrations that drop business tables are not endorsed for working-data rollback.

New `cef70fb23591`, parent `bdf69ea12480`, adds:
- `gym_slots.sync_kind`: existing rows default to LEGACY, new application-created ordinary slots are DIRECT, scheduled classes are CLASS.
- `class_sessions.source_slot_id`: nullable explicit FK/index to the generating slot.

No name/time heuristic backfill is performed. Upgrade resumes after partially committed column/FK/index DDL. Downgrade refuses any populated session link or non-LEGACY slot provenance before dropping fields; it never silently erases those relationships. In-memory and actual isolated MySQL migration checks cover upgrade/downgrade/re-upgrade, preservation of seeded legacy ledger/slot data, and refusal with protected metadata. QR concurrency fixtures also traverse the real migrations and partial-DDL recovery path successfully.

## Approved class behavior

The user approved the conservative policy: **synchronize unbooked future sessions; block the entire change when reservations/payment-pending sessions are affected; preserve history; require explicit reconciliation for legacy links.**

- Creation stores an explicit source-slot association. Duplicate active class/date/time creation returns 409 rather than creating a misleading empty owner schedule.
- Name/time/price/capacity edits synchronize linked future sessions in the same transaction as the owner slot.
- Past or already-started sessions retain their details. Renaming creates new class metadata for future sessions rather than changing a shared historical GymClass name.
- Booked capacity, CONFIRMED/PAYMENT_PENDING cart reservations and existing pending/confirmed booking links block the entire mutation with CLASS_HAS_RESERVATIONS. A conservative positive booked counter remains a blocker even if inconsistent; it is not silently repaired.
- A direct slot with booking history cannot have its name/time rewritten because historical booking/access display still references that slot. Create a new schedule instead.
- Deactivation cancels only unstarted, unbooked linked sessions and prevents new class purchases. It does not cancel customer bookings, grant refunds, move attendance or delete history.
- Active shopping carts are not paid reservations. Affected entries are marked REMOVED rather than silently moving their selected class time/price. Customers must reselect the updated session.
- Reactivation does not resurrect cancelled sessions. Recurrence/date changes require a new schedule; they are rejected explicitly rather than ignored.
- LEGACY slots reject edits/deactivation until provenance is explicitly reconciled. This intentionally limits legacy schedule editing rather than guessing associations.
- Gym-first locking coordinates owner changes, class cart selection, direct slot reservation and cart checkout; current locking reads avoid stale repeatable-read data. The actual MySQL race test permits only: edit commits/cart is invalidated, OR pending reservation commits/edit is rejected.
- Existing timestamps and preserved historical rows provide the available history. No complete before/after actor audit ledger existed for classes, and this phase does not claim to add one. A dedicated class-edit audit ledger remains future work if required.

Frontend owner copy and controlled error-code messages explain blocked reservations, protected history and legacy reconciliation. The browser fixture checks failure remains a failure with no success state until a permitted retry succeeds.

Core files:
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend/app/models/slot.py`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend/app/models/class_booking.py`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend/app/services/slot_service.py`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend/app/services/class_sync_service.py`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend/app/routers/cart.py`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend/app/services/payment_checkout_service.py` (class lock ordering only; provider/amount/fulfillment rules unchanged)
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend/app/services/booking_service.py`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/frontend/src/owner/Operations.tsx`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/frontend/src/services/client.ts`

## Failure classification and repair

Original audit: 415 passed, 24 failed, 2 setup errors. Subsequent phases added tests; Phase 3 reached 574 passed, 24 failed, 2 errors. Counts are not a like-for-like unchanged test population.

| Cases | Classification and repair |
| --- | --- |
| admin booking ops/report; admin booking search; booking capacity; expired-pending capacity; two reschedule cases; customer booking detail; owner booking view; original staff invitation access | Same-day morning fixtures conflicted with future-start policy. Explicit future IST dates used, preserving capacity/ownership/idempotency assertions. Staff invitation case was already repaired in Phase 2 to use the real invitation acceptance/login contract. |
| booking idempotency same-key case | Additional time-sensitive evening fixture fails after 18:00; moved to a future IST date. No production time validation loosened. |
| booking capacity after date repair | Fixture manually set APPROVED after submission but left is_active=false. Fixture now sets approved AND active. |
| successful pending reschedule after date repair | Real bug: demanded an admission window even when an unpaid booking had no QR records to rotate. Now window validation/rotation runs only for existing passes; future-start, capacity, same-gym, paid-price and used-QR restrictions remain. |
| five customer-access system tests and one membership daily-QR test | Obsolete internal dummy purchase/invitation setup failed before access assertions. Test-only explicit entitlements/assignments replace retired setup, not application behavior. Multi-Gym is an explicit membership/partner scope; calendar uses its own membership and real successful check-in evidence. Actual purchase and invitation flows retain separate tests. |
| wallet production/external-payment case | Retired top-up endpoint deliberately returns 409 directing gateway checkout, not 403. Test now asserts exact status/message AND unchanged balances. |
| eight safe-error logging cases | In-process Alembic fileConfig disabled application loggers/replaced capture handlers. Alembic preserves existing host handlers and uses disable_existing_loggers=False only when configuring a standalone console. Existing safe-error/log-content assertions unchanged. |
| two booking QR MySQL setup errors | Wallet FK/index downgrade ordering defect; fixed, both real concurrency assertions now execute and pass. |

No failing test was deleted, renamed away, or newly skipped. Ten originally audited booking/invitation fixtures and six admission tests were reviewed alongside the later additions. Exact baseline failing names remain in the checkpoint/task output. Full final run has zero skips with all MySQL opt-ins enabled.

Test additions/updated fixtures include:
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend/tests/test_phase4_migrations_mysql.py`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend/tests/test_class_synchronization.py`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend/tests/test_class_synchronization_mysql.py`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend/tests/legacy_access_fixtures.py`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/frontend/scripts/class-sync-browser.mjs`
- existing affected booking/access/wallet fixture files and five disposable MySQL fixtures now using run-scoped names.

## Orphans: evidence preserved, cause not established

Read-only inspection earlier in Phase 4 found 11 wallet transaction user references and one staff-assignment user reference orphaned. Four TOPUP credits total INR 2500 and seven PAYMENT debits total INR 1999; entries date September 3–30, 2026. All ledger rows reference existing wallet accounts with matching stored user IDs, but those account owners are missing too. The staff assignment's gym exists. Declared foreign keys are present.

This proves invalid references, not their historical cause. Existing rows and source/migration history cannot distinguish deleted accounts, imports or temporarily disabled FK checks without backups/binlogs/account audit evidence. No ledger/account/assignment was deleted, reassigned or modified. No repair migration was created because the correct identities/financial ownership are unknown.

Separate approval plan before any repair:
1. Back up exact affected users/accounts/ledger/assignments/gyms and schema/version in a private snapshot; retain checksums and counts.
2. Dry-run read-only anti-join queries and compare historical backups/binlogs to establish identity and authorized financial ownership. Include orphaned wallet accounts, not just their ledger rows.
3. Produce an explicit per-record proposed mapping or restoration plan with evidence; do not infer identity from amounts/names or create dummy users to satisfy FKs.
4. Obtain review/approval; implement a separate guarded, idempotent repair transaction with expected-row/version checks and a verified restoration procedure. Validate balances against unchanged movement history before/after.
5. If evidence remains insufficient, retain/quarantine records from operational use and report the discrepancy rather than deleting financial history.

The earlier accidental user 3862/gym 1668 is a separate cleanup decision, not part of orphan reconciliation. No deletion permission is assumed.

## Validation evidence and limitations

- Initial restored migration/QR/logging selection: 27 passed.
- Intermediate isolated full run after those fixes: 584 passed, 16 failed, zero setup errors.
- First new guarded selection: 51 passed.
- Migration/class/concurrency/logging selection: 40 passed.
- Final full guarded run: **626 passed, zero failures/errors/skips**. Negative safeguard fixture was corrected to truly remove a SQLAlchemy URL port; the application guard was not weakened.
- Frontend final: **385 passed**, typecheck exit 0, production build exit 0.
- Class browser fixture: passed policy notice, blocked 409/no-change state, permitted retry, responsive layout.
- Final raw backend XML/logs: `C:/Users/ckishor/AppData/Local/Temp/fitigo-isolated-062218a06020bafb-rtmp0a7q/results.xml` and `pytest.log` in that same directory. Keep them private.
- Frontend/browser logs: `C:/Users/ckishor/AppData/Local/Temp/fitigo-phase4-final`.

No real email, SMS, payment, refund or physical device acceptance was performed. The suite passing does not certify all production concurrency/performance/security properties. MySQL warnings/deprecations remain. Test data directories are retained, servers stopped.

## Deployment boundary / exact next step

The working database was last observed at `acf58d9e1037`, missing Phase 2 tables and Phase 4 provenance columns. Current code therefore still cannot serve affected bookings/class queries against that schema. **Passing isolated tests does not fix the running application's missing-column error.**

Next step is a separately approved backup and forward-migration/deployment plan for the intended local/staging database: review the full accumulated diff, verify the exact target, snapshot data, apply pending additive migrations `bdf69ea12480` and `cef70fb23591`, then restart the correct FitiGo backend and verify its health/schema before login/bookings checks. No migration command was executed on that database here. Do not run a downgrade there to test rollback; it is intentionally guarded against data loss.

Legacy class linkage remains deliberately blocked after migration until individually reviewed. Wallet spending, gateway-funded offers, automatic refunds and orphan cleanup remain outside this completed phase. Do not start another phase or modify working data without explicit authorization.

Current `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/frontend/vite.config.ts` has BOTH proxies targeting port 8000, contrary to the earlier handoff. Verify which application owns that port and deliberately align FitiGo's backend and both proxies (8000 was previously recommended). The startup script was not run; do not use it blindly to stop existing port-8000 applications.

Final process verification found that Windows MySQL child processes survived launcher termination. The runner was corrected to verify datadir ownership and issue authenticated SHUTDOWN, with an owned process-tree fallback. Earlier isolated child processes were individually matched to the six exact run directories before stopping them; working-server processes were excluded. No datadir was deleted.

Post-shutdown-fix safeguard/class concurrency rerun passed (11 tests), with process enumeration confirming no test mysqld children remained. Its artifacts are at `C:/Users/ckishor/AppData/Local/Temp/fitigo-isolated-40ad3134c7fd5442-mchjq6jx`. The full 626-test result above remains the final application regression run; only runner shutdown handling and this documentation changed afterward.