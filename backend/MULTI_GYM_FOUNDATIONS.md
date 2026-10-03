# Multi-Gym foundations: implemented contract and operations

**Superseded payment state:** the later authorized controlled wallet MVP is implemented and locally migrated. See `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\MEMBERSHIP_WALLET_MVP.md` for the current checkout/activation contract. The foundation-stage notes below describe the earlier payments-disabled milestone, not current development wallet capability. External payments remain disabled.

## Scope

Implemented catalog, backend pricing/offers, audited admin configuration and customer-owned unpaid order reviews. There is no gateway adapter, wallet charge, payment success simulation, platform membership activation, partner enrollment or new access entitlement. Existing Single-Gym, cart and QR implementations are unchanged.

Four additive tables: platform_membership_plans, platform_membership_offers, platform_membership_orders and platform_membership_audit. This avoids nullable gym-reference migration and legacy entitlement changes in a payments-disabled phase. A later explicit entitlement integration is required before sales can be enabled.

## Actual endpoints (prefix /api/v1)

| Method and route | Access | Behavior |
| --- | --- | --- |
| GET /memberships/plans?membership_type=MULTI_GYM | Public | Active plans ordered by display_order, then ID; server_time and checkout_available=false |
| GET /memberships/plans/{plan_id} | Public | Current active plan and authoritative pricing; 404 for missing/inactive |
| POST /memberships/orders | Active CUSTOMER | Body contains only plan_id; Idempotency-Key header required, 8–64 letters/digits/underscore/hyphen |
| GET /memberships/orders/{order_id} | Owning CUSTOMER | Immutable selected-plan snapshot plus freshly priced current_plan and requires_review |
| POST /memberships/orders/{order_id}/payment-session | Owning CUSTOMER | Always 409 PAYMENT_NOT_CONFIGURED; no side effects |
| GET /admin/membership-plans | ADMIN / SUPER_ADMIN | Includes inactive plans |
| GET /admin/membership-plans/{plan_id} | ADMIN / SUPER_ADMIN | Full saved offer configuration, including scheduled/expired/disabled, current price and server time |
| POST /admin/membership-plans | ADMIN / SUPER_ADMIN | Create validated configuration, audit transaction |
| PUT /admin/membership-plans/{plan_id} | ADMIN / SUPER_ADMIN | Full replacement with expected_version; conflict on stale version |
| PUT /admin/membership-plans/{plan_id}/offer | ADMIN / SUPER_ADMIN | Configure/disable one offer per plan with expected_version; no offer stacking |

No payment amounts, discounts, user IDs or payment statuses are accepted in customer order bodies. Unknown fields are rejected. Order reads verify ownership. Plan codes and customer-scoped idempotency keys have database unique constraints. Customer and plan locks serialize order creation on databases supporting SELECT FOR UPDATE. Idempotency-key reuse for a different plan is rejected.

Every order reports status=PAYMENT_DISABLED, payment_status=NOT_STARTED, eligibility_status=NOT_EVALUATED, payment_available=false and membership_id=null. Choosing a plan does not evaluate or promise future purchase eligibility, reserve pricing, debit money or create gym access. The snapshot remains unchanged; current_plan is null after withdrawal. No order expiry or payment acceptance window is invented in this review-only phase.

## Pricing/configuration contract

Create/update plan fields: code, name, optional description, duration_value, duration_unit (DAY/MONTH/YEAR), base_price, currency, benefits, optional badge, display_order and is_active. Updates also require expected_version. All new plans default inactive unless explicitly activated. INR is the only configured currency; unsupported currencies are rejected rather than guessing rounding/FX. Display uses the response currency.

Money is validated as finite non-negative decimal with at most two fractional digits and stored as NUMERIC(12,2). JSON responses serialize decimal strings. Offer value must be positive; percentages cannot exceed 100. Percentage discounts use Decimal ROUND_HALF_UP to two places. Fixed discounts and computed percentage amounts are capped at base price, so final_price never becomes negative. A single configured offer per plan avoids implicit stacking. Changing any configuration increments the plan version and creates an audit row in the same transaction.

Offer fields: kind (FIXED/PERCENTAGE), value, optional title, starts_at, ends_at and is_active. Timezone-qualified input is required, storage is naive UTC to match MySQL conventions, API timestamps are UTC-aware. Active window is starts_at <= server time < ends_at. Outside the window the response has offer=null, discount_amount=0, discount_percentage=null and final_price=base_price. Percentage display is the configured percentage; fixed discounts expose an amount, not an invented percentage. Offers that round to zero do not create a promotion badge.

