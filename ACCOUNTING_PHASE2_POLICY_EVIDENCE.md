# Phase 2 — policy and evidence contract

## Scope and release boundary

This phase extends the existing versioned agreement subsystem. It does **not**
calculate commission, recognize revenue, post journals, create payable/settlement
records, invoke payment providers, change customer balances or alter QR behavior.
There is no automatic posting switch. `posting_enabled`, `posting_eligible` and
`statutory_reporting_enabled` remain false, even for fully configured policies.

Working database migration/settings have not been changed. Existing local source
reload may expose the additive editor, but the new pin table is not deployed locally.
No real agreement or source pin was created as part of testing.

## Existing agreement compatibility

- Reuses `financial_agreement_scopes`, `financial_agreement_versions`, their current
  primary keys, effective dates, immutable history, scope locks, optimistic version,
  actor/reason/CA references, and idempotency controls.
- The actual existing model is `FinancialAgreementVersion` (not a separate model
  named `FinancialAgreement`). No parallel agreement subsystem was introduced.
- Adds optional `terms.policy_contract`. Absent/null means **legacy contract v1**;
  an included contract has explicit `contract_version: 2`.
- Old JSON rows, proposals and request hashes are not rewritten. Canonical save
  removes absent/null policy_contract to preserve the old hash and stored shape.
  Existing retry keys keep working. New non-null policies are included in the hash.
- New policies use the same future-only version creation path. No editing existing
  terms, automatic approval, inherited approval from CA reference, or backdated save.
- Read-time schema/catalog defaults describe technical representation and unknown
  state only. Commercial choices are null, not invented values. Explicit zero and
  empty deductions differ from missing values.
- A later version supplies a complete snapshot, not a patch applied to old versions.

## Policy v2 layout

Existing top-level `attended`, `no_show`, `single_gym` percentages and `multi_gym`
rate/member-gym limits remain authoritative. Existing settlement frequencies and
threshold remain authoritative. They are not duplicated in the new contract.

Every new policy section contains its own approval:

```json
{"approval":{"status":"AWAITING_APPROVAL","reference":null}}
```

`APPROVED` requires an explicit reference. This records an administrator's policy
attestation, not independent CA verification. Approving an incomplete section is
rejected when saving/validating `AgreementTerms`. A completed configuration does
not assert that source evidence or an executable calculator exists.

### Monetary

| Field | Allowed choices / meaning |
|---|---|
| currency/storage_scale/provider_unit | INR / 2 / PAISE: existing technical convention |
| calculation_precision | 28 significant digits: technical Decimal precision; does not choose rounding |
| rounding | HALF_UP, HALF_EVEN, DOWN, or unset |
| rounding_stage | PER_VISITOR, PER_BOOKING, PER_ALLOCATION, or unset |
| residual_paise | LARGEST_REMAINDER_VISITOR_INDEX, FINAL_VISITOR, REQUIRE_EXACT, or unset |
| discount_allocation | PROPORTIONAL_UNIT_PRICE, EXPLICIT_SOURCE_LINES, or unset |
| tax_treatment | EXCLUDE_SEPARATELY_COLLECTED_TAX, or unset |
| partial_refund | REVERSE_ORIGINAL_ALLOCATIONS, EXPLICIT_APPROVED_LINES, or unset |

### Attended individual booking

- Gym/FitiGo percentages: existing `terms.attended`.
- allocation_basis: PAID_NET_OF_DISCOUNTS_EXCLUDING_TAX or unset.
- calculation_unit: PER_ATTENDED_VISITOR / PER_BOOKING / unset.
- eligibility: VERIFIED_BACKEND_CHECKIN or unset.
- rounding: one of the explicitly selected monetary methods; when both are set,
  section and monetary rounding must match.
- Discount and tax handling reference the monetary policy, not separate conflicting
  defaults. Existing `group_basis` proposal remains visible; v2 calculation_unit is
  the explicit future accounting selection, not an instruction to change QR rules.

### No-show

