# Increment 4 — Deployment readiness and controlled validation

## Outcome

**Ready for deployment review, NOT approved for production financial activation.**
Validated actual source/migrations/tests rather than treating previous handoffs as
proof. All work was code, documentation, read-only inventory, or synthetic isolated
tests. No production environment/provider acceptance claim is made.

Operational procedures and the detailed four-gate matrix are in:
`C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\FINANCIAL_INCREMENT4_OPERATIONS.md`.

## 1. Verified implementation and migration status

- Increment 1: own-gym versioned settings, actor/reason/effective dates, immutable
  history and new-gym initialization exist. Existing missing settings are NOT seeded.
- Increment 2: one shared calculator; configured percentage/fee paths; checkout and
  admission version bindings; monthly exact calculation; once-per-membership fee
  budgets; pending net for unknown fees; historical snapshots preserved.
- Increment 3: source/tax/settlement readiness, read-only reconciliation, immutable
  review history and protected payout eligibility exist.
- Migration chain: **36 revisions**, one head `eb3f70126935`; actual working revision
  `d46e70ba9268`. Seven outstanding financial revisions, including the two specified
  revisions and all dependencies, were reviewed and tested. No migration file changed
  and no new migration is needed for Increment 4.
- Fresh installation passed on disposable MySQL 26.7.0.
- Populated synthetic `d46e70ba9268` upgrade passed; every existing table's row/hash
  fingerprint excluding Alembic revision matched afterward. Missing funding/evidence
  and cancelled-paid legacy rows were preserved, not “repaired.”
- Constraints, FKs, indexes, unique keys, nullable uncapped metadata and financial
  triggers inspected. Raw UPDATE/DELETE rejection verified after restore.
- Dump/restore into a second isolated schema passed with matching all-table data
  fingerprints and trigger sets. Not a production clone, PITR or failover rehearsal.
- Forward-only downgrade refusal verified. Runtime privilege separation is still
  essential: source/agreement/pin evidence is ORM-guarded, not uniformly protected by
  database triggers. DDL permissions must not be granted to runtime workers.

## 2. Existing data readiness — read only

Inventory artifacts:
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\INCREMENT4_DATA_READINESS_BEFORE.json`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\INCREMENT4_DATA_READINESS_AFTER.json`

Both used explicit consistent-snapshot READ ONLY transactions and rolled back.
They emit aggregate counts/hashes, not user identities, tokens, provider credentials
or raw transaction data. **All 55 table fingerprints matched before and after.**

| Finding | Observed result / disposition |
|---|---|
| Gyms | 39: 37 approved, 2 draft |
| Gym owners | 1 distinct owner; 0 missing owners; 0 inactive owners |
| Financial versions | 0; all 39 gyms missing own effective configuration in both test/live |
| Effective conflicts | 0 duplicate starts, invalid intervals or version/time ordering conflicts; absence is not readiness |
| Purchases | 9 PAID test checkouts: 8 CART, 1 MULTI_GYM; no live purchases observed |
| Booking status | 8: 3 cancelled, 5 confirmed; 1 marked attended |
| Funding | 8 purchases lack checkout funding; 7 cart bookings lack line funding; existing funding has 0 component mismatches |
| Checkout links | 0 bookings/memberships missing their checkout link |
| Source/tax evidence | Schema absent; no immutable source/tax evidence available for the historical purchases; unknown counts remain null |
| Admissions | 2 successful: 1 booking, 1 membership; 1 lacks QR validity window |
| Duplicate admissions | 0 duplicate successful daily-access IDs |
| Memberships | 1 paid active Multi-Gym membership; term spans months; observed visits do not span multiple gyms/months |
| Cancelled paid without credit record | 1; explicitly preserved for separate historical review |
| Financial posting/payout tables | Not deployed; no automatic historical allocations created |

These historical gaps are not safe to synthesize during migration. Preserve source
rows and quarantine financial allocation eligibility. A future data reconciliation
project needs authoritative external facts and separate adjustment approval.

## 3. Tax evidence integration findings

| Type | Actual source available | Missing integration |
|---|---|---|
| Individual | Stored booking unit/quantity/total; verified funding/payment; no-discount equality supports explicit discount zero | No authoritative purchase-tax field/invoice producer; tax remains null |
| Single-Gym | Accepted plan final price and gym; verified activation/funding | Plan/accepted terms normally have no purchase-tax evidence |
| Multi-Gym | Platform catalog base price, explicit offer discount and accepted final price | Platform response has no purchase-tax calculation/invoice evidence; absent tax remains null |