Catalog response includes base_price, discount_amount, final_price, discount_percentage, offer, benefits, badge, duration and backend ordering. The fixed product rule (one daily access to eligible partners) is reported by the backend. pause_rule=null because pause allowance enforcement is not included. purchase_available=false is not an environment toggle; no configuration edit can turn on checkout.

## Optional initial backend configuration

`C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\config\multi_gym_plans.json` contains the four user-requested initial plan names, prices, month durations and display order. No offers, badges or pause limits were invented. This is server configuration, never bundled into production frontend assets.

The import command validates all input first and defaults to a dry run with no database access. Apply requires an existing active ADMIN/SUPER_ADMIN ID. Existing plan codes are skipped, never overwritten, so rerunning does not reset operator price changes. Each creation is audited and committed; an interrupted batch can be rerun safely for missing codes. Ongoing edits can now use **Admin > Membership Plans** at `/admin/membership-plans`, including plan editing, visibility and offer scheduling/disable controls. All writes reuse the versioned admin APIs and audit behavior.

## Local development deployment status

The reported HTTP 500 was reproduced directly on port 8000 and through the frontend proxy on port 5173. The local development database was still at revision `2a7d0b9c9a11` and all four platform tables were absent.

After confirming the configured environment was development and the database host was local, revision `3b8e1c2d4f60` was applied. Existing user, membership, booking and wallet-transaction counts were checked before/after and remained unchanged. The approved four-plan configuration was imported with the existing active administrator (ID 3); a second run created zero records and skipped all four existing codes.

Both live endpoints now return HTTP 200 with the four configured INR prices and `checkout_available=false`; every plan still reports `purchase_available=false`. No payment, order, membership activation or offer was created during this repair. This verifies the local catalog deployment, not production readiness or an authenticated purchase flow.

## Deployment procedure for other environments

1. Review and back up the target database. Test the migration on an isolated MySQL database with the deployment version; SQLite tests do not verify MySQL lock/concurrency semantics.
2. Review the backend's configured database/environment privately; never print credentials to logs or paste secrets into chat.
3. Apply the additive Alembic migration before routing traffic to the new catalog page.

```powershell
Set-Location 'C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend'
& '.\.venv\Scripts\python.exe' -m alembic upgrade head
& '.\.venv\Scripts\python.exe' -m app.scripts.import_platform_membership_plans --file 'C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\config\multi_gym_plans.json'
```

4. Set FITIGO_ADMIN_ID to the intended existing administrative user's ID in the shell, then explicitly apply the approved configuration:

```powershell
& '.\.venv\Scripts\python.exe' -m app.scripts.import_platform_membership_plans --file 'C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\config\multi_gym_plans.json' --apply --admin-id $env:FITIGO_ADMIN_ID
```

5. Restart/deploy the backend and frontend together, verify public catalog and authenticated order review, and verify payment-session requests still return PAYMENT_NOT_CONFIGURED. Without the import/admin-created plans, the real catalog is empty. Without the migration, the API fails; the frontend shows retry, not fake plans.

Do not run downgrade casually: it deletes catalog/order/audit history. Roll back application traffic first and use reviewed backup/repair procedures.

## Validation completed

- Isolated SQLite tests for pricing boundaries/rounding, configuration roles/validation/version conflicts, audit, active ordering, inactive plans, ownership, idempotency, amount injection rejection, current-price refresh and payment blockade.
- Existing isolated access regressions remain green.
- New migration upgrade/downgrade runs against disposable SQLite; MySQL offline migration SQL compiles. The additive migration was subsequently applied to the local development MySQL database as documented above.
- Backend configuration dry-run validates four plans without DB access.
- Frontend unit tests, TypeScript and production build; isolated browser network fixtures cover desktop/mobile, discounts, empty/error/loading, offer expiry, order review, unavailable plans and duplicate clicks. No production mock data.

## Remaining release gates

Provider selection, sandbox integration, verified events/reconciliation, immutable payment acceptance semantics, exact duration/start/expiry and overlap policies, taxes/fees, pause enforcement, explicit partner eligibility, legacy entitlement migration, production authentication/top-up/dummy-purchase hardening, abuse rate limiting, retention policy and MySQL concurrency tests remain open. In particular the legacy dummy membership purchase and unverified wallet top-up are pre-existing risks, not safe fallbacks for platform payments. Do not enable real-money sales until these are resolved.