- Percentages: existing `terms.no_show`.
- eligibility: CONFIRMED_PAID_CLOSED_WINDOW_NO_SCAN or unset.
- allocation_basis: PAID_NET_OF_DISCOUNTS_EXCLUDING_TAX or unset.
- partial_attendance: BLOCK_FOR_REVIEW / UNATTENDED_VISITORS_ONLY / unset.
- Explicit rounding matching monetary policy.
- UNATTENDED_VISITORS_ONLY describes a policy, but the current booking-level source
  does not provide participant no-show events. Future posting must remain blocked
  until that evidence exists; no additional attendance behavior was introduced.

### Single-Gym membership

- Percentages: existing `terms.single_gym`.
- recognition_method: AT_ACTIVATION / DAILY_SERVICE_PERIOD / PER_VERIFIED_EVENT /
  OTHER_APPROVED / unset.
- start_event: ACTIVATION / SERVICE_PERIOD_START / unset.
- end_event: ORIGINAL_EXPIRY / ADJUSTED_EXPIRY / unset.
- pause_treatment: SUSPEND_AND_EXTEND / CONTINUE_SCHEDULE / unset.
- transfer_treatment: PRESERVE_SCHEDULE_NO_NEW_SALE / PROHIBITED / unset.
- refund_treatment: REVERSE_ORIGINAL_RECOGNITION / MANUAL_REVIEW / unset.
- SUSPEND_AND_EXTEND with ORIGINAL_EXPIRY is rejected as contradictory.
- OTHER_APPROVED requires a specification reference and is **UNSUPPORTED**, not
  an executable formula. No recognition schedule exists in Phase 2.
- Legacy `membership_recognition: NOT_APPROVED` remains for old clients. The v2
  policy is additive; neither representation enables recognition/statutory reports.

### Multi-Gym

- Per-visit payout, per-member/per-gym monthly visit and amount limits: existing fields.
- platform_monthly_payout_cap: nullable Decimal amount.
- platform_cap_scope: PER_MEMBERSHIP_ALL_GYMS / ALL_MEMBERSHIPS_ALL_GYMS / unset.
- cap_exhaustion: HOLD_FOR_REVIEW / STOP_FURTHER_ALLOCATION / unset.
- earning_formula: FIXED_PER_VERIFIED_VISIT / PERCENT_OF_NET_PURCHASE /
  OTHER_APPROVED / unset, with the matching fixed amount/percentage/specification.
  Extraneous or missing formula parameters are rejected.
- recognition_method: same method options, independently configured; OTHER requires
  a reference and stays unsupported.
- unused_value: REMAIN_UNALLOCATED / MANUAL_REVIEW / OTHER_APPROVED / unset.
- monthly_reconciliation: ADMIN_APPROVED_VERIFIED_VISITS / unset.
- allocation_timezone: Asia/Kolkata / UTC / unset.
- Blank caps/rates mean missing, never unlimited/zero. No remaining purchase value
  is classified as FitiGo earnings. Monthly budget/cap execution is a later phase.

### Owner settlement

Existing frequency/cycle/threshold and mandatory approval remain in `terms.settlements`.
New fields:

- Weekly cutoff weekday (0 Monday … 6 Sunday), monthly cutoff day (1 … 31).
- Short-month rule: LAST_CALENDAR_DAY / NEXT_MONTH / unset.
- Cutoff time HH:mm:ss and explicit Asia/Kolkata or UTC timezone.
- Holding days: integer >= 0; zero is explicit, null means unknown.
- Eligible deductions: null unknown, [] explicitly none, or unique selections from
  ACTUAL_GATEWAY_FEES / ACTUAL_TAX_WITHHOLDING / APPROVED_SOURCE_ADJUSTMENT.
- Partial settlement: ALLOW_WITH_ALLOCATION_LINKS / FULL_ENTITLEMENT_ONLY / unset.
- Failed settlement: REMAIN_OUTSTANDING_REQUIRE_EVIDENCE / unset.
- Required cutoff fields follow the configured weekly/monthly frequencies. No payout
  date, payment evidence or settlement transaction is created by these settings.

## Monetary precision contract (no calculations in this phase)

- Keep database money as Decimal rupees at scale 2; gateway contract uses integer
  paise. Decimal JSON values are strings, never binary float calculations.
- Percentage inputs remain Decimal 0..100 with <=2 decimals and pair sum 100.
- New policy amounts and percentages reject binary floats and booleans. Use Decimal,
  integer or decimal-string input. Legacy endpoints retain their existing parsing.
