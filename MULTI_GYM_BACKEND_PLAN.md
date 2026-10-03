# Multi-Gym catalog, offers and payment integration plan

**Current milestone:** controlled development wallet checkout now activates explicit memberships using test credits. Single-Gym dummy activation has been replaced. See `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\MEMBERSHIP_WALLET_MVP.md`. The proposal/foundation history below is retained for context; external payments are still disabled.

Status: catalog, pricing and unpaid order foundations are now implemented; payment initiation and activation remain disabled. See `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\MULTI_GYM_FOUNDATIONS.md` for the actual contract, local deployment repair and deployment procedure. The broader payment/entitlement design below remains a proposal. Provider selection and the product decisions below are still open. The catalog migration and initial configuration have now been applied to the local development database; no payment or entitlement change has been performed.

Implementation deviation for the limited foundation phase: additive platform catalog tables preserve the existing gym-bound schema and APIs. No nullable gym IDs or access-inference changes ship before the explicit entitlement migration is ready. The future integration must connect platform purchases into the existing membership/access system rather than treating review orders as entitlements.

## 1. Verified starting point

- Backend: FastAPI, SQLAlchemy, Pydantic, MySQL, Alembic, httpx and pytest. Current migration head: `2a7d0b9c9a11`.
- Frontend: React/TypeScript, existing history router, API client, resource hooks, membership checkout and shared FitiGo components. Preserve these.
- Catalog: `GET /api/v1/memberships/gyms/{gym_id}/plans`, with gym-bound IDs, decimal-string price, currency, duration_days and is_active. No platform catalog, offer, pause allowance or promotional metadata contract exists in the running OpenAPI definition.
- Purchase: `POST /api/v1/memberships/gyms/{gym_id}/purchase` accepts plan_id and validates the database price, but activates using DUMMY/PAID. The frontend blocks production purchases; the backend needs its own guard.
- Both gym_membership_plans and user_memberships require gym_id. Daily access and QR records reference user_memberships.
- AccessService and profile responses infer MULTI_GYM from multiple active gym-bound memberships. Gym discovery applies different gym-bound membership checks. These cannot be reused unchanged for a platform plan.
- Gym approval/active status exists; explicit Multi-Gym partner enrollment does not.
- Wallet ledger and debit checkout exist. Wallet top-up credits requested amounts without payment-provider verification. Some wallet/cart routes also fall back to a development customer without an environment guard in their local helper.
- No external payment gateway integration or webhook router was found.
- Test tooling is available. Twenty relevant membership/access tests collected successfully. Existing membership integration tests write through the configured database; run implementation tests only against an isolated test database.

## 2. Implementation boundaries

Extend the existing backend, not a separate service or cart. Preserve Single-Gym plan IDs, existing visit/cart behavior, historical memberships and check-ins. Reuse membership checkout layout and shared UI; its new Multi-Gym mode will use verified orders rather than dummy activation.

Catalog metadata, price/offer calculation, membership validity, partner eligibility, pause validation and expiry computation belong on the server. Frontend only renders returned values and action capabilities.

Gateway selection is not inferred from currency or developer preference. No real funds, credentials, production deployment or live migrations are part of this planning step.

## 3. Proposed persistence changes

### Plans and offers

Prefer extending gym_membership_plans in place (despite its historical name) to preserve IDs and owner APIs, subject to migration review:

