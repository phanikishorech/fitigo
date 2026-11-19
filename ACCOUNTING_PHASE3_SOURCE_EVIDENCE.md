# Phase 3 — source evidence and transactional handoff

## Scope

Additive source infrastructure only. No financial journal, commission calculation,
revenue recognition, owner payable, owner settlement, refund initiation, payout,
statutory reporting, branding or global CSS change. Existing agreement configuration
and selection policies remain intact. No working database migration or setting was
changed. `SOURCE_EVIDENCE_ENABLED` defaults to false and is a deployment gate, not a
financial posting switch.

## Inspection baseline

Reviewed the Phase 2 handoff, agreement version/pin models and seven independent
selection contexts, payment checkout/provider adapters and transports, booking
visitor scanner and no-show policy, cancellation/wallet credit, both membership
activation paths, production membership QR issuance/scanning, pause/transfer,
gym ownership, migrations and isolated test fixtures.

Existing `Checkin`, `BookingCancellation`, `MembershipPause`, `MembershipTransfer`,
`PaymentAttempt` and `WalletTransaction` remain the business source records. The
new records preserve evidence and refer to these IDs; they do not grant access,
create another payment/refund, or change any wallet balance.

## 1. Schema and migration

Migration **f68a92dc1480**, parent **e57f81cb0379**, creates:

### financial_source_evidence

- UUID identity and unique SHA-256 idempotency key.
- Event type, source type/ID, nullable FK to existing payment checkout.
- Immutable source-derived environment; null only for quarantined legacy evidence.
- Actual source `occurred_at`, separately stored `created_at`, evidence status.
- Optional NUMERIC(12,2) amount and currency; no FLOAT/DOUBLE.
- Versioned JSON payload and canonical SHA-256 integrity hash.
- Payload includes verification source, source references, relevant identities,
  admission/time/owner facts, and policy-resolution status.

### financial_source_outbox

- UUID event identity, unique evidence FK and idempotency key.
- Immutable event type, source ID, test/live environment and actual occurrence time.
- Processing status, retry count, last redacted error, availability time,
  lease expiry and random fencing token.
- `binding_status=AWAITING_POLICY_RESOLUTION` and nullable existing agreement-pin FK.
- No engine in this phase assigns a pin. Binding fields cannot be edited through
  the Phase 3 outbox worker.
- Index on environment/status/availability for claims.

### gym_owner_evidence

- Immutable evidence FK, gym ID, observed owner user ID, observation timestamp,
  and `LOCKED_SOURCE_MUTATION` basis.
- This is event-scoped owner evidence, **not** a fabricated historical ownership
  interval or a replacement for current gym ownership.

All three tables are additive. Migration performs no seed/backfill or transaction
updates. Downgrade refuses if any source evidence/outbox/owner evidence exists.
ORM update/delete guards protect evidence and outbox identity; privileged raw SQL
can bypass these guards, so DB permissions and backups remain operational controls.
Worker verifies evidence payload hash before handoff.

## 2. Payment provider changes

`ProviderPayment` retains its existing SUCCESS/PENDING/FAILED interface used by
checkout fulfillment. Additive fields preserve collection state, authoritative
capture timestamp/source, actual fee/tax/basis, and individual refund objects.

- INITIATED and AUTHORIZED are not capture events.
- CAPTURED requires the existing successful verification path.
- FAILED, PARTIALLY_REFUNDED and FULLY_REFUNDED are retained as observations.
- Each capture links checkout, existing attempt, provider order/payment identities,
  amount/currency, environment and verification source.
- Browser assertions and webhook body alone do not establish paid funds: existing
  signature checks, order/payment refetch, amount/currency and configuration checks
  are preserved.
- Provider webhook IDs are retained where supplied. Separate verified-event links
  retain a webhook identity even when capture was first observed by refresh.
- Cashfree currently supplies no distinct provider event ID through the existing
  webhook adapter. Null is retained rather than relabeling a receipt hash as one.
- Later timestamps/fees create deduplicated PAYMENT_DETAILS_VERIFIED evidence,
  linked to the original capture. They never rewrite or duplicate the capture.