- Future calculations use a local Decimal context with 28 significant digits and
  explicit approved rounding. Overflow/excess precision must fail closed rather
  than silently clamp to the database width. No calculation is performed here.
- Future percentage arithmetic must be exact until the approved rounding boundary;
  no implicit Python default rounding is a commercial policy.
- Largest-remainder option: future residual paise assigned by fractional remainder,
  ties by stable visitor index. Final-visitor option: final stable visitor absorbs
  remainder. Require-exact option: non-divisible allocation is held for review.
- Discount allocation must use actual source discounts and the approved rule; never
  subtract a discount twice from already discounted paid value.
- Separately collected tax requires actual source tax evidence. Missing is not zero.
  Tax inclusion is not an available shortcut because it contradicts the stated
  after-discounts/excluding-tax agreement; a changed tax policy requires review.
- Partial refund policy references original allocation IDs/amounts or approved lines,
  not the latest agreement rate. Future reversals must not exceed original entries.
- No new FLOAT/DOUBLE financial columns or monetary allocations are introduced.

## Agreement selection contexts and version pinning

All seven contexts are independently configured, with instant initially null:

| Context | Permitted explicitly selected instants |
|---|---|
| BOOKING_PURCHASE | CHECKOUT_CREATED, PAYMENT_CAPTURED |
| BOOKING_ATTENDANCE | CHECKOUT_CREATED, PAYMENT_CAPTURED, BOOKING_START, CHECKIN |
| NO_SHOW | CHECKOUT_CREATED, PAYMENT_CAPTURED, BOOKING_START, NO_SHOW_CONFIRMED |
| MEMBERSHIP_PURCHASE | CHECKOUT_CREATED, PAYMENT_CAPTURED |
| MEMBERSHIP_ACTIVATION | CHECKOUT_CREATED, PAYMENT_CAPTURED, MEMBERSHIP_ACTIVATED |
| MEMBERSHIP_RECOGNITION | MEMBERSHIP_ACTIVATED, RECOGNITION_PERIOD_START |
| MULTI_GYM_VISIT | MEMBERSHIP_ACTIVATED, CHECKIN |

- No context automatically selects any commercial instant. Selection needs an
  explicit governing policy version whose context rule is APPROVED with a reference.
- Conservative technical guard: the supplied governing policy must be effective
  at the stored source event time. Its selected instant then resolves the commercial
  agreement through the existing gym override/default resolver. Both version IDs
  are retained. A future alternative governing-policy assignment requires explicit
  contract revision; current code does not infer a latest policy for old events.
- `select_for_source()` accepts stored source IDs, never browser mode/amount/time.
  It derives environment from `payment_checkouts.mode` and verifies scope ownership.
- `pin_for_source()` is a dormant internal caller-transaction function: locks the
  checkout/default agreement scope, creates one immutable pin per checkout/context/
  source identity, and never commits on its own. No HTTP pin endpoint exists.
- Separate source identities handle cart bookings, booking visitors, membership
  purchase checkout, activated membership, and Multi-Gym daily access.
- Exact retries return the existing pin rather than reinterpreting later ownership
  or later agreements. Conflicting governing version/environment is rejected.
- Pin contains agreement-version ID, selection-policy-version ID, selected source
  time, immutable mode, source identity, evidence JSON/hash and creation time.
- Pin is **not** a financial event/allocation/recognition/journal. Future events and
  allocations must FK the pin and pass additional funding, owner and policy checks.
- Posting eligibility is always false; a selected version alone is insufficient.

### Evidence-dependent selection limitations

- PAYMENT_CAPTURED is configurable but cannot resolve until authoritative provider
  capture time is persisted. first_seen_at/updated_at are not substitutes.
- BOOKING_START is configurable but blocked until immutable scheduled-service
  evidence exists; current reschedulable slot values are not historical proof.
- MEMBERSHIP_RECOGNITION context exists but resolution is blocked because no stored
  recognition-period source exists yet. No schedule was fabricated for Phase 2.
- Multi-Gym check-ins without token.valid_from are blocked, preserving the Phase 1
  finding. QR issuer/query behavior was not changed in this phase.

