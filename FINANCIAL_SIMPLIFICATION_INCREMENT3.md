# Increment 3 — Financial readiness, reconciliation and review controls

## Status and boundaries

Implemented and tested without deployment or financial activation. Both previous
handoffs were read, then checked against actual schemas, producers, allocation,
monthly finalization, fee budgets, payout logic, routing and tests.

Read-only working database verification: revision `d46e70ba9268`, two agreement
proposal scopes, zero agreement versions. Source evidence, monthly calculations,
review events and owner payout tables remain absent. No application data or
configuration was written to the working database.

All four gates remain false: `source_evidence_enabled`,
`marketplace_allocations_enabled`, `marketplace_live_allocations_enabled`,
`marketplace_payouts_enabled`. No scheduler/worker was started, no actual payout
initiated, no historical financial adjustment performed, and no pricing changed.

## Implemented functionality

### Tax/source readiness

- Shared purchase-basis readiness classifies UNKNOWN, CONFIRMED_ZERO,
  CONFIRMED_NONZERO and INVALID; null is never converted to zero.
- Only immutable BOOKING_PURCHASE_RECORDED / MEMBERSHIP_PURCHASE_RECORDED facts
  are considered purchase-tax evidence. Provider fee-tax is not customer tax.
- Checks source verification/hash, exact nonnegative paise, currency, price
  representation, explicit discount, and tax/discount consistency with price.
- Percentage allocation now invokes this same check. Original purchase/allocation
  snapshots are never updated.
- Admin tax/source report includes missing purchase evidence, ambiguous sources,
  booking outcome, payment status, tax status, blockers and original evidence IDs.

**Source finding:** the booking model still has no authoritative purchase-tax field;
Single-Gym accepted terms normally do not provide tax either. The producer correctly
leaves those values unknown. This increment does not invent a rate, statutory
classification, tax exemption, invoice authority, or an Admin tax override.
Confirmed zero/nonzero are supported when explicitly evidenced by the purchase
source; missing-tax production records remain blocked.

### Versioned settlement policy

Extended the existing `financial_settings.settlements` object, not a new overlapping
configuration table. Admin changes retain the existing future-only version, actor,
reason, optimistic concurrency and immutable history.

Explicit nullable fields: cutoff time/timezone, weekly day, monthly day,
short-month treatment, holding days, Single-Gym cycle, permitted deductions,
verified-net/undisputed eligibility, partial-settlement treatment and failed-payment
treatment. Existing booking/Multi-Gym cycle and minimum payout fields are retained.

No new business defaults are supplied. Empty deduction list explicitly means none;
null means unconfigured. Gateway fees cannot appear as a second manual deduction.
Only evidenced withholding / approved source adjustment types are selectable;
no withholding rate is assumed.

Payout availability reads the **original pinned gym version**, never current
settings. A later holding-policy version cannot reprice or change old eligibility.
Upfront Single-Gym entitlement is retained; settlement holding days still apply.
Weekly/monthly Single-Gym settlement no longer takes the legacy upfront shortcut.
Multi-Gym uses finalized monthly net and membership fee evidence, with refund,
invalidated-admission, configuration-integrity and actual-fee-budget checks.

Old versions with missing settlement policy stay blocked. Optional null additions
are excluded from the new request-hash canonicalization to preserve earlier retry
keys. No existing configuration versions were updated.

### Admin Financial Reconciliation

Dedicated Admin-only route `/admin/financial-reconciliation`, using existing cards,
tabs, forms, modal, typography, colors and agreement CSS. No global CSS changes.

Separate views: Individual, Single-Gym, authorized no-show, Multi-Gym months,
gateway fees, tax/source evidence, collections, payout balances and corrections.
Every amount is accompanied by underlying source/allocation/configuration/payout
references. Immutable source/allocation/month/fee-budget snapshots can be inspected
through environment-isolated read-only detail endpoints with hash validation.

The dashboard displays current-page totals explicitly, not fabricated all-time
totals. Unknown components make the corresponding total unknown. It shows monthly
revision history separately; revisions must not be added together.

### Reconciliation formulas and scope