### Razorpay

- Payment entity `created_at` is not used as capture time. Actual capture timestamp
  is explicitly unavailable from the currently used payment entity.
- Actual provider `fee`/`tax` integer paise are preserved if present and valid;
  Razorpay payment fee is marked INCLUDING_TAX. Missing remains null.
- Existing cumulative `amount_refunded` behavior remains unchanged.
- When evidence is enabled and refunds exist, read-only, bounded pagination of
  `GET payments/{payment_id}/refunds` preserves individual refund IDs, payment ID,
  amounts/currencies and statuses. No refund creation call exists.
- Refund `created_at` is not called successful processing time. If no authoritative
  completion time is available, confirmed refund evidence has null occurred_at.
- Invalid/missing refund evidence stops that reconciliation transaction; a later
  verified retry can complete. It never fabricates missing rows.

### Cashfree

- `payment_completion_time` is used only for SUCCESS with `is_captured=true` and
  no preauthorization object. Unknown/preauthorization capture timing stays null.
- Payment start time, receipt time and first-seen time are not substituted.
- Existing order-refund GET is reused. Individual successful refunds use
  `processed_at`, not `created_at`; pending/other statuses remain observations.
- Duplicate refund IDs do not create duplicate confirmed evidence or add the
  cumulative refunded amount twice within an observation.
- No actual fee is supplied by the existing normalized payment endpoint contract;
  fee/tax remain null until a separately verified source is integrated.

Provider documentation inspected (public documentation only; no merchant calls):

```text
https://razorpay.com/docs/api/payments/entity/
https://razorpay.com/docs/api/refunds/fetch-multiple-payments/
https://razorpay.com/docs/api/settlements/fetch-with-id/
https://www.cashfree.com/docs/api-reference/payments/latest/payments/Get-Payments-for-an-Order
https://www.cashfree.com/docs/api-reference/payments/latest/refunds/Get-All-Refunds-for-an-Order
https://www.cashfree.com/docs/api-reference/payments/latest/settlements/Get-Settlements-by-Order-ID.md
```

## 3. Gateway settlement contract — not imported

`GatewaySettlementEvidence` defines provider/environment, provider settlement ID,
provider status/reference, currency, actual settlement amount, fee/tax/basis,
settled_at, verified_at, verification source, evidence reference and reconciliation
status. Money is Decimal-safe; unknown amounts/times remain null.

Razorpay's settlement entity includes amount/status/fees/tax/UTR/created_at;
created_at is not silently treated as bank completion time. Cashfree's order
settlement API includes pending and failed settlements as well as linked details:
presence of a settlement object does not prove settlement succeeded.

**No settlement importer, settlement database records, owner payouts or automated
reconciliation are implemented.** This meets the contract-only fallback and avoids
violating the restriction on creating settlement records. A later reviewed importer
must verify status, actual timestamps, environment/account and payment links.

## 4. Booking and membership mutation boundaries

Evidence/outbox writes occur before the existing business commit, in the same
SQLAlchemy transaction. If evidence insertion fails, no partial business benefit
may commit. There is no independent post-commit notification-based source handoff.

| Production boundary | Evidence/event |
|---|---|
| New booking/cart checkout | BOOKING_PURCHASE_RECORDED per booking, not a captured sale |
| New membership checkout | MEMBERSHIP_PURCHASE_RECORDED, not activation |
| Verified payment observation | PAYMENT_CAPTURED / initiated / authorized / failed |
| Individual successful visitor scan | BOOKING_VISITOR_ATTENDED for that check-in only |
| Existing authorized booking no-show | BOOKING_NO_SHOW_CONFIRMED |
| Booking cancellation and wallet credit | BOOKING_CANCELLED plus linked WALLET_CREDIT_CONFIRMED |
| Gateway or development-wallet membership activation | MEMBERSHIP_ACTIVATED |
| Accepted pause and expiry extension | MEMBERSHIP_PAUSED referencing MembershipPause |
| Completed membership transfer | MEMBERSHIP_TRANSFERRED referencing MembershipTransfer |
| Multi-Gym successful admission | MULTI_GYM_VISIT_VERIFIED |
| Single-Gym successful admission | MEMBERSHIP_ADMITTED |
| Verified individual successful refund | REFUND_CONFIRMED |