## Ownership and environment

`FinancialSourceEvidence` defines a strict internal future-event contract containing:
source ID/type, context, checkout ID, source-derived mode and timestamp, gym ID,
owner-at-event ID/reference, original purchaser, holder-at-event, financial beneficiary
with evidence reference, and agreement pin ID. No HTTP endpoint accepts this object.

- Checkout environment is authoritative. Admin report filters/config scope selections
  cannot assign a different environment to a source event or pin.
- Original purchaser is checkout.user_id. Current membership holder can differ only
  with completed transfer evidence. Check-in holder is preserved independently.
- Financial beneficiary is not automatically the current holder or current gym owner.
- Existing records lack immutable historical gym-owner/beneficiary snapshots. The
  pin records null and SOURCE_DATA_MISSING, never queries current gym ownership to
  invent past ownership. The future source producer must record owner-at-event under
  source locks, with evidence, and preserve it thereafter. Historical rows require
  reconciliation rather than backfill from current owner IDs.
- The schema rejects owner/beneficiary IDs without supporting references. This is
  structural validation, not proof of authenticity; future producers must verify
  those references. No source producer is wired or historical owner rewritten here.

## Evidence mapping and exact required extensions

The machine-readable catalog is also returned by agreement GET `policy_catalog.evidence`.

| Event | Existing evidence | Missing / required extension |
|---|---|---|
| Successful collection | payment_attempts SUCCESS/captured observation + checkout order/amount/currency/mode | Preserve existing backend verification; not every PAID label alone is sufficient |
| Capture date | Not stored; first_seen_at is observation only | Add nullable provider_captured_at, capture_timestamp_source, verified_at; extend ProviderPayment and Razorpay/Cashfree normalizers |
| Refund amount/date | Cumulative payment_attempts.refunded_amount | Separate unique provider refund event ID, amount/currency/date/verification and original attempt FK |
| Gateway fee/fee tax | Not persisted | Actual fee/tax Decimal values, provider evidence reference/date, attempt/settlement links; no percentage estimate |
| Gateway settlement | No settlement evidence | Provider settlement identity/environment/date, net/fee/tax and payment allocation references; verified imports |
| Booking visitor attendance | SUCCESS Checkin + QR visitor/source/gym/user/window | Preserve source check-in ID; mutable manual ATTENDED is not admission |
| Confirmed no-show | bookings.attendance_status + attendance_marked_at | Immutable actor/time/window/source no-show event; participant evidence for partial groups |
| Membership activation | user_memberships.start_at + verified checkout fulfillment | Future immutable activation source snapshot, not creation/capture-date conflation |
| Pause/extension | membership_pauses dates/days, previous/new expiry | Approved accounting interpretation, future schedule links; don't alter operational pause behavior |
| Transfer | membership_transfers original/recipient/date + original checkout purchaser | Preserve original sale; future beneficiary snapshot separate from holder |
| Multi-Gym visit | checkins + daily access + QR | Audited token.valid_from omission needs Phase 3 source repair; no manufactured historical window |
| Wallet credit/debit | wallet_transactions + checkout_funding / booking_cancellations | Future immutable movement environment and credit-lot allocations; don't duplicate movements |
| Actual owner payout | No payout records | Actual payment reference/date/mode/currency/beneficiary/evidence/status and original entitlement links; approval not proof of payout |

These evidence/provider additions are **documented proposals**, not migrations or
provider behavior changes in Phase 2. No capture/refund/fee/payout fields were backfilled.

### Proposed schema/adapter specification (not applied)

Use UTC DATETIME with timezone-normalized adapters, Decimal NUMERIC(12,2) rupees,
integer paise in provider objects, nullable fields for unobserved evidence, and
unique `(mode, provider, external_event_id)` identities. Never use a database
insertion timestamp as the provider occurrence timestamp.

- `payment_attempts`: nullable `provider_captured_at DATETIME`,
  `capture_timestamp_source VARCHAR(100)`, `verified_at DATETIME`.
