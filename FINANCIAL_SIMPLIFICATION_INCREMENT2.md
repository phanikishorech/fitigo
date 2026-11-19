# Increment 2 — gym-specific calculation integration

## Delivery boundary

Code and tests implemented. **Not deployed or activated.** No working database
records, historical financial adjustments, production workers, flags or payouts
were changed. Tests used disposable MySQL servers and mocked payment providers.

Final read-only working database check: revision `d46e70ba9268`, 2 proposal scopes,
0 agreement versions, no `gym_monthly_calculations` table. All four gates false:
`source_evidence_enabled`, `marketplace_allocations_enabled`,
`marketplace_live_allocations_enabled`, `marketplace_payouts_enabled`.

## Approved policy implemented

The user explicitly approved checkout-time percentage selection; admission-time
Multi-Gym selection; Asia/Kolkata months; exact monthly accumulation and HALF_UP
once at the gym/month total; deterministic paise attribution; membership-complete
fee attribution once per provider payment; append-only invalidations; and review
for changes affecting reserved/paid money. No leftover-collection commission.

### Individual, Single-Gym, authorized no-show

- New checkout creation captures the gym's own effective version ID, version,
  terms hash, selection timestamp and environment in its snapshot and, when the
  evidence gate is enabled, in immutable purchase evidence. Missing settings are
  recorded as a blocker and do not fail customer payment merely for commercial
  configuration absence. No shared-default or other-gym fallback.
- Existing `FinancialAgreementPin` is reused when allocating the source; no new
  settings table or duplicate financial calculator was introduced.
- Individual uses `individual.revenue/gateway_fee`; Single-Gym uses
  `single_gym.revenue/gateway_fee`; explicitly authorized no-show uses
  `no_show.revenue/gateway_fee` from the checkout-pinned version.
- Single-Gym still allocates upfront on verified activation/purchase, without
  changing activation/access. Purchased gym, purchaser, paid funding and activation
  source are checked. Booking allocations verify visitor, QR window and outcome.
- Authorized closed-window whole-booking no-show checks remain. No scan absence
  alone creates a no-show entitlement.
- Removed calculator hardcoded 85/15 and 70/30 comparison and approved-agreement
  validation enforcing those fixed rates. Existing completed rows are not rerun.
- Snapshots retain exact revenue/fee percentages, full terms/hash, source/pin IDs,
  funding, gross/net, actual fee reference and deterministic partition context.

### Gateway fees

- Provider-confirmed authenticated evidence remains authoritative; included fee
  tax is not added twice. Missing/ambiguous fees do not become zero.
- For consolidated carts: allocate the actual checkout fee to lines by gateway
  funding using largest-remainder paise first, then split each line using its gym
  and outcome-specific fee percentages, then distribute to purchased visitors.
  This permits different gyms' fee responsibility without duplicating checkout fees.
- Wallet-only lines have zero gateway weight; contradictory positive fees block.
- Existing append-only late-fee corrections reuse the original saved percentages
  and line/visitor partition. Original gross snapshots remain untouched.
- Full cancellation reversal remains source-backed and blocks reserved claims;
  original gross and fee contributions are negated once. Existing provider refund
  and split-refund review behavior remains protected by regression tests.

## Purchase evidence and funding

Purchase producer now writes transaction type/source, gym/owner observation,
currency/environment, gross price representation, purchase amount, discount/tax
facts or explicit unknowns, wallet/gateway portions and commercial version binding.

**Important remaining source limitation:** booking pricing has no authoritative tax
field, and Single-Gym accepted terms also normally lack one. Their tax is stored
as null / `SOURCE_NOT_SUPPORTED`, not zero. Such percentage allocation is blocked
until authoritative tax evidence exists. Booking zero discount is recorded only
when unit-price × quantity equals the stored purchase total in the no-discount
pricing path. Platform membership base/discount facts come from accepted terms.
No customer price, tax or discount was invented or changed.

Gateway-only purchases now create `CheckoutFunding` and per-booking
`BookingFunding` records on the new purchase path, including current-cart calls
without wallet selection. `PaymentCheckout.amount` remains **gateway amount**;
total consideration remains in funding. Existing purchases are not backfilled.

Regression found that three recovery branches historically used funding-row
existence as a wallet indicator. They now check `wallet_amount > 0`, preserving
gateway-only late-capture recording and preventing cancelled memberships from
reactivating. Wallet hold/debit/release and recovery tests pass after this fix.