Provider `fee_tax_amount` describes tax on the gateway's fee, NOT tax on the customer
purchase. It cannot supply purchase-tax readiness. No rate/exemption/zero assumption,
price change or legal determination was introduced. Percentage allocation remains
blocked on unknown tax. Multi-Gym visit entitlement remains independent of unapproved
residual commission/statutory revenue.

## 4. Correction execution

Added a separate Admin-only POST:
`/api/v1/admin/financial-reconciliation/reviews/{case_id}/execute`.

Request requires environment, expected review revision, expected impact hash,
authorization reference, reason, explicit `authorize_execution=true`, and an
Idempotency-Key. Independent approval remains a prior action and never executes.

Supported safe subset: approved MONTH_CORRECTION whose original source is a
verified MULTI_GYM_VISIT_INVALIDATED event, with no affected active reservations,
paid claims or closed membership fee budget. Execution requires evidence/allocation
gates and the live gate for live mode. No payout gate is enabled and no transfer runs.

Executor rechecks source identity/hash, current impact against the approved snapshot,
original monthly/source links and source invalidation; locks business sources in
the existing order, uses current locking reads for financial/review rows, reuses
the existing finalizer, and atomically appends:
1. A new monthly correction revision (original retained).
2. An immutable EXECUTED review event with approver linkage, executor, authorization
   reference, reason, result ID/revision/hash and rechecked impact.

Duplicate requests return the same audit/result; changed payload/key usage blocks.
Concurrent duplicates produce one revision. Injected failure after monthly append
rolls back both the correction and execution audit, even if the caller commits.

**Not executable:** late-visit additions after finalization, closed-fee-budget
reallocation, arbitrary monetary replacement, reserved/paid recovery or bank return.
Those cases need approved algorithms and coordinated money/fee recovery; their
existing blocks remain. No broad “force execute” switch or UI auto-execute was added.

Execution was exercised only on synthetic disposable records. No existing working
review, month, purchase or payout was corrected.

## 5. Repeatable reconciliation validation

Regression fixtures cover individual, independently configured Single-Gym and
authorized no-show; gateway/wallet/split funding; discounts and known/unknown/invalid
tax; actual/missing fees; duplicate payment/scan events; refunds/cancellations;
immutable snapshots; monthly rounding and review/protected amounts.

New cross-month scenario: one membership visits Gym A at ₹30 and Gym B at ₹45 across
the November/December Asia/Kolkata boundary. Monthly gross = ₹30 (A November), ₹30
(A December), ₹90 (B December), total ₹150. Provider fee ₹2.37 is distributed once
as ₹0.60/₹0.59/₹0.59/₹0.59. Pinned fee responsibility is 0% owner for A and 50% for B:
owner fees ₹0.58, aggregate owner net ₹149.42. Collection ₹1,000 remains separately
unallocated, not FitiGo earnings. Duplicate event/fee calls preserve original IDs.

## 6. Operational controls and risks

- Added fail-closed startup validation for gate dependency combinations and missing
  schema. All gates false makes this a no-op; it never creates tables or workers.
- Both financial CLI entry points now require an explicit authorization reference,
  explicit environment and enabled prerequisite gates before opening a processing
  session. Live workers require separate live gate approval.
- API startup still starts only the pre-existing wallet recovery task; it does not
  start financial allocation, source handoff, monthly or correction schedulers.
- Source outbox leases remain fenced, expiring and retryable; allocation retries
  remain source-ID/idempotency-based. Worker failures do not rewrite posted entries.
- New inventory includes outbox status/expired lease/oldest pending and payout
  status counts when schemas exist. No automatic alert sender was configured.
- External supervisor jobs, deployment permissions, production MySQL version/grants,
  replication/PITR, monitoring alert thresholds/owners and RPO/RTO still require
  production signoff. No claim of inspecting remote production infrastructure.
- Code-only rollback requires a compatible binary with gates/workers off. Older
  consumers may not understand consolidated JSON, NULL caps, monthly budgets or
  EXECUTED review states. Prefer forward repair; do not force destructive downgrade.

Detailed backup/restoration, migration interruption, monitoring, incident response
and rollback steps are in the operations runbook. A backup alone is not proof of
restoration readiness; the disposable restore was actually performed.

## 7. Gate matrix summary

| Gate | Current | Activation prerequisites still outstanding |
|---|---|---|
| source_evidence_enabled | FALSE | Approved migration/grants/restore, consistent mutation-server release, evidence cutover and monitoring |
| marketplace_allocations_enabled | FALSE | Evidence stage signoff, gym versions, authoritative tax for percentage cohorts, monthly policy, reconciled staging scenarios, operational owner |
| marketplace_live_allocations_enabled | FALSE | Earlier checks plus production/provider acceptance, independent live reconciliation and bounded approved rollout |
| marketplace_payouts_enabled | FALSE | Validated net, complete pinned settlement policy, protected-amount review resolution, finance/payment-reference controls and explicit workflow authorization |