- Proposed `payment_refund_evidence`: `id`, `attempt_id` FK, `checkout_id` FK,
  source-derived `mode VARCHAR(10)`, `provider VARCHAR(50)`,
  `external_event_id VARCHAR(100)`, `amount NUMERIC(12,2)`, `currency VARCHAR(3)`,
  `provider_refunded_at DATETIME NULL`, `verified_at DATETIME`, `body_hash CHAR(64)`,
  `status VARCHAR(30)`, `evidence_reference VARCHAR(200)`.
- Proposed `gateway_settlement_evidence`: analogous mode/provider/external identity,
  `settled_at DATETIME NULL`, `gross_amount`, `net_amount`, `fee_amount`,
  `fee_tax_amount` as NUMERIC(12,2), currency and verification/hash/reference. Separate
  `gateway_settlement_payment_links` references attempt/refund IDs and Decimal amounts.
- Proposed `payment_fee_evidence`: attempt FK, optional settlement FK, unique provider
  evidence identity, actual fee/tax Decimal amounts, currency, occurrence/verification
  timestamps and reference. Fee tax is not customer sales tax.
- Proposed `booking_service_evidence`: booking/visitor FK or stable visitor index,
  immutable scheduled start/end, observed event kind, occurred_at, actor/source,
  source-derived mode, event reference/hash and original owner snapshot. No-show
  evidence includes final admission-window closure and confirmed absence checks.
- Proposed `membership_activation_evidence`: membership/checkout FK, activation time,
  original purchaser, holder-at-event, gym/owner-at-event and evidence reference.
  Pause/transfer evidence links existing permanent records; never another payment.
- Proposed source-level customer-tax/discount evidence: checkout/source-line FK,
  actual gross/discount/net/tax Decimal amounts, currency, evidence identity and
  method/reference. Until present, excluding separately collected tax is blocked.
- Proposed wallet lot links: existing credit transaction FK, debit transaction FK,
  Decimal consumed amount, original source-derived mode, immutable allocation ID.
  They explain existing movements; they must never duplicate the wallet balance.
- Actual owner payout evidence belongs to the separately approved settlement phase:
  original entitlement/allocation links, beneficiary snapshot, mode/currency, actual
  amount, provider/bank reference, paid_at, failed/reversed evidence and verification.

Adapter extension points inspected:

- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\services\payment_provider.py`:
  extend `ProviderPayment` with optional authoritative capture/fee evidence, and
  introduce typed refund/settlement evidence DTOs. Do not overload cumulative refunded.
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\services\razorpay_provider.py`:
  `payments()` currently normalizes status/amount/refunded only; preserve source
  timestamps/evidence when independently verified. A created timestamp must not
  silently become a captured timestamp.
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\services\cashfree_provider.py`:
  `payments()` currently returns the same minimal contract; preserve individual
  refund identities and authoritative event timestamps rather than only totals.
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\services\payment_checkout_service.py`:
  future observation boundary persists verified evidence atomically and deduplicates
  events. Provider-specific payload semantics/endpoints still need official-contract
  verification during that implementation; no new provider assumption is asserted here.

## Admin screen and API

- Only the existing Revenue Sharing Agreements screen was extended. Existing fonts,
  theme, global CSS, header and navigation are unchanged.
- Opt-in checkbox includes contract v2 only for a new agreement version.
- Controls are generated from the backend Pydantic JSON schema, including nullable
  single-choice fields; unknown values display Not configured rather than a default.
- Separate collapsible sections for monetary, booking, no-show, Single-Gym,
  Multi-Gym, settlements and seven selection contexts, each with approval/reference.
- Explicit state labels: Configured, Awaiting approval, Not configured, Unsupported;
  agreement lifetime labels: Effective, Effective in future, Expired / superseded.
- Validate policy readiness checks the entire current proposal, including old rates
  and caps, without saving or pinning. A changed proposal invalidates its displayed
  validation result. Review/save still uses the existing versioned confirmation path.
- Stored policy JSON and computed readiness are visible in immutable history.
- `GET /api/v1/admin/financial-agreements`: additive `policy_catalog` and per-version
  `policy_readiness`; existing fields unchanged.
- `POST /api/v1/admin/financial-agreements`: same endpoint/idempotency/version contract.
- Added `POST /api/v1/admin/financial-agreements/policy-validation`: ADMIN/SUPER_ADMIN,
  no-store, schema validation only; no source/pin/financial writes.