- Add membership_type: SINGLE_GYM or MULTI_GYM; backfill existing rows as SINGLE_GYM.
- Allow gym_id to be null only for MULTI_GYM. Enforce the scope/gym invariant in validation and database constraints supported by the deployed MySQL version. Owner APIs must only read/write their gym-bound plans.
- Retain stored price as base price; introduce explicit duration_value/duration_unit, display_order, optional badge, benefits and a version number. Existing gym APIs keep price and duration_days compatibility. Do not convert existing 30-day plans to calendar months.
- Add explicit server-enforced pause-rule configuration only when a corresponding pause workflow is implemented. Do not advertise allowance from a decorative text field alone.
- Add plan offers: plan reference, type (fixed/percentage), configured discount value, title, enabled flag, validity interval and audit fields. Initial proposal: one effective offer per plan, no stacking. Reject ambiguous overlapping windows; confirm this policy before implementation.
- Use Decimal database values; do not calculate money using float. Server produces base_price, discount_amount, final_price and optional display percentage. Define currency rounding once, independently of the display percentage.
- Admin-managed Multi-Gym partner enrollment per gym, default false. Enrollment does not override suspension, approval or active status.

### Memberships

- Extend user_memberships with explicit scope and nullable gym_id under the same invariant. Keep daily access foreign keys attached to this existing membership entity.
- Snapshot purchased duration, access rule, pause rule, name and pricing terms; retain original expiry separately from adjusted expiry. Later catalog changes must not silently rewrite already-purchased terms.
- Preserve old gym-specific routes and response semantics for Single-Gym callers. Update typed customer/admin/profile consumers before returning platform records with null gym_id. This is a coordinated compatibility rollout, not an unreviewed nullable-field change.

### Orders and verification

- membership_orders: customer, plan, pricing/terms snapshot, plan version, currency, status, acceptance/expiry metadata, provider references and linked membership ID.
- payment_attempts: order, provider, provider order/payment IDs, verification state and retry/reconciliation metadata. Keep payment outcome separate from membership fulfillment.
- payment_webhook_events: unique provider/event key, verified receipt metadata and processing state. Minimize retained payloads; never log credentials or payment instrument data.
- Unique constraints for customer-scoped idempotency keys, provider payment references and membership activation per order. A request-payload fingerprint rejects reuse of a key for different input.
- Persist audit events for plan/offer/partner edits and order transitions; do not claim an existing audit product is available.

## 4. Proposed HTTP contract

These routes are proposals, not existing APIs. Prefix: `/api/v1`.

| Route | Responsibility |
| --- | --- |
| GET /memberships/plans?membership_type=MULTI_GYM | Active platform catalog, server ordering, current effective pricing and metadata |
| GET /memberships/plans/{plan_id} | Fresh plan details and availability |
| POST /memberships/orders | Authenticated customer submits plan_id; backend returns the current price/terms for review. Idempotency-Key required. No price field accepted. |
| GET /memberships/orders/{order_id} | Owner-only canonical order, payment and activation status for refresh/polling |
| POST /memberships/orders/{order_id}/payment-session | Revalidate availability, eligibility and price before starting payment; no frontend amount accepted |
| POST /payments/webhooks/{configured_provider} | Provider-authenticated notification; no customer JWT; verify authenticity before processing |
| POST/PATCH /admin/membership-plans[/\{plan_id\}] | Authorized platform catalog configuration, versioned edits and audit |
| POST/PATCH /admin/membership-plans/{plan_id}/offers[/\{offer_id\}] | Authorized validated offer configuration |
| PUT /admin/gyms/{gym_id}/multi-gym-participation | Explicit platform partner enrollment, not owner self-enrollment |

Retain existing `/memberships/me`, `/profile/membership`, discovery/details, calendar and QR routes, extending their implementations consistently. Add a read-only gym-specific access decision only if extending the existing membership_access response cannot represent the required state without duplication.

### Catalog response fields

Envelope: items, server_time, catalog_version and checkout availability. Empty items means genuinely no active catalog entries; an API failure is not an empty result.

Each item:

- id, name, membership_type, description
- duration_value, duration_unit; server-formatted display label where appropriate
- base_price, discount_amount, final_price as decimal strings; currency
- discount_percentage only when the server intentionally supplies one for display
- offer: null or active offer metadata including id, title and valid_until
- badge, display_order, is_active, benefits
- access_rule: eligible partner scope and daily access allowance (one under the specified product rule)
- pause_rule: enabled and verified configuration, or null/unavailable
- version and explicit availability/purchase capability