## Multi-Gym monthly calculation

`allocate_visit` retains the existing admission/daily-access/token, owner, funding,
environment and duplicate checks. New admissions preserve their own gym version.
Consolidated visit rows have no cap (`applied_cap = NULL`) and explicit pending
monthly status; their monetary values are not reported as finalized zero earnings.

`finalize_month` in the existing visit service:

1. Requires processing gates, closed Asia/Kolkata calendar month and reconciled
   successful admissions/allocated visits for that gym/month.
2. Uses each admission's immutable reference amount/divisor, sums exact rational
   values, applies HALF_UP once to the total, then assigns paise by largest remainder
   with stable admission-time/check-in ordering.
3. Appends an immutable monthly calculation; repeats return the existing result.
   Concurrent finalizers use current locking reads under MySQL repeatable-read.
4. Late visits after finalization block for explicit review, not silent repricing.

Examples verified in pure arithmetic and disposable-MySQL end-to-end tests:

| Reference | Eligible visits | Monthly gross |
|---|---:|---:|
| ₹3,000 / 100 | 50 | ₹1,500 |
| ₹3,000 / 100 | 100 | ₹3,000 |
| ₹3,000 / 100 | 160 | ₹4,800 |
| ₹3,000 / 100 | 200 | ₹6,000 |

Different configuration versions within a month retain their respective rates.
Example: one ₹30 visit plus two ₹40 visits finalizes at ₹110. Different gyms never
share a monthly calculation. No arbitrary caps or platform-earnings formula added.

`attribute_membership_fee` requires the membership to have ended, all its eligible
visits/months to reconcile and finalize, and actual provider fee evidence. It stores
one unique budget per checkout, distributes the fee equally in deterministic paise
across eligible visits, then uses each admission's pinned fee percentages. Unknown
fee or incomplete attribution leaves net pending. No eligible visits means the fee
stays unallocated; it is not charged to nonexistent visits.

`monthly_position` projects gross/net from immutable completion and fee evidence.
FitiGo's fee contribution does **not** reduce the owner's configured gross payout;
only the owner's assigned fee reduces owner net. FitiGo earnings stay null and
collections remain separately reported.

### Corrections

`source_evidence.invalidated_multi_gym_visit` records Admin-authorized evidence for
an admission already rejected by its source workflow; it does not change access.
`finalize_month(... correction_evidence_id=..., actor_id=...)` verifies the original
evidence link/hash, appends a revision, and leaves the original finalization intact.
Changes affecting any reserved/paid allocation in the month block for coordinated
review. A closed membership fee budget also blocks invalidation pending coordinated
fee reallocation review. This increment does not automate those review resolutions.

## Migration

One new forward-only revision: `da2e6f105824` after `c91dc50f4713`.

- Makes existing visit `applied_cap` nullable for explicitly uncapped new records.
- Adds append-only `gym_monthly_calculations` with unique gym/mode/month/revision.
- Adds append-only `membership_visit_fees` with unique checkout fee budget.
- Adds MySQL UPDATE/DELETE rejection triggers. Downgrade refuses history removal.
- No data seed, backfill, configuration edit or gate activation.

Existing migrations were not edited. The new chain was applied only to disposable
test schemas; actual table/unique constraint/trigger metadata was checked.

## Files modified/added

All paths below are under the absolute workspace
`C:\Users\ckishor\.cline\data\workspaces\chat\fitigo`.

Backend services: `marketplace_calculation.py`, `marketplace_allocations.py`,
`gym_visit_payouts.py`, `agreement_selection.py`, `gym_financial_settings.py`,
`source_evidence.py`, `checkout_funding.py`, `payment_checkout_service.py`,
`marketplace_corrections.py`, `marketplace_reporting.py`, `owner_payouts.py`,
`accounting_policy.py`, all in the workspace's `backend\app\services` directory.

Schemas: `backend\app\schemas\gym_financial_settings.py`,
`backend\app\schemas\financial_agreement.py`.
Model: `backend\app\models\gym_visit_payout.py`.
Migration: `backend\alembic\versions\da2e6f105824_monthly_visit_completion.py`.

Frontend: `frontend\src\admin\FinancialSettings.tsx`,
`frontend\src\admin\gymFinancialSettingsService.ts`,
`frontend\src\admin\marketplaceService.ts`. Only policy text/types and an explicit
new-version adoption action changed; no redesign or global CSS changes.

