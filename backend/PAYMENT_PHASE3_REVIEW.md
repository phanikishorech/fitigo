# Phase 3 payment integrity review — approved subset implemented

## Status

After the architecture review, the user explicitly approved: **admin test/live isolation and truthful cancellation/refund status only; defer wallet spending and gateway offers.** That subset is implemented. No Phase 3 environment, migration, provider-adapter, wallet-spending or working-database changes were made. See the implementation handoff at `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend/PAYMENT_PHASE3_IMPLEMENTATION.md` for final behavior, tests, files and limitations.

The financial decisions below remain unresolved for the deferred scope. The original full Phase 3 wallet/offer acceptance criteria are NOT complete. The architecture map and findings below describe the pre-implementation review; the implementation handoff supersedes the old admin-mode and cancellation findings for the approved subset.

Local configuration inspected without printing credentials: development environment, CASHFREE selected, test mode, gateway_required=true. Credential fields are populated, but no provider requests or real payments/refunds were executed. Credentials being present is not proof they work.

## Documented blockers

- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend/CUSTOMER_PAYMENTS_PROFILE.md`, lines 12–35: the prior INR 500 recharge/INR 450 payment and INR 150 cart/INR 100 payment each involved an INR 50 provider offer. Documentation requires a separately agreed promotion/accounting policy; it explicitly forbids bypassing the amount check or retrying those already-paid orders.
- The same document, lines 108–115: gateway-funded recharge does not authorize a new wallet-spending flow; spending was intentionally disabled and must not be advertised until confirmed. Test/live balances must not mix.
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend/MEMBERSHIP_WALLET_MVP.md`: the existing spending implementation is development test-credit-only, not an approved real-money wallet product. Refund/cancellation and funding policies are open release requirements.

## Flow and source-of-truth map

| Flow | Current authority / lifecycle |
| --- | --- |
| Provider selection | Backend settings select Razorpay/Cashfree for NEW attempts. PaymentCheckout persists provider, mode, key identity, source key, order ID, amount, currency and snapshot. |
| Gateway checkout | PaymentCheckoutService locks the customer, validates owned source and server pricing, persists intent before the external create-order call, and reconciles the original order after ambiguous outcomes. |
| Verification | Provider adapters fetch order/payment state; internal checkout amount/currency/reference must match. Browser redirects/callbacks are not payment authority. |
| Wallet recharge | Validated requested recharge amount becomes the internal order amount. Verified fulfillment credits WalletAccount and inserts a WalletTransaction linked uniquely to the checkout; repeat reconciliation does not credit again. |
| Wallet balance | WalletAccount.balance is the operational locked balance; WalletTransaction is the movement history. Legacy balances/entries must be reconciled rather than assumed fully verified or silently reclassified. |
| Wallet membership | Existing development-only service locks customer, plan/order and wallet; verifies current quote, eligibility and funds; debit, ledger entry and membership activation commit together. Unique purchase references prevent duplicate activation. Disabled whenever a gateway is selected. |
| Wallet booking | Legacy cart wallet endpoint locks cart/account, validates pricing and creates paid booking/payment/QR records in its transaction. It is explicitly blocked with gateway selection or outside development. It is not a drop-in verified real-money debit lifecycle. |
| Plan offers | PlatformMembershipOffer is a FitiGo catalog discount: active dates, fixed/percentage amount, capped/rounded backend final price, accepted quote and purchased snapshot. These offers reduce the internal order amount before gateway creation. |
| Gateway offers | Different from catalog offers. Successful payment amounts differing from the internal order become REVIEW_REQUIRED/PAYMENT_AMOUNT_MISMATCH. Normalized provider payment data does not represent an approved funding allocation, settlement receivable or promotional wallet bucket. |
| Membership activation | Persisted linked UserMembership requires paid/active/started/unexpired entitlement. Gateway fulfillment creates it in the verified transaction; daily QR issuance remains explicit through existing access services. |
| Booking / QR | Booking confirmation and Payment.PAID are written by fulfillment. BookingAccessService creates unique visitor access records and checks payment, booking status, visitor/window and usage before issuance/admission. Cancellation/refund revokes unused access. |
| Webhooks | Raw-body signature validation precedes lookup. Receipt deduplication plus customer/checkout locking invokes the same reconciliation path used by refresh. No independent webhook activation business logic. |
| Cancellation | Changes booking/access state; gateway payment stays PAID unless a provider refund is confirmed. No external refund initiation method exists in the provider contract. |
| Observed refunds | Reconciliation reads provider refund evidence. Full refunds revoke access and update statuses; partial refunds require review. Top-up reversals append incremental ledger debits exactly once. A refunded top-up that has already been spent can create debt under the CURRENT implementation. |
| Owner revenue | Existing shared projection uses explicit checkout mode, verified gateway linkage, INR and purchase-date filtering. Booking recognition also requires confirmed/non-no-show/successfully checked-in; group payment counts once using EXISTS. Single-Gym membership payment counts once without a visit. Wallet/legacy and Multi-Gym allocations are not recognized. |
| Admin revenue | Dashboard and daily booking report sum PAID booking amounts without explicit checkout mode filtering. Both require correction. Current documented admin date basis is scheduled booking date, distinct from owner purchase-date recognition. |