The operations document provides purpose, dependencies, configuration, evidence,
tests, safeguards and exact approval conditions for each gate. No automatic activation
mechanism exists. Gate-off stops future actions but never undoes committed history.

## 8. Test results and failures/reruns

Overlapping checkpoints, NOT a full backend-suite or unique-total claim:

| Checkpoint | Result | Duration |
|---|---|---:|
| Initial new migration/execution | 7 passed, 2 failed | 48.86s |
| Migration/restore rerun | 3 passed | 30.02s |
| New execution/operations/reconciliation | 24 passed | 75.35s |
| Review/payout/source regressions | 57 passed | 234.02s |
| Calculation/funding/purchase regressions | 89 passed | 296.37s |
| Enhanced restore/operations | 14 passed | 75.64s |
| Payment/refund/execution/cross-month regressions | 71 passed | 73.35s |
| Final Increment 4 migration/execution/operations/reconciliation | 26 passed | 73.88s |
| Frontend unit suite | 483 passed, 0 failures/skips | 5.14s |
| TypeScript / production build | Passed | build artifact retained |

The two initial failures were the same test-fixture DetachedInstanceError (reading a
checkout ID after session closure), fixed in the fixture. No production calculation
or migration change was needed. No test timeout occurred in this increment. One tool
returned at 300 seconds while its test process completed successfully in the
background; this is not a timeout. Existing datetime deprecation warnings remain.

## 9. Remaining business/release decisions

- Authoritative purchase-tax/invoice producer and verification ownership for all
  purchase types; no inferred tax exemption/rate.
- Actual future-dated gym settlement settings, and approval of any historical data
  reconciliation as a separate task.
- Executable policy for late additions, closed membership fee corrections and
  reserved/paid recovery. Supported invalidation execution does not imply approval
  to run it on historical or production data.
- Multi-Gym residual earnings and cross-gym collection attribution remain unapproved.
- Production target/version, deployment approval, monitoring/paging, retention and
  RPO/RTO, PITR and release rollback acceptance.

## 10. Changes in this increment

No frontend styling/pricing/customer-flow changes; no migration changes.

New files (absolute paths):
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\services\financial_deployment_readiness.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\services\financial_startup.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\scripts\financial_readiness_inventory.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\tests\test_increment4_migrations.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\tests\test_increment4_execution.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\tests\test_increment4_operations.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\tests\test_increment4_reconciliation.py`

Updated:
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\main.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\services\financial_reviews.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\schemas\financial_review.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\routers\admin_financial_readiness.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\scripts\marketplace_allocation_worker.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\scripts\source_event_worker.py`

## Final safety attestation

All **55 working-table row counts and hashes were identical** in before/after
read-only inventories. Working revision remains `d46e70ba9268`; four gates false.
No workers/schedulers, actual payments, historical financial corrections or working
database migration were run. Stop here for separate deployment/activation approval.

## Validation artifact locations

- `C:\Users\ckishor\AppData\Local\Temp\fitigo-isolated-fd67feddd2cd62aa-tid0jd6i\pytest.log` — initial fixture failures
- `C:\Users\ckishor\AppData\Local\Temp\fitigo-isolated-cf5f90955bbb01d4-9qrc1ei8\pytest.log` — migration rerun
- `C:\Users\ckishor\AppData\Local\Temp\fitigo-isolated-38d09e9382152597-upu8fpoi\pytest.log` — 24-pass readiness checkpoint
- `C:\Users\ckishor\AppData\Local\Temp\fitigo-isolated-6797a7ad2137e83c-bmlqbchl\pytest.log` — 57-pass regression
- `C:\Users\ckishor\AppData\Local\Temp\fitigo-isolated-cd715d8bf87cc76e-5ypqglh7\pytest.log` — 89-pass regression
- `C:\Users\ckishor\AppData\Local\Temp\fitigo-isolated-c71b15b9cc28ea34-2t5whqoo\pytest.log` — enhanced restore/operations
- `C:\Users\ckishor\AppData\Local\Temp\fitigo-isolated-92f1d91121ce6e75-y6dim1xz\pytest.log` — 71-pass regression
- `C:\Users\ckishor\AppData\Local\Temp\fitigo-isolated-6673403079a91d51-6wmd3o09\pytest.log` — final 26-pass run
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\increment4-tests.txt`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\increment4-build.txt`

All successful checkpoints had zero failures/skips. The final owned disposable
servers were confirmed stopped. Edited Python files passed syntax verification;
scoped tracked-file whitespace checks passed; no existing migration diff exists.
No new browser automation was claimed for this increment because UI was unchanged.