Inactive/expired offers produce offer=null, no stale discount label, and server-calculated current price. Preserve database ordering with a deterministic tie-breaker. Never infer badges from duration or derive pricing in React.

Reject frontend-supplied amount/discount fields on order commands rather than silently treating them as trusted. Use structured error codes such as PLAN_UNAVAILABLE, PRICE_CHANGED, OFFER_CHANGED, MEMBERSHIP_NOT_ELIGIBLE, CHECKOUT_UNAVAILABLE and PAYMENT_PENDING with safe customer-facing messages.

## 5. Payment lifecycle and price changes

1. Choose Plan submits its ID to create or resume an order. Server checks current account eligibility and returns authoritative terms and payable amount.
2. Customer reviews that amount in the existing membership checkout layout.
3. Payment-session creation revalidates price, offer, availability and eligibility. If terms changed, return a recoverable conflict and fresh order revision for explicit customer review. Do not silently charge more or less than the accepted amount.
4. Persist an initiation state and stable provider reference before calling the provider. Avoid holding database locks across network calls. On timeout, reconcile that reference before another provider order is created. Map provider-specific idempotency only after selecting its documented integration.
5. Create a hosted payment session/order using the server-owned amount/currency. Return only provider-approved public browser data. Never return private keys or accept browser-supplied payable amounts.
6. Treat browser return/callback as UX only. UI queries order status and may display Payment processing; it cannot mark the order paid.
7. Verify webhook authenticity using the selected provider's documented mechanism. Validate provider account/environment, order reference, amount, currency and captured/success state; use server-to-server verification as required by that provider. Authorization alone is not fulfillment.
8. Under consistent locks/unique constraints, record verified payment and activate the membership once. Duplicate notifications and retries must not create additional memberships or charges. A durable processing record and reconciliation job recover from database/provider/network failures.
9. Paid but not activated remains a visible recoverable fulfillment state, not an instruction to pay again. Admin reconciliation must account for every such order.
10. Catalog price edits after payment initiation do not rewrite accepted payment snapshots. A late payment on an expired/revoked order enters reconciliation rather than automatic entitlement issuance or an unverified refund promise.

State separation:

- Payment: pending, verified/captured, failed, refunded, disputed as actually supported by the selected provider.
- Order fulfillment: awaiting payment, activation pending, activated, reconciliation required, cancelled/expired.

Provider events can be duplicated or arrive out of order. Transitions must not regress verified payment merely because an older failure event arrives. Reconciliation also covers refund/dispute events according to an agreed entitlement policy.

Initial payment proposal: one-time membership purchase, not automatic renewal. Wallet is excluded from production membership funding until top-up verification, authentication and ledger provenance are resolved. Do not relabel existing unverified balances as paid funds.

## 6. Access integration and legacy migration

Create one server entitlement resolver used by gym discovery/details, Book a Visit decisions, summary, calendar, QR issuance and staff validation.

- Single-Gym: explicit purchased scope and matching gym.
- Multi-Gym: explicit purchased scope and eligible, approved, active enrolled partner.
- One daily access shared across eligible memberships for the user. Existing check-in evidence must remain authoritative even if the selected membership or QR changes.
- Recheck membership/payment dates, account status, pause, partner status and daily consumption at scan time; retain short-lived hashed QR tokens and existing staff authorization.
- Keep eligibility, daily-used state and action capabilities distinct. Available applicable membership opens the existing two-choice popup. Used membership access continues into paid visit booking. My Access stays personal-only.
- Upgrade the current count-based inference everywhere together. Do not silently convert two Single-Gym purchases into a new paid platform membership or revoke legacy access without an explicit transition policy.
- Migration rehearsal must cover legacy QR tokens/daily rows and null gym references in all owner/admin/report code. Use staged feature flags so selling plans cannot start before their access path is deployed.