## Relevant implementation files inspected

- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend/app/services/payment_checkout_service.py`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend/app/services/payment_provider.py`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend/app/services/payment_providers.py`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend/app/services/razorpay_gateway.py`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend/app/services/razorpay_provider.py`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend/app/services/cashfree_provider.py`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend/app/services/wallet_gateway_service.py`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend/app/services/membership_wallet_service.py`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend/app/services/platform_membership_service.py`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend/app/services/booking_service.py`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend/app/services/admin_booking_ops_service.py`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend/app/services/admin_dashboard_service.py`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend/app/services/owner_revenue.py`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend/app/services/customer_payment_history.py`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend/app/services/booking_access_service.py`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend/app/routers/cart.py`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend/app/routers/admin.py`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend/app/models/wallet.py`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend/app/models/payment_checkout.py`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/frontend/src/pages/booking/CartPage.tsx`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/frontend/src/pages/booking/BookingDetailPage.tsx`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/frontend/src/pages/membership/MembershipOrderPage.tsx`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/frontend/src/pages/wallet/WalletPage.tsx`

## Confirmed issues to address after scope/policy approval

1. Wallet spending is blocked by explicit policy gates, not a Cashfree adapter failure. Removing those gates alone would expose legacy test-credit behavior and omit funding provenance, mode and reporting requirements.
2. Gateway-funded offer fulfillment lacks a financial rule and internal funding representation. Accepting any provider-reported discount would weaken exact verification.
3. Admin dashboard AND daily report lack test/live isolation. Unlinked legacy records cannot safely be classified as live by provider name or an assumed order prefix.
4. Customer, owner and admin legacy cancellation paths mark non-gateway/unlinked PAID payments REFUNDED without issuing a corresponding wallet credit. This is incorrect refund representation and must not be carried into a new wallet flow.
5. Existing owner reports exclude wallet-funded purchases. Enabling spending requires recognizing eligible purchases once while not also treating recharge as gym revenue.
6. Top-up refund after spending currently permits a negative balance to preserve debt. The new requirement that purchase debits cannot go negative is straightforward, but it must not silently erase this separate debt case. Its treatment needs confirmation if live wallet use is enabled.
7. Existing checkout binding retains original provider and rejects mode/key mismatches; it does not automatically recover orders across unavailable credential versions. Do not silently switch providers or recreate charges after timeouts.

## Decisions required (not inferred)

### Wallet funding and use

Confirm whether to enable FULL-wallet purchases for memberships and individual bookings under BOTH gateways using only verified same-mode gateway funds. Proposed conservative boundary: no split wallet+gateway payments, no promotional credit, no automatic conversion of legacy balances, and block inconsistent/unclassified ledgers pending explicit reconciliation. This is a proposal, not an approved policy or an implemented feature.

If live spending is approved, confirm treatment of recharge refunds after funds were spent: retain an explicit debt/restricted-wallet state, or prohibit voluntary recharge-refund initiation after spend while still recording externally imposed refunds/chargebacks. Neither approach can ignore verified external reversals. No auto-refund initiation is proposed without policy.

### Gateway-funded offers

For a nominal INR 500 recharge with INR 450 paid and INR 50 discount, specify:

- Which approved offer IDs/funders are allowed, eligibility and stacking rules?
- Is spendable credit INR 450 or INR 500? If INR 500, who funds the difference, and what provider evidence proves it is owed/settled?
- Is the difference refundable, transferable or restricted promotional credit?
- What amount is refundable to the customer and what happens to the subsidy on full/partial refunds?
- For memberships/bookings, is revenue gross list price or net customer consideration, and how is subsidy allocated to gyms?

Provider technical documentation can establish signature/payload verification, but cannot decide FitiGo's merchant contract, promotional liability or refund policy. Until approved, retain review-only handling and do not retry/recredit already-paid exceptions.

### Cancellation and reporting

The prompt permits keeping refund initiation unsupported: cancel access separately, report refund NOT_INITIATED unless provider evidence proves otherwise, and use an authorized provider-dashboard refund followed by reconciliation. This does not establish automatic refund eligibility.

Admin mode isolation can be fixed independently while preserving its documented scheduled-date basis and clearly labeling mode/exclusions. Owner purchase-date/check-in recognition should remain unchanged unless explicitly revised. This report does not silently choose a new revenue-recognition policy.

## Validation performed

Before the pause: **170 tests passed** across payment configuration, Razorpay, Cashfree, wallet gateway history, payment recovery, platform memberships, owner analytics and date-range reporting. On resumption: **34 focused tests passed** for payment recovery, configuration and wallet gateway history (overlapping subset, not 204 distinct tests).

These tests use isolated fixture databases and mocked providers; no gateway credentials were exercised and no working-database records were changed. No Phase 3 production-code changes were made, so frontend build/full regression/migration tests were not rerun for this review-only checkpoint. Existing test results are not proof of newly implemented wallet spending or offer support.

## Manual sandbox acceptance still required after implementation

For EACH provider using its own sandbox credentials and authorized test accounts:

1. Recharge success/failure/pending, duplicate/delayed signed webhook and browser refresh: one verified credit, zero on unsuccessful payment.
2. Full-wallet membership and booking purchase, insufficient funds, concurrent different purchases, same-request retries: at most one debit per purchase; no debit below available funds; no extra entitlement/QR.
3. Existing plan discount and stale quote; separately approved gateway offer, unapproved offer and currency/amount mismatch. Capture expected customer-paid, subsidy, wallet credit and revenue amounts before testing.
4. Interrupted create-order/callback and provider timeout: recover the original order, never initiate a replacement charge solely due to timeout.
5. Switch new-checkout provider while an earlier order is pending; old order must reconcile only through its original provider. Mode/key mismatch must fail closed.
6. Test/live reporting fixtures and selected/all-gym aggregation: no sandbox contribution to live revenue, no recharge-and-spend double counting, no group-scan multiplication.
7. Paid cancellation without refund: access revoked, payment history retained, refund not falsely marked complete.
8. Authorized SANDBOX provider-dashboard full/partial refund, pending/failed refund and repeated events: only confirmed amounts reflected, no duplicate reversal. Include spent top-up handling according to the approved policy.
9. Real raw-body webhook signatures, replay/out-of-order handling and rejected tampering; check that secrets/payloads are absent from logs.

No real charges/refunds or provider-dashboard changes were executed. The scope selection has since authorized the reporting/cancellation subset; additional wallet/offer work still requires policy approval.