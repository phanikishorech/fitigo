# Phase 4 marketplace allocation and owner payout implementation

## Release status — not deployment approval

This work adds a practical commercial allocation ledger and manual evidenced payout
workflow, not an ERP or statutory accounting ledger. No migration was deployed to
the working database. No local commercial agreement was created/approved and no
Live processing, bank transfer, gateway payout, refund or statutory reporting was
enabled. Existing pricing, payment fulfillment and wallet balance logic are unchanged.

Pre-implementation read-only check: working revision `d46e70ba9268`, zero agreement
versions; Phase 2 pin and Phase 3 evidence/outbox tables absent; source-evidence gate
false. Working tree contains prior unrelated changes; none were reset or committed.

**Not production-ready merely because fixture allocations can be inserted.** The
source producers do not yet supply explicit immutable `transaction_basis` discount/
tax evidence for real purchases. Percentage allocation blocks those sources instead
of treating unknown tax/discount as zero. Remaining decisions/integrations below are
required before activating end-to-end processing.

## Subphases

### 4A: schema and arithmetic

- `marketplace_allocations`: immutable posted commercial entries with source event/
  evidence, checkout, transaction reference, environment, historical owner evidence,
  customer, booking/membership/visitor, agreement pin/version, exact amounts, fee
  status, calculation snapshot/hash, reversal/adjustment links, and creation time.
- Unique original purchased-unit key, source-event/unit key and idempotency key.
- MySQL checks enforce gross/fee/net/funding conservation; MySQL triggers reject
  UPDATE/DELETE, including raw SQL. ORM guards match. Privileged DB administrators
  can drop triggers; permissions/backups remain required.
- Corrections are append-only, never changes to original entries. Schema supports
  reversal/replacement, but no arbitrary Admin replacement endpoint is exposed.
- Optional `marketplace_contract` extends existing agreement JSON. Old terms and
  hashes are preserved by omitting absent optional contracts from canonical saves.
- No statutory recognition is required to configure commercial Single-Gym upfront
  entitlement; existing recognition contract remains separate and disabled.

### 4B: individual bookings

- Internal allocation adapter accepts only an existing outbox ID; no caller-supplied
  amount, environment, beneficiary or latest agreement version.
- Verifies source hash/identity, paid funding, refund state, successful visitor
  admission, authoritative token window via existing pin service, historical owner,
  approved selection instant, explicit discount/tax basis and commercial contract.
- Acquires source locks in purchaser/gym/booking/checkout order, then agreement and
  allocation locks. Savepoint rolls back partial group allocations/new pins on a block.
- Attended allocations cover only successful visitors. Unit values are partitioned
  over ALL purchased visitors, not only scanned visitors.
- Whole-booking no-show requires authorized closed-window evidence, matching
  visitor indices and no successful scans. Partial-group no-show remains blocked.
- Cancelled bookings do not create original allocations. Existing allocations can
  be fully reversed only from confirmed cancellation evidence and an explicitly
  approved original reversal policy. Existing payout reservations/adjustments require
  coordinated review rather than silently releasing paid/reserved value.
- Actual late fee evidence creates a zero-gross fee-adjustment entry linked to the
  original, with unique application. Repeated delivery does not deduct twice.

### 4C: Single-Gym

- Successful paid activation yields 85/15 gross allocation, with original purchaser,
  historical gym owner and approved pinned agreement.
- Gateway-only, modern checkout-linked wallet-only and split-funded purchases use
  existing funding/debit evidence. No second charge or fulfillment action.
- Entitlement timing is UPFRONT; actual payout remains separate and Admin-approved.
- Payout availability is immediate after validation for Single-Gym (no invented
  recognition schedule), while explicit minimum/deduction/fee-readiness settings
  remain required. Unknown fees preserve gross allocation with null net.

### 4D: Multi-Gym

- `gym_visit_payouts` records fixed verified-visit allocations, source/check-in/daily
  access/membership/holder/gym/historical owner/period/agreement references and caps.
- Unique environment/check-in AND environment/daily-access constraints prevent
  duplicate admission value, including inconsistent duplicate event imports.
- Separate approved `visit_payout_contract` does not require or approve a FitiGo
  earning formula. Fixed amount and member/gym limits reuse existing agreement fields.
- Explicit monthly timezone, platform-cap mode, cap-exhaustion rule and cap-order
  policy required. Null is not unlimited. Cap writers serialize through existing
  environment default-agreement scope lock; empty-month/platform cap races are closed.
- Monthly reports keep visit entitlement distinct from Multi-Gym collections and
  unapproved FitiGo earnings. Earnings remain null, never leftover collection value.