Pause enforcement is a separate dependency for any advertised pause allowance: future-date validation, overlap/allowance checks, preview and confirmed expiry must run on the backend with membership-linked pause records. Do not seed an enabled pause benefit before that workflow is operational.

## 7. Release-blocking security work

- Backend environment guards for dummy membership activation and unverified top-up; frontend DEV checks are insufficient.
- Remove anonymous/development-customer fallbacks from payment-capable operations in production. Require active authenticated customer and resource ownership; strict roles on platform configuration.
- Verify webhook bodies before side effects, bound request size, redact logs and separate sandbox/live configuration. Exact signature/replay handling depends on provider contract.
- Rate-limit order creation/status and webhook abuse; choose implementation consistent with deployment infrastructure, not a new unapproved stack.
- No destructive downgrade after live platform purchases without a reviewed recovery path. Document backups, forward repair, feature flags and migration ordering.

Security reference used for the plan: OWASP Third Party Payment Gateway Integration Cheat Sheet (official OWASP Cheat Sheet Series). Server-side payment verification, amount/order validation and idempotent fulfillment inform this design; provider details will be checked against official documentation after selection.

## 8. Configuration and outstanding product decisions

The four requested names, INR prices and month durations can be imported as backend configuration through an explicit idempotent admin/seed operation. They will not be frontend constants or silently inserted into a live database. No offer, badge or pause allowance will be invented.

Before enabling sales, confirm:

1. Payment provider/account and sandbox integration; secrets supplied only through server configuration, never chat or source code.
2. Calendar-month versus fixed-day duration semantics, end-of-month behavior and access timezone. Existing access uses UTC; do not silently change historical dates.
3. Whether the listed prices include any applicable tax/fees and what the displayed final payable total must include. No tax assumptions in code.
4. Purchase overlap/renewal/upgrade policy, including paused memberships and mixed Single-/Multi-Gym ownership.
5. Legacy count-based access transition/grandfathering and explicit partner enrollment.
6. Plan-specific pause allowance, extension policy and when pause support should ship.
7. Offer stacking/overlap, price acceptance window, late payment/refund/dispute handling and membership start time.

## 9. Delivery sequence and tests

1. Agree contract and provider. Establish isolated MySQL test database and capture baseline tests without touching the development/live data.
2. Add additive Alembic migrations, models, catalog/pricing service and restricted configuration APIs; test upgrades using representative legacy records.
3. Centralize eligibility and integrate explicit scope throughout membership/access/discovery. Test existing Single-Gym behavior and account-wide daily-use concurrency.
4. Implement orders and selected provider sandbox adapter, verified events, idempotent activation and reconciliation. Keep production checkout disabled until release gates pass.
5. Connect real Multi-Gym catalog to the shared frontend service/resource layer. Extract reusable plan cards, price/offer display and existing checkout presentation; never pass frontend prices as authority.
6. Implement pause workflow before exposing enabled pause benefits. Import approved plan and partner configuration.
7. Run backend, frontend, responsive and sandbox end-to-end tests. Require explicit production readiness sign-off and environment configuration.

Test matrix: no/percentage/fixed/labeled/expired offers; date/rounding boundaries; inactive plan; ordering/badge changes; stale pricing; extra amount fields rejected; owner cannot edit platform plans; customer cannot read another order; invalid signatures and amount/currency mismatch; duplicate/concurrent/out-of-order events; timeout and late capture; paid-but-not-activated recovery; one activation per order; competing purchases; partner revoked between QR and scan; one daily access across memberships; pause after QR issuance; legacy migration; empty/error/loading catalogs; keyboard/mobile cards; existing popup/cart/checkout regression.

Completion means real sandbox purchase -> verified payment -> membership -> eligible gym -> staff-validated check-in works end-to-end. Fixture UI success is not payment-provider or live-money sign-off.