### Visitor attendance and no-shows

Booking evidence preserves booking/visitor index/name, purchaser/customer, gym,
observed gym owner, successful check-in ID, QR ID, admission timestamp/window,
service date, environment and admission status. No QR raw secret is stored.
Existing unique per-booking visitor constraints and one-time scanner rules remain.
A guest name/index identifies an admitted guest, not an invented registered user.

Partially attended bookings produce only the actual visitor events. Existing
booking-level no-show remains owner/staff-authorized and requires the admission
window to end and no successful admission. The evidence rechecks these facts.
Unvisited guests in a partly attended booking remain **unresolved**, not automatically
no-show. A participant-level confirmation endpoint/process is not invented here;
it requires a separately approved operational workflow. Whole-booking confirmations
explicitly carry scope WHOLE_BOOKING and covered visitor indices.

### Membership QR mismatch fixed

Production `_mint_qr_token()` now sets valid_from from issuance time, floored to the
existing whole-second DATETIME precision. Existing five-minute/day-boundary expiry
is retained. Scanner checks not-before when valid_from is present and retains its
existing expiry guard. No historical QR values are populated or rewritten.

Admission snapshot includes membership/customer/gym/daily access/check-in/QR IDs,
validity start/expiry, service date, verified timestamp, USED access status and
source-derived environment. Legacy null-valid_from admissions remain incomplete
evidence, not financial-ready. The production issuance-to-scan test executes the
actual existing financial visit query and verifies the new admission is visible.

## 5. Ownership and transferred memberships

No sufficient historical ownership intervals were found. The current gym owner is
captured under a gym row lock at NEW purchase, activation, admission, cancellation
or no-show confirmation boundaries. Later owner edits cannot rewrite those snapshots.
Purchase and service snapshots are distinct; this phase does not choose which one
determines contractual owner entitlement.

Membership events distinguish original purchaser (checkout where available),
holder-at-event, original/recipient holder, and immutable transfer reference.
Pause/transfer can reference prior activation owner evidence. Historical financial
beneficiary is null/awaiting policy where never established; it is not invented by
equating the current holder or current owner with a beneficiary. No ownership changes
or historical beneficiary backfill occur in this phase.

## 6. Durable handoff and crash recovery

- Producers use deterministic source/event keys and source transaction locks.
  Database uniqueness is the final deduplication boundary.
- Worker `claim()` uses `FOR UPDATE SKIP LOCKED`, explicit test/live environment,
  a bounded lease and random lease token. Caller commits the claim first.
- `finish()` locks/revalidates identity, environment, payload hash, status and lease
  token. An expired/stale worker cannot acknowledge a reclaimed event.
- Crashed workers leave PROCESSING rows that can be reclaimed after lease expiry.
- Controlled errors become RETRY with bounded backoff and redacted last_error.
- Crash before claim commit rolls it back; crash before finish commit leaves the
  durable lease, so evidence is not lost. Exact successful acknowledgement repeats
  are idempotent.
- Successful Phase 3 handoff ends AWAITING_POLICY or AWAITING_EVIDENCE. It never
  deletes events, sends provider requests, binds an arbitrary agreement or posts.
- Retry_count counts claim attempts, including recovered leases.

Internal CLI only; no new public financial mutation endpoints:

```powershell
& 'C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\.venv\Scripts\python.exe' 'C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\scripts\source_event_worker.py' --mode test --limit 100
```

Do not start this on the working database until deployment is separately approved.
Policy/evidence resolution and journal consumers are future phases; no scheduled
worker or requeue-to-post workflow was installed.

## 7. Environment isolation and historical limitations

- Checkout.mode is authoritative, never a frontend argument or current report mode.
- Linked wallet movement/account is used when there is no checkout; cross-environment
  checkout/wallet relationships and owner mismatches are rejected.