- Eligible percentage basis = evidenced after-discount price minus purchase tax.
- Gym gross + FitiGo gross = eligible basis.
- Wallet funding + gateway funding = customer consideration.
- Gym fee + FitiGo fee = actual attributed provider fee.
- Net owner entitlement = gym gross minus owner fee contribution.
- Monthly visit gross = existing exact admission-pinned volume formula, HALF_UP
  once per gym/month, with deterministic paise allocation (unchanged).
- Membership fee portions sum to the single provider-confirmed membership fee;
  each portion's owner/platform contributions must reconcile.
- Unattributed provider fee = actual fee minus signed allocation fee entries and
  closed membership fee budget. Negative amounts are differences, not clamped.
- Non-Multi-Gym unallocated consideration = verified consideration minus signed
  allocated customer basis. Multi-Gym collections remain separately unallocated
  because no commercial residual-earnings formula exists. Visit costs are NOT
  subtracted to invent FitiGo revenue.
- Payout items must sum to entitlement; net payout + deductions = entitlement.
- Reserved, approved-not-paid, pending-approval and actual-paid are separate.
  Approved and pending are subsets of reservations, not additive to reservations.
- Cart/fee collection rows remain checkout-wide when gym-filtered and are clearly
  labeled not gym-prorated. Cross-gym Multi-Gym collections are not assigned to a
  gym without a collection-attribution policy.

### Correction review controls

New append-only review events support LATE_VISIT, MONTH_CORRECTION,
CLOSED_FEE_BUDGET and RESERVED_OR_PAID cases. Each requires verified original source
evidence, gym/environment identity and a reason. Server-derived impact records
include affected allocations, month revisions, closed fee budgets and payout
claims. Duplicate opens, stale revisions and mismatched idempotency keys block.

Decisions: NEEDS_EVIDENCE, REJECTED, APPROVED_FOR_RECONCILIATION. Approval requires
a different Admin from the proposer. Reserved/paid impact requires explicit
acknowledgment; all decisions require acknowledgment that they execute nothing.
Impact hashes require refreshing when affected records change.

Review approval does not rewrite finalized records, reopen fee budgets, release
reservations, execute adjustments or activate processing. Open/needs-evidence/
approved-for-reconciliation reviews block affected payout eligibility. Rejected
reviews release only this review blocker, not underlying allocation safeguards.
Original reserved/paid and closed-budget correction blocks remain intact.

**Execution boundary:** this is the requested controlled review stage, not an
automated financial adjustment engine. Executing approved late-visit or closed-fee
budget reallocation and resolving paid-money recoveries remain separately gated
future work; no existing history was adjusted in this increment.

### Activation controls

Read-only runtime gate values, required-table readiness, evidence/settlement/review
checklist, and explicit `activation_authorized=false`. There is no activation toggle,
gate-mutation endpoint, worker starter or bank-transfer call. Schema-ready does not
mean evidence-ready or approved to process.

## Migration

New forward-only revision `eb3f70126935`, parent `da2e6f105824`:

- Creates `financial_review_events` with case/revision and mode/request uniqueness.
- Stores actor/reason, source FK, immutable impact snapshot/hash and previous-event
  linkage in the snapshot.
- MySQL UPDATE/DELETE rejection triggers and ORM append-only guards.
- No seeds, backfills, financial adjustments or gate changes; downgrade refuses.

Existing migrations unchanged. Applied only to disposable MySQL. Repository head
is `eb3f70126935`; working database remains `d46e70ba9268`.

## Modified files

Workspace: `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo`.

New backend files:
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\services\financial_readiness.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\services\commercial_settlement.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\services\financial_reviews.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\models\financial_review.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\schemas\financial_review.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\routers\admin_financial_readiness.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\alembic\versions\eb3f70126935_financial_review_controls.py`

Updated backend files:
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\schemas\gym_financial_settings.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\services\gym_financial_settings.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\services\owner_payouts.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\services\marketplace_allocations.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\models\__init__.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\routers\admin.py`

Frontend additions/updates:
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\admin\FinancialReconciliation.tsx`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\admin\reconciliationService.ts`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\admin\SettlementSettingsEditor.tsx`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\admin\FinancialSettings.tsx`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\admin\gymFinancialSettingsService.ts`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\admin\AdminApp.tsx`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\admin\AdminLayout.tsx`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\admin\routes.ts`

Tests:
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\tests\test_increment3_readiness.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\tests\test_increment3_mysql.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\tests\allocation_migration_helper.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\tests\test_increment2_migration.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\scripts\reconciliation.test.mjs`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\scripts\reconciliation-browser.mjs`

