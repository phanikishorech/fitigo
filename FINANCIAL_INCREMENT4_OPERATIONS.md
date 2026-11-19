# Financial deployment operations — NOT an activation authorization

Workspace: `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo`.
This runbook is a release proposal. No working/production migration, worker,
scheduler, correction or payment was executed during the exercise.

## Release decision

**NO-GO for production financial allocation or payouts.** Code/schema rehearsal
does not resolve absent source tax, missing gym versions/settlement policies,
historical evidence gaps, monitoring ownership or production restoration approval.

Production infrastructure, replication, grants, schedulers, secret manager and
provider production dashboards were not accessible/validated here. Local fixtures
are not a production clone or a performance qualification.

## Verified migration chain

36 revisions, one linear head `eb3f70126935`. No new migration in Increment 4.
Outstanding from the inspected working revision, in order:

| Revision | Adds/changes | History protection / rollback limit |
|---|---|---|
| `e57f81cb0379` | Source configuration pins | ORM immutable; populated downgrade refused |
| `f68a92dc1480` | Source evidence, owner evidence, leased outbox | ORM immutable identity/evidence; no raw-SQL immutability triggers |
| `a79ba3ed2591` | Percentage allocations | MySQL monetary checks, unique units, UPDATE/DELETE triggers |
| `b80cb4fe3602` | Verified visit allocations | Unique check-in/daily access, amount check, immutable triggers |
| `c91dc50f4713` | Manual payouts/items/audit | Claim constraints, unique references, immutable items/audit triggers |
| `da2e6f105824` | Monthly completion, membership fee budgets; nullable visit cap | Unique gym/month/revision and checkout fee budget; immutable triggers; forward-only |
| `eb3f70126935` | Financial review event history | Unique case/revision and request key; immutable triggers; forward-only |

All parents from base were exercised by fresh installation, not only the two most
recent revisions. Existing migration files were not edited. A populated synthetic
database was installed at `d46e70ba9268` then upgraded: fingerprints of every existing
table except `alembic_version` matched exactly afterward. No source/funding/financial
backfill appeared. The fixture retained an incomplete legacy contract, missing
funding, a cancelled paid booking, wallet liability and a spanning membership.

Migration checks include FKs/unique constraints/index metadata, allocation checks,
nullable uncapped metadata, and all financial trigger names. Restore testing also
performed raw UPDATE/DELETE against a restored populated review record and verified
the immutability triggers reject both.

**Privilege risk:** agreement versions, pins, source evidence and owner evidence
currently rely on ORM immutability plus hashes; a privileged raw-SQL actor can bypass
those guards. Deploy runtime grants without DDL and restrict UPDATE/DELETE on
append-only tables where feasible. Outbox leases and payout state require narrowly
scoped UPDATE access. Migration/backup users must be separate from runtime users.
Do not claim all financial records have database-trigger protection.

## Deployment sequence after separate approval

1. Identify exact application artifact/commit, MySQL version, deployed revision,
   all serving instances and scheduled jobs. Preserve existing unrelated working
   changes in version control before release; this workspace is not a clean release
   commit. Validate on the actual supported target MySQL version.
2. Confirm all four flags explicitly false on every instance. Disable financial CLI
   jobs in the process supervisor/cron/task scheduler; do not merely rely on flags.
3. Record cutover and maintenance window; drain writers for migration/backup if
   required by the DBA-approved plan. Do not run migrations from API startup.
4. Produce and verify a protected backup; rehearse restore as below. Capture schema,
   row fingerprints/counts, triggers, grants, migration revision and artifact hash.
5. Apply the reviewed chain in staging first, then production only under the
   separate approval. Run one migration process. Inspect each revision/DDL result;
   if interrupted, stop and inspect rather than stamping past failure.
6. Deploy current code with all four flags false. Validate API startup, admin role
   denial, missing-evidence reports and normal purchase/access recovery; no posting
   smoke test against existing customer history.
7. Initialize missing gym settings only through explicitly authorized future-dated
   configuration changes. Never copy current owner/tax values into old purchases.