- Gateway-funded visit payout release remains blocked pending purchase-fee
  distribution policy across visits. The fixed visit entitlement is still recorded.
- Modern wallet-only memberships without actual gateway fee evidence may follow an
  approved monthly payout cycle. Any later actual charge requires distribution review.
- Cap priority currently supports only explicitly approved serialized processing
  order. Chronological late-arriving event repricing is not invented.

### 4E: manual owner payout workflow

- `owner_payouts`, immutable `owner_payout_items`, append-only `owner_payout_audit`.
- ACCRUED/AVAILABLE are derived from entitlement, approved schedule and evidence;
  request states are PENDING_APPROVAL, APPROVED, PROCESSING, PAID, FAILED, REVERSED.
- Single owner/gym/category/environment per request, immutable selected allocation
  reservation amounts, reasons, approved deductions, threshold/partial policy.
- Source locks and allocation locks prevent concurrent reservations exceeding net
  entitlement. Failed requests retain reservations and retry through approval.
- Every approval/process/paid transition revalidates cancellation/refund/entitlement.
- PAID requires actual matching INR amount, owner, reference, non-future date and
  protected bank/provider evidence-document reference. The server records Admin
  attestation; it does not independently validate a bank document or send funds.
- Unique environment/actual reference covers outgoing payments and returns in audit.
- Paid reversal requires distinct bank-return evidence; outgoing payment reference
  remains in history. Unpaid cancellation releases reservation; failed transfers do
  not silently release/reissue money.
- Idempotency and optimistic version checks on requests/transitions. No arbitrary
  manual monetary adjustment API and no real transfer integration.
- UI supports a single allocation request and ordinary transitions. API supports
  approved partial claims/deductions and grouped items. Paid-return recording is API
  only; a bank-return UI and provider verification are not implemented.

### 4F: existing financial screen

- Existing FinancialOverview embeds marketplace metrics/drilldowns with existing
  DataCard/MetricCard/Select/Modal/table components; no global CSS or branding edits.
- Separate commercial commissions, owner gross/net/paid/reserved, allocated actual
  gateway fees/shares, wallet liability, Multi-Gym collections and visit entitlements.
- Unknown fees or visit fee distribution make aggregate net payable unavailable,
  not false zero. Known subsets and pending counts remain visible.
- Filters: test/live, existing date range/gym/gateway plus historical owner/category.
- Allocation cohort is selected by original service/activation date. All append-only
  corrections to selected roots are included as of now; never orphan correction deltas.
- Actual payout cash/returns have their own actual payment-date scope. Settled owner
  entitlement includes approved deductions and is not confused with bank cash.
- Source-confirmed collections need actual capture timestamps; undated captures
  are separately counted. Cross-gym/gateway attribution is unavailable where not
  evidenced, not prorated by guesswork.
- Existing statutory/recognition tiles remain disabled. No financial posting in GET.
- Historical payout owner options include allocation owners no longer owning a gym.

### 4G: historical review and validation

- Read-only bounded review report: unpinned agreements, paid bookings/memberships
  without allocations, missing admission/partial group evidence, cancellation-credit
  gaps, historical owner/fee/basis gaps and inconsistent outbox/evidence identities.
- Unlinked environment sources are global unclassified counts, never assigned a mode.
- No historical repricing, adjustment execution, synthetic agreement, or source rewrite.
- Proposed historical adjustment approval/execution is intentionally not implemented;
  a reviewed immutable-evidence/authorization workflow is still required. Report
  returns `historical_adjustments_enabled=false`.

## Formulas and deterministic paise

All arithmetic uses Python Decimal with local precision 28; INR storage NUMERIC(12,2)
and gateway paise conventions remain. Float/bool, non-finite, negative input amounts
and fractional paise are rejected.

- Explicit GROSS_BEFORE_DISCOUNT: funded = price - discount.
- Explicit ALREADY_DISCOUNTED: funded = price (discount evidence is not subtracted again).
- Eligible = funded - explicitly evidenced separately collected tax.
- Wallet + gateway funding must equal funded. Missing discount or tax is blocked.
- Gym gross = eligible × approved 85% (attended/Single) or 70% (no-show), rounded using
  the explicitly approved method. FitiGo gross = eligible - gym gross, conserving paise.
- Actual provider fee INCLUDING_TAX is not taxed twice. EXCLUDING_TAX needs actual
  fee-tax evidence; missing tax keeps fee pending.