The migration helper change is empty-fixture teardown only, not a production
downgrade. Existing payment/QR/customer mutation implementations were not edited.

## Validation results

Overlapping checkpoints; not a sum of unique tests or a complete backend-suite claim.

| Run | Result | Duration |
|---|---|---:|
| Initial new-feature tests | 24 passed | 126.08s |
| Expanded new-feature tests | 30 passed | 163.88s |
| Combined regression | TimeoutExpired at 900s; incomplete, not green | 900s bound |
| Monthly/evidence/migration regression | 83 passed | 804.92s |
| Settings/agreement regression | 72 passed | 625.64s |
| Allocation/payout/reporting/API regression | 27 passed | 370.46s |
| Expanded final features before clock fix | 33 passed, 1 failed | 121.28s |
| Final features + owner payout regression | 41 passed | 174.29s |
| Final report-integrity targeted rerun | 3 passed, 14 deselected | 12.16s |
| Frontend unit suite | 483 passed, zero failures/skips | see artifact |
| TypeScript and production build | Passed | see artifact |

The one backend failure identified differing evaluation clocks between payout
service and commercial helper. Fixed by passing the payout service's evaluation
time into the helper; final 41-pass rerun includes it.

Browser test initially failed due to a test selector (`Close` versus the existing
`Close dialog` accessible label). Corrected test and reran successfully: all views,
unknown amounts, disabled activation, immutable-source drill-down and 360/768/1440
layouts, all API calls mocked and zero mutations.

One actual test-runner timeout occurred. The tool's other 300-second yields were
background continuation, not timeouts. Disposable servers were stopped by their
runners. Existing datetime deprecation warnings remain.

## Unresolved decisions / next steps

1. Choose an authoritative purchase-tax producer/invoice integration and verification
   process. Do not treat current missing tax as exemption/zero or backfill history.
2. Admins must explicitly configure gym settlement values in future versions; none
   of the new cutoff/holding/deduction choices were activated in working data.
3. Design separately approved execution for reviewed late visits, fee-budget
   replacements and reserved/paid recovery. Approval records alone cannot do this.
4. Multi-Gym residual earnings and cross-gym collection attribution remain unapproved.
5. Activation/deployment and worker scheduling require separate explicit approval.
6. Reconciliation currently exposes paginated record/page totals and evidence
   drill-down, not an all-time export or statutory report.

## Validation artifacts

- `C:\Users\ckishor\AppData\Local\Temp\fitigo-isolated-4851f02acb97e914-8nroo9pj\pytest.log` — 24 passed
- `C:\Users\ckishor\AppData\Local\Temp\fitigo-isolated-689ec6260cecd1c8-lxacq9h2\pytest.log` — 30 passed
- `C:\Users\ckishor\AppData\Local\Temp\fitigo-isolated-63cb3511c9357344-wyn5unox\pytest.log` — incomplete timed-out run
- `C:\Users\ckishor\AppData\Local\Temp\fitigo-isolated-6c9e075b52e5f3c2-21y4uu2p\pytest.log` — 83 passed
- `C:\Users\ckishor\AppData\Local\Temp\fitigo-isolated-24bfc20557b298c6-7gp6rm5q\pytest.log` — 72 passed
- `C:\Users\ckishor\AppData\Local\Temp\fitigo-isolated-bf25b689b4a19161-fsa7nm1i\pytest.log` — 27 passed
- `C:\Users\ckishor\AppData\Local\Temp\fitigo-isolated-b6ad93c46cdfb3b9-xrtf3ah7\pytest.log` — 33 passed / 1 failed before clock fix
- `C:\Users\ckishor\AppData\Local\Temp\fitigo-isolated-deacabfc1988bfb7-r0_h2hlb\pytest.log` — 41 passed final feature/payout run
- `C:\Users\ckishor\AppData\Local\Temp\fitigo-isolated-548c642438ccc69c-0qd96ud8\pytest.log` — final targeted 3 passed
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\increment3-tests.txt`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\increment3-build.txt`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\increment3-browser.txt`

Final edited Python files passed syntax verification; scoped tracked-file whitespace
checks passed. Existing migrations have no edits. All completed backend runs had
zero skips; the targeted last run deliberately deselected 14 unrelated tests.