8. Obtain independent signoff for each later gate stage. Deployment alone grants no
   permission to run monthly completion, correction execution or payouts.

## Backup, restoration and rollback

### Rehearsed here

On a new disposable MySQL 26.7.0 server: fresh schema + synthetic existing rows +
immutable review evidence were dumped using `mysqldump` and restored with `mysql`
into a second new schema. All table fingerprints and trigger sets matched; restored
triggers rejected raw mutation. A temporary client option file held only generated
test credentials and was removed. No working DB dump or restoration was performed.

### Production procedure still requiring DBA signoff

- Use protected secret-manager credentials; never passwords in command arguments,
  repository files or logs. Restrict backup file access and encrypt retained copies.
- Include schema/data/triggers and applicable routines/events. Audit restored
  scheduled events before allowing an event scheduler to run. Keep all financial
  workers and flags off during recovery.
- A single-transaction InnoDB dump must not overlap schema-changing DDL. Retain
  matching binary-log coordinates/GTID and logs if point-in-time recovery is required.
  These precautions follow the MySQL Reference Manual's mysqldump guidance.
- Restore into a NEW isolated target first, never over the sole production copy.
  Validate row hashes/counts, FK/check/unique constraints, triggers, revision, audit
  continuity, wallet/provider reconciliation and pending checkout/outbox states.
- Agree RPO/RTO and retention with operations. Those business targets are not
  invented here. This runner disables binary logging; PITR/failover replication was
  **not** rehearsed and remains a production acceptance item.
- A restore to an older backup loses intervening activity unless reconciled/replayed.
  Drain traffic and provider callbacks under an incident plan, preserve current data
  for investigation, and reconcile every uncertain provider capture/refund before
  reopening payment flows. Never recreate gateway orders merely because local state
  was restored.

Reference consulted: MySQL Reference Manual, “mysqldump — A Database Backup
Program” (official documentation; no tax/legal advice used).
Official references (for release reviewers):
```
https://dev.mysql.com/doc/refman/8.4/en/mysqldump.html
https://dev.mysql.com/doc/refman/8.4/en/implicit-commit.html
https://dev.mysql.com/doc/refman/8.4/en/cannot-roll-back.html
```
These documented DDL/backup limitations inform the runbook; the actual local
rehearsal used installed MySQL 26.7.0, not a claim of testing MySQL 8.4.

### Application rollback compatibility

- Prefer forward code repair with financial gates off and financial workers stopped.
- The seven new revisions are additive except nullable `applied_cap`; old rows were
  preserved. This does not prove an arbitrary old binary can process new JSON forms.
- Before any consolidated versions/allocations exist, a compatible code-only rollback
  may be possible with gates off, but must be tested against the target release.
- After monthly records or EXECUTED review events exist, older financial consumers
  may misclassify pending gross, NULL caps, monthly protocols or review status. Do not
  roll back financial processing to a binary lacking these formats.
- `da2e6f105824` and `eb3f70126935` reject downgrade; earlier financial revisions
  refuse populated destructive downgrades. Do not drop triggers/tables or stamp a
  revision to force rollback. Restore under the approved recovery plan or forward-fix.

## Worker and scheduler controls

- API startup does not schedule allocation, source-handoff, monthly completion,
  fee attribution or correction execution. Existing wallet-hold recovery remains
  unchanged and is NOT the commercial allocation worker.
- Startup now rejects inconsistent enabled gate combinations and missing required
  financial schema. All-off startup performs no financial schema activation.
- Both CLI workers now require `--authorization-reference` in addition to explicit
  mode. The reference is an operator acknowledgment, not a cryptographic approval or
  authorization to enable flags. Deployment access control still governs execution.
- Allocation CLI accepts explicit outbox IDs (maximum 100), never scans history.
  Successful retry returns immutable original IDs; blocked events roll back and
  report codes. It does not update source handoff status into a false “paid” state.
- Source handoff uses expiring fenced leases, SKIP LOCKED and redacted exponential
  retries. AWAITING_POLICY/AWAITING_EVIDENCE means no allocation was posted.