Tests: new `backend\tests\test_increment2_calculation.py`,
`backend\tests\test_increment2_mysql.py`,
`backend\tests\test_increment2_purchase_evidence.py`,
`backend\tests\test_increment2_migration.py`; updated existing calculator/settings
expectations, legacy visit fixture, and empty-fixture child-migration teardown helper.

## Validation checkpoints

These overlap; do not add them as a unique total. No full backend suite claim.

- First focused run: **79 passed, 1 failed** (old test expected charging a gateway
  fee to wallet-only funding; expectation updated to required reconciliation block).
- Early combined run: **159 passed, 4 failed** (legacy cap fixtures incorrectly
  generated new-format admission evidence; fixed as explicit historical fixtures).
- Expanded early new tests: **19 passed, 2 failed** (one partial-attendance fixture
  expectation and a real repeatable-read finalization race, both corrected).
- Focused rerun: **30 passed**, 215.75s.
- Financial/configuration regression: **196 passed**, 1190.71s, within 1200s limit.
- Monthly volume/migration checkpoint: **26 passed**, 254.16s.
- Payment/access initial regression: **147 passed, 3 failed**; recovery conditions
  fixed to distinguish wallet contribution from gateway-only funding records.
- Payment/access rerun: **150 passed**, 518.90s.
- Additional correction/version/cancellation checks: **3 passed, 15 deselected**.
- Core financial final checkpoint: **106 passed**, 238.01s.
- Final targeted isolation/concurrency selection: **4 passed, 20 deselected**, 18.66s.
- Final complete visit/reporting/Increment 2 MySQL files after the last safety
  guard: **27 passed**, zero failures/skips, 106.20s.
- Frontend: **477 passed**, zero failures/skips; TypeScript and production build pass.
- No test-runner timeout occurred. Several tool calls yielded after 300 seconds
  while tests continued; these are not timeouts. Existing deprecation warnings remain.

## Remaining gaps / next increment

1. Add authoritative purchase-tax source facts without repricing or retrospectively
   labeling unknown tax as zero. Current unknown-tax percentage sources stay blocked.
2. Complete settlement cutoff/timezone/holding/deduction/partial/failed payout
   configuration. New-format payouts explicitly block rather than borrow statutory
   legacy settlement policy. Manual payout reservations/audits were retained.
3. Approve and integrate operational scheduling for monthly completion and
   membership-complete fee attribution. Internal services are implemented; no worker
   was enabled and no automatic payment/GET allocation trigger added.
4. Add coordinated review resolution for late visits after month finalization and
   invalidations after fee budgets close or amounts become reserved/paid. They
   currently fail closed, retaining original evidence.
5. Legacy development wallet-only memberships without a PaymentCheckout remain
   unsupported by the existing allocation adapter; do not fabricate checkouts or
   backfill their financial records.
6. Existing Increment 1 versions with null monthly policies remain unchanged and
   block monthly calculation. Admin can explicitly adopt the approved protocol in
   a future version. New-gym default versions use the approved monthly protocol.
7. Finish activation/deployment review before any migration or gate change. This
   report does not authorize production processing or actual payouts.

## Principal validation logs

- Financial/configuration 196-pass run:
  `C:\Users\ckishor\AppData\Local\Temp\fitigo-isolated-bc14c86f9ff9a9c2-6j2634ay\pytest.log`
- Payment/access 150-pass rerun:
  `C:\Users\ckishor\AppData\Local\Temp\fitigo-isolated-d44d72c237b05945-bs0ae8_1\pytest.log`
- Core financial 106-pass rerun:
  `C:\Users\ckishor\AppData\Local\Temp\fitigo-isolated-54771b638456df78-gb7rnh8j\pytest.log`
- Final visit/reporting 27-pass run:
  `C:\Users\ckishor\AppData\Local\Temp\fitigo-isolated-27e4a6906dbdcab2-o93zs1bg\pytest.log`
- Frontend unit/build:
  `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\increment2-tests.txt`
  `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\increment2-build.txt`

Every disposable test server was stopped by its runner. Scoped tracked-file diff
checks and Python syntax checks passed. No production browser writes were used;
this increment's frontend validation is unit tests/typecheck/build, not a new
browser-automation claim.