# Phase 4 checkpoint — incomplete; test-isolation incident

> Historical checkpoint. Subsequent safeguard/remediation results are documented
> in `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend/PHASE4_COMPLETION.md`.
> The incident and affected records below remain part of the record; no cleanup
> was authorized or performed.

## Safety incident (November 10, 2026)

During Phase 4 the agent mistakenly included `test_owner_list_slots.py` in a direct pytest invocation rather than the disposable-database harness. That legacy test imports the configured SessionLocal and commits its account and gym setup before creating a slot. This violated the requirement not to write to the working database.

Read-only inspection identified the new matching fixture records:
- User ID **3862**, created `2026-11-10 15:37:41` (stored database timestamp).
- One user-role mapping for that user.
- Gym ID **1668**, named `SlotGym`, city `X`, status DRAFT, same timestamp.
- Zero slots for that gym. The slot insert failed because the working schema has no `gym_slots.sync_kind` column.

No cleanup, reassignment or migration was performed afterward. Do not delete these records automatically: recheck exact ownership/dependencies and obtain explicit approval before any repair. No password, token or email address is included in this checkpoint.

The working schema still reports revision `acf58d9e1037`; Phase 2/4 migrations have not been applied there. New class code depends on the new schema. It must not be presented as deployed/working against the current local database. Existing servers may auto-reload source changes; no restart or migration is authorized by this checkpoint.

## Approved class policy

The user approved synchronizing unbooked future sessions, atomically rejecting changes affecting booked/payment-pending sessions, preserving historical sessions, and requiring explicit reconciliation of ambiguous legacy associations. No automatic customer rescheduling, cancellation or refund was approved.

## Changes in progress (not acceptance-complete)

- Wallet migration `acf58d9e1037`: foreign key is dropped before the dependent unique index; an additional guard prevents discarding classified wallet payment-mode metadata.
- Alembic logging: preserve an embedding process's handlers; standalone setup uses `disable_existing_loggers=False`.
- New additive migration `cef70fb23591`: `gym_slots.sync_kind` and nullable `class_sessions.source_slot_id`; no guessed legacy linkage. Downgrade guards populated provenance. Requires further dedicated round-trip/data-preservation testing.
- Class service: explicit provenance for newly created schedules; transactional future-session synchronization; reservation blocking; past-session name preservation through class metadata cloning; stale active carts invalidated; legacy linkage and recurrence/date edits fail explicitly. Class cart selection locks the session. Further concurrency review/tests and frontend explanatory text are still required.
- Legacy booking tests: explicitly listed fixture dates moved to future IST dates, preserving assertions.
- Six admission tests: replaced obsolete purchase/invite setup with test-only entitlement/assignment fixtures; explicit Multi-Gym semantics and real check-in calendar evidence.
- Retired wallet top-up test: now expects the documented 409 redirect-to-gateway response and still asserts unchanged balances.
- Pending unpaid reschedule: avoid computing/rotating an admission window when no QR records exist. This newly discovered application fix still needs its final regression run.

## Test results so far

1. After wallet downgrade/logging fixes: **27 passed** (wallet migration, both real disposable MySQL QR concurrency cases, safe-error tests).
2. Full isolated MySQL run after those fixes, before the remaining repairs: **584 passed, 16 failed, 0 setup errors** (600 tests). Disposable main schema removed.
3. Isolated legacy repair selection: **23 passed, 2 failed** (25 tests). Remaining failures traced to approval fixture leaving gym inactive, and unpaid reschedule unnecessarily requiring an admission window. Corrections made afterward, not yet rerun.
4. Class/time/QR/owner-slot selection: **53 passed, 1 failed**. The one failure is the unsafe legacy test invocation described above, against an unmigrated working schema. This is NOT a successful isolated run and must not be counted as Phase 4 completion.
5. Git whitespace check passed at checkpoint. No final Phase 4 full backend/frontend/typecheck/build results exist yet.

No failing tests were deleted or skipped to obtain these counts. Existing MySQL opt-in tests were enabled for the disposable full run.

## Orphan investigation (read-only)

- Eleven wallet transactions still reference missing users. Four IN/TOPUP entries total INR 2500; seven OUT/PAYMENT entries total INR 1999; recorded between September 3 and September 30, 2026.
- All eleven reference existing wallet accounts whose stored user IDs agree with their ledger entries, but those account users are also missing. Reassigning only the ledger would not repair ownership correctly.
- One staff assignment references a missing user and an existing gym; stored creation timestamp September 30, 2026.
- User/account/gym foreign keys are declared. These rows alone do not prove whether deletion, import or disabled constraint checking caused the inconsistency. No historical audit/binlog evidence establishing cause was found in this inspection.
- No orphaned row was modified. Further remediation needs a reviewed backup/evidence plan, not blanket deletion.

The original temporary audit report was unavailable; findings in the prompt and repository handoffs were used. Current Phase 4 temporary test artifacts/harness are under `C:/Users/ckishor/AppData/Local/Temp/fitigo-phase4`; raw legacy assertions can include disposable test tokens and must remain private.

## Required next action

Pause for user acknowledgment of the incident. Recommended continuation is to leave the accidental fixture records untouched, first install a fail-closed test-database safeguard so direct legacy tests cannot reach the working schema, then resume all Phase 4 testing only in disposable databases. Any cleanup of IDs 3862/1668 is a separate explicitly approved operation. Phase 4 is incomplete and must not be deployed or described as certified green.