- Legacy sources without trustworthy environment are retained as quarantined evidence
  with ENVIRONMENT_UNAVAILABLE and **no routable outbox row**. Null is not test/live.
- Existing wallet accounts without historical mode cannot prove past environment.
- Source timestamps can be null when the provider cannot establish them; outbox does
  not replace null with observed/created time. Such events await evidence.
- No bulk historical reconciliation, source replay/backfill, QR correction or
  reclassification was run. Existing financial transactions remain unchanged.
- No tax/discount line evidence, wallet credit-lot allocation engine or historical
  owner reconstruction is invented. These remain later evidence/reconciliation work.

## 8. Deployment and rollback

1. Review this handoff, code, tests, provider read permissions and operational gates.
2. Back up database; apply outstanding Phase 2 pin migration then f68a92dc1480.
3. Deploy producers with evidence gate still off; verify schema and permissions.
4. Enable SOURCE_EVIDENCE_ENABLED on **all** mutation-serving instances together.
   Partial rollout would create an explicit evidence coverage gap; record the cutover.
5. Verify sample new events, environment, owner snapshots and source/outbox counts.
6. Only then optionally run bounded handoff workers, separately per environment.
7. Posting/statutory flags remain false throughout.

Enabled mode with missing tables fails closed (503 before commit), not silent data
loss. Gate-off compatibility preserves existing operational behavior but creates no
new evidence; disabling it is an explicit coverage-gap decision, not transparent rollback.

Rollback code without dropping evidence. Empty-table downgrade is tested; populated
downgrade is refused. Stop workers before rollback, retain rows for forward repair.
Do not downgrade Phase 2 parent tables while new FK children exist.

## 9. Validation

Tests use disposable databases and mocked providers; no real refunds/payouts or
merchant API calls. Full-suite and focused checkpoints are reported separately:

- Full backend checkpoint: **1,010 passed, 2 failed** before the final QR precision
  correction. The two immediate-scan failures exposed MySQL timestamp rounding of
  newly issued valid_from. The fix floors validity start to whole seconds.
- Final QR/access/pause/booking/agreement/migration regression rerun:
  **109 passed**, including both previously failing production QR tests.
- Final enabled evidence/provider/cancellation/concurrency suite: **95 passed**.
- Dedicated final source/worker/provider/settlement-contract run: **31 passed**.
- Final admin-override lock-order and source/contract rerun: **21 passed** after
  aligning the override's customer/gym/booking lock order with the scanner.
- A full all-tests green rerun after the final changes is **not claimed**. The above
  targeted reruns cover the corrected paths; the earlier full run retained all
  existing regressions and reported its failures honestly.
- Existing datetime.utcnow deprecation warnings remain.
- No frontend files changed; frontend/browser/build tests were not rerun in Phase 3.
- Worker CLI --help/import validated without executing a worker on working data.
- Read-only working DB verification: revision d46e70ba9268; zero agreement versions;
  all three new tables absent; source evidence gate false.

The provider/API tests reuse existing disposable SQLite fixtures under the isolated
runner; source atomicity, owner snapshots, real membership QR issuance/admission,
analytics visibility, no-show, pause/transfer, migration, concurrency and worker
crash/recovery tests execute on disposable MySQL. Tests never contact configured
merchant credentials.

## 10. Implementation inventory

All paths below are under the existing workspace; no parallel application added:

- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\alembic\versions\f68a92dc1480_source_evidence.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\models\source_evidence.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\schemas\gateway_evidence.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\services\source_evidence.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\services\payment_evidence.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\services\source_outbox.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\scripts\source_event_worker.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\tests\test_source_evidence_mysql.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\tests\test_source_evidence_providers.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\tests\test_gateway_evidence_contract.py`

Existing provider/service boundaries extended in place; model registration, settings,
isolated runner and parent migration tests updated. Existing Phase 2 handoff remains
unchanged as the historical baseline; this document describes what Phase 3 adds.

Stop here for review. No Phase 4 journal, recognition, payable or settlement engine
has been started.