- Split actual checkout fee 50/50 ONCE. Odd paise assigned to explicitly configured
  GYM_OWNER or FITIGO. Each party's amount is partitioned across gateway-funded
  cart lines/visitors using integer largest-remainder with stable source-order ties.
- Gym net = gym gross - its assigned actual fee. FitiGo net = gross - its assigned fee.
  Negative results remain review-required, not clamped or paid.
- Unknown gateway fee leaves gross valid and both nets null. Explicit fee-before-payout
  policy is REQUIRED or ALLOW_PROVISIONAL_GROSS; no default. Provisional payout with
  later fee evidence and an existing reservation requires coordinated review.
- Wallet-only fee is zero without actual external fee evidence. Wallet topups are
  collection/liability evidence, never commission revenue.

## New migrations (not deployed locally)

1. `a79ba3ed2591` after `f68a92dc1480`: marketplace_allocations.
2. `b80cb4fe3602` after `a79ba3ed2591`: gym_visit_payouts.
3. `c91dc50f4713` after `b80cb4fe3602`: owner_payouts/items/audit.

Downgrade refuses populated financial evidence. Parent migration regression tests
now use correct child-before-parent order. Application startup does not migrate.

## API and worker

Existing ADMIN/SUPER_ADMIN authorization:

- GET `/api/v1/admin/marketplace/financial-summary`
- GET `/api/v1/admin/marketplace/historical-review`
- GET/POST `/api/v1/admin/marketplace/payouts`
- GET `/api/v1/admin/marketplace/payouts/{id}?mode=test|live`
- POST `/api/v1/admin/marketplace/payouts/{id}/transition`

Mutation requests require Idempotency-Key; transitions also expected_version. Money
is returned as decimal strings. Responses no-store. Statutory reporting always false.

Explicit-ID internal CLI: `marketplace_allocation_worker.py --mode test --event-id UUID`.
It does not scan/reprice history, send payments or start automatically. Safe repeats
return existing allocation IDs. Source outbox remains durable; no Phase 3 identity
is rewritten to fabricate a binding. Allocation/visit records FK the actual pin.
There is no automatically scheduled continuous allocation consumer in this release.

## Known deployment blockers / remaining decisions

1. Publish NEW effective agreements with explicit commercial basis, residual/rounding,
   fee readiness/distribution and approved independent selection instants. Business
   approval of percentages does not authorize selecting purchase versus service time.
2. Add authoritative source-producer discount/tax facts (`transaction_basis`) without
   changing customer pricing. Existing historical records remain blocked; no invented
   zero tax/discount or backfill from today's policy.
3. Confirm booking settlement day/time/timezone, holding, minimum, deductions and partial
   handling. Single upfront entitlement is separate from CA statutory recognition.
4. Approve Multi-Gym purchase-fee distribution, platform-cap scope/order and unused
   value/earning formula. No remaining collection amount is treated as revenue.
5. Gateway settlement date/reference import remains Phase 3 contract-only. Actual
   fee evidence is consumed where available; a verified settlement importer has not
   been implemented. Unavailable fees remain null.
6. Legacy wallet-only memberships with no trusted PaymentCheckout remain blocked by
   existing pin design; modern wallet-only/split checkout paths are supported.
7. Known-fee changes, reversal of already-adjusted/paid claims, partial refunds,
   replacement entries and historical adjustment execution require coordinated
   review; not silently automated. First late missing fee and full uncomplicated
   cancellation reversals are implemented/tested.
8. Reporting currently aggregates selected rows in memory with bounded drill-down
   output. Large-volume SQL aggregation/paging optimization remains before scale-out.
9. Bank evidence is Admin-attested metadata/document reference, not an automated
   statement verification system. Protect referenced documents and audit permissions.

## Deployment / rollback plan

No local deployment is authorized or performed. After separate approval:

1. Backup and inventory pending migrations from actual deployed revision.
2. Apply Phase 2/3 parents and the three Phase 4 migrations in order on staging first.
   Verify MySQL triggers, unique constraints and restoration procedures.
3. Deploy with SOURCE_EVIDENCE_ENABLED, MARKETPLACE_ALLOCATIONS_ENABLED,
   MARKETPLACE_LIVE_ALLOCATIONS_ENABLED and MARKETPLACE_PAYOUTS_ENABLED all off.
4. Complete policy/source blockers, then enable evidence capture consistently across
   all mutation instances at a documented cutover. Do not silently fill earlier gaps.
5. Enable test allocations only; explicitly process sample event IDs and reconcile
   source funding, original-unit uniqueness, fee totals, owner net and dashboard.
6. Separately approve manual payout workflow and any Live gate. No provider payout
   integration is implied. CA statutory reporting remains disabled.
7. Roll back code/gates without deleting financial records. Gate changes create
   documented processing/evidence gaps; populated schema downgrade is refused.

## Validation results

Validation checkpoints (all backend runs use the disposable MySQL runner and mocked
providers; no working database migrations or financial writes):

- 4A calculation/schema/agreement checkpoint: **134 passed**.
- 4B fee-conservation/correction/concurrency checkpoint: **61 passed**.
- 4C/4D/4E were advanced only after their isolated financial tests passed.
- Broad financial/API run: **83 passed**, including ledger invariants, partial visitors,
  wallet/gateway/split Single-Gym, visit caps, approval/paid distinctions, payout
  reservations, bank returns, cancellation/refund revalidation, APIs and report totals.
- Final source/migration/policy/report/visit regression rerun: **146 passed**.
- Last current-code booking/membership/correction/payout/report/API rerun:
  **27 passed**, after the final fee/source validation guards.
- Full backend checkpoint: **1,110 passed, 1 failed**. Failure was a preexisting
  missing-schema test dropping gym_owner_evidence before its new child FK tables.
  Fixture was corrected to use child-first migration order and passed in the 146-test
  rerun. A wholly green full-suite rerun after every final change is NOT claimed.
- One larger combined run reached its 900-second timeout before completion and is
  explicitly incomplete, not counted as passed. Subsequent focused runs completed.
- Frontend: **472 passed**, TypeScript no-emit passed, production Vite build passed.
- Mocked financial browser: existing dashboard/analytics/reports, unknown values,
  filters/CSV/error states and widths 360/768/1440 passed.
- Mocked agreement browser: proposal/edit/validation/review/save/history passed.
- Mocked payout browser: request, approval, processing, actual-payment evidence
  entry and recorded reference passed; all writes intercepted.
- CLI --help, documented-file existence and Python AST validation passed.
- Existing datetime.utcnow deprecation warnings remain.

Final read-only working-state verification: `d46e70ba9268`, zero agreement versions;
source evidence and all new allocation/visit/payout tables absent; evidence,
allocation, Live allocation and payout gates all false. Source migration head is
`c91dc50f4713`, not the deployed revision.

Do not interpret fixture calculations or migration-only success as full production
readiness. Source basis/settlement import/historical execution gaps above remain.

Additional correctness boundaries: paid returns with deductions require separate
withholding/adjustment-return review. Member/gym visit limits use customer identity
at admission (not a fresh allowance per renewal); explicit per-membership platform
caps remain a separate policy. These choices are preserved in allocation snapshots.

## Changed-file inventory

New core files:

- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\models\marketplace_allocation.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\models\gym_visit_payout.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\models\owner_payout.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\schemas\marketplace_allocation.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\schemas\owner_payout.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\services\marketplace_calculation.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\services\marketplace_allocations.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\services\marketplace_corrections.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\services\gym_visit_payouts.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\services\owner_payouts.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\services\marketplace_reporting.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\services\marketplace_reconciliation.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\routers\admin_marketplace.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\scripts\marketplace_allocation_worker.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\alembic\versions\a79ba3ed2591_marketplace_allocation.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\alembic\versions\b80cb4fe3602_gym_visit_payouts.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\alembic\versions\c91dc50f4713_owner_payout_workflow.py`

Existing backend registration/configuration and agreements extended in place:

- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\core\config.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\models\__init__.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\schemas\financial_agreement.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\services\financial_agreements.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\services\accounting_policy.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\routers\admin.py`

Frontend changes (existing screen/theme, no global CSS):

- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\admin\MarketplaceFinancials.tsx`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\admin\HistoricalFinancialReview.tsx`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\admin\marketplaceService.ts`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\admin\FinancialOverview.tsx`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\admin\RevenueSharingSettings.tsx`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\admin\agreementService.ts`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\scripts\marketplace.test.mjs`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\scripts\admin-financial-browser.mjs`

New tests and migration-test helper:

- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\tests\test_marketplace_calculation.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\tests\test_marketplace_allocation_mysql.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\tests\test_marketplace_booking_mysql.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\tests\test_marketplace_membership_mysql.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\tests\test_gym_visit_payout_mysql.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\tests\test_owner_payout_workflow_mysql.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\tests\test_marketplace_reporting_mysql.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\tests\test_marketplace_api_mysql.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\tests\allocation_migration_helper.py`

Existing migration regression fixtures updated for child FK order and optional hash fields:

- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\tests\test_financial_agreements.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\tests\test_agreement_selection_contract.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\tests\test_source_evidence_mysql.py`