- CA reference on an agreement does not approve its individual policy sections;
  section approval does not independently verify CA sign-off or enable statutory reports.

## Migration and compatibility plan

Added migration `e57f81cb0379`, parent `d46e70ba9268`:

- New `financial_agreement_pins` table only: source/policy binding metadata, no amounts.
- FKs to existing checkout and both agreement version identities; unique
  `(checkout_id, context, source_key)`; immutable ORM guards.
- No changes/backfill to existing agreement terms, templates, purchases, wallets,
  memberships or attendance. No financial journal/payable/settlement tables created.
- Downgrade refuses destruction once pin evidence exists. Parent migration tests
  now downgrade the child first, respecting real FK order.
- Policy v2 uses existing JSON storage and does not require rewriting existing rows.
- Working DB remains on its existing revision; new migration tested only in isolated
  MySQL. Backup/migrate/restart requires a separate approved release.
- Direct privileged SQL bypasses ORM immutability; future ledger hardening remains
  Phase 3+. No claim of database-trigger-enforced immutability is made.

## Values still awaiting business/CA approval

No new commercial field was auto-approved or given a non-null default:

1. All seven commercial selection instants and their governing-policy decision.
2. Decimal rounding method/stage, residual paise distribution and discount allocation.
3. Source tax evidence requirements and partial-refund allocation/reversal method.
4. Explicit booking unit and no-show partial-attendance treatment.
5. Single-Gym recognition timing, service endpoints, pause/transfer/refund treatment.
6. Multi-Gym rates/member-gym limits if unset, platform cap scope/amount, cap exhaustion,
   FitiGo's independent formula/parameter, recognition, unused-value and monthly closure.
7. Settlement cutoffs/timezone, holding period, deductions, partial/failed handling.
8. CA-approved principal-agent/account mappings and statutory release approval.

## Tests and results

Validation results:

- Full backend regression checkpoint: **991 passed** on a disposable, isolated MySQL
  26.7 server. The run started before the final additional context/precision tests.
- Final Phase 2 targeted rerun: **83 passed** after those additions, including all
  existing agreement tests and new policy/selection tests.
- Frontend: **468 passed**, TypeScript no-emit check passed, Vite build passed.
- Mocked browser: proposal editing, policy opt-in, null choices, readiness validation,
  review/save/history, gym override and missing-schema guard passed at 360/768/1440.
- New migration upgrade/downgrade and evidence-loss refusal tested on disposable
  MySQL only; no provider calls or working-database changes.
- Read-only working database confirmation: revision `d46e70ba9268`, zero agreement
  versions, `financial_agreement_pins` absent.
- Existing datetime.utcnow deprecation warnings remain; no test failures.

Coverage includes
legacy hash preservation; null-vs-zero; precise percentages/money; invalid formulas;
contradictory pause/expiry; approval requirements; unsupported custom methods;
all context contracts; source-backed selection; wrong environment/source rejection;
missing captures/windows; future policy; immutable pins; concurrent retries; new
versions preserving old pins; read-only validation endpoint; migration preservation.

No journal/commission calculation tests are claimed: no such engine is introduced.

## Files changed / added

- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\schemas\accounting_policy.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\schemas\financial_evidence.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\schemas\financial_agreement.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\models\financial_agreement.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\services\accounting_policy.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\services\financial_evidence_contract.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\services\agreement_selection.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\services\financial_agreements.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\routers\admin_financial_agreements.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\alembic\versions\e57f81cb0379_policy_evidence_pins.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\tests\test_accounting_policy_contract.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\tests\test_agreement_selection_contract.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\tests\test_financial_agreements.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\admin\PolicyContractEditor.tsx`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\admin\RevenueSharingSettings.tsx`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\admin\agreementService.ts`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\scripts\policy-contract.test.mjs`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\scripts\agreements-browser.mjs`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\ACCOUNTING_PHASE2_POLICY_EVIDENCE.md`

Next step is policy/evidence review and approval. Do not proceed to ledger/source
producer integration until approved. Existing dashboard accounting amounts remain
unavailable because Phase 2 deliberately does not implement financial posting.