- Live CLI requests additionally require the live-processing gate. Evidence capture
  can be evaluated without starting a live handoff worker.
- No monthly scheduler exists; deploying this code cannot start one. Future scheduler
  design must preserve explicit periods, close-time completeness and idempotency.

## Logging, monitoring and incident checks

Existing visibility: immutable source/review/month/allocation hashes and references,
outbox last_error/retry/lease fields, structured allocation CLI outcomes, Admin
reconciliation/trace endpoints and a new read-only inventory artifact with outbox
status counts, expired leases, oldest pending creation time and payout status counts.

**Not implemented/deployed:** metrics scraper, alert delivery, paging rota, dashboard
SLOs or unattended dead-letter resolver. These are release blockers for unattended
processing. Assign an operator and approved thresholds rather than inventing them.

Required alerts before activation:

| Signal | Required response |
|---|---|
| Unexpected enabled gate/worker or schema mismatch | Stop financial consumer, keep customer recovery intact, verify deployment |
| Source hash/identity/owner/environment conflict | Quarantine source; do not rewrite evidence |
| Growing oldest PENDING/RETRY or expired leases | Inspect lease ownership/backoff, retry only with approved bounded IDs |
| Missing tax or provider fee | Keep allocation/net blocked; investigate authoritative ingestion |
| Fee/funding/paise difference or over-reservation | Stop affected posting/payout cohort, review evidence |
| Late admissions/month correction/closed fee budget | Open review; no automatic rebalance |
| Refund after allocation/reservation/payment | Preserve claim, require coordinated reversal/return review |
| Backup/restore verification failure | No migration or gate activation |

## Four-gate readiness matrix

All current statuses: **FALSE / NOT AUTHORIZED**.

| Gate | Purpose | Dependencies/configuration/evidence | Tests and safeguards | Exact activation conditions |
|---|---|---|---|---|
| `source_evidence_enabled` | Capture NEW source/owner/outbox facts atomically | Pins/evidence/funding migrations; consistent rollout; trusted checkout identity/amount/currency/owner observation; explicitly unknown tax remains unknown | Source producer/provider/dedup/rollback and normal booking/access tests; no historical fill; handoff worker separate | Reviewed backup/restore + schema/grants + all mutation-serving instances on one reviewed build + documented evidence cutover + source coverage monitoring + explicit evidence-only approval |
| `marketplace_allocations_enabled` | Permit internal percentage/visit/month/correction allocation services | Evidence gate true; allocation/month/fee/review schema; effective own-gym versions; verified admission/purchase funding; explicit purchase tax/discount for percentage allocation; actual fee or net pending | Exact paise, gym/mode isolation, duplicate/concurrency/cancellation/month completeness tests; CLI bounded IDs; no automatic scheduler | Evidence stage signed off + authoritative tax integration for intended percentage cohorts + configured monthly protocol + reviewed isolated/staging reconciliation + on-call/runbook + explicit allocation approval; test mode first |
| `marketplace_live_allocations_enabled` | Additional live-environment allocation and worker permission | Allocation gate and evidence true; live-only configurations and evidence; no mixed test/live data; approved rollout scope | Live-denial tests, source/configuration isolation and restore/cutover checks; no toggle endpoint | All earlier checks plus controlled staging/provider acceptance, independent reconciliation signoff, production deployment authorization, bounded reviewed live cohort and monitored rollback plan |
| `marketplace_payouts_enabled` | Permit manual reservation/approval/payment-attestation workflow, never bank calls | Allocation readiness; live gate for live claims; complete pinned settlement cutoff/holding/deduction policies; validated net/fee budgets; no open review/refund/invalidations; actual bank evidence for PAID | Reservation race/idempotency/independent review/paid protection/return reference tests; approval ≠ payment | Finance approves settlement values + clean cohort reconciliation + permission separation and payment-reference reconciliation + recovery/monitoring owner + explicit payout-workflow authorization. Actual transfer remains separately authorized outside this implementation |

Turning a gate off does not undo committed evidence or allocations. Pause, inspect
and reconcile; never delete audit rows as a rollback technique.