# Previous checkout recovery and wallet reservation safety

## Follow-up: original membership retry dead end (November 18, 2026)

The initial recovery implementation protected funds but left the same-plan retry
blocked forever after a local hold deadline. Added an explicit same-order resume
path; this is NOT cancellation or permission to buy a different plan.

- New owner-scoped POST `/payments/checkouts/{id}/resume-membership` reconciles
  current provider evidence under the customer/checkout locks. Only an expired,
  still-HELD Razorpay membership reservation with a payable verified-unpaid order,
  complete attempt count, no known processing/success/refund, and no cancellation
  intent qualifies for renewal. Eligibility and coverage of all reserved wallet
  amounts are checked. The same hold gets a new 15-minute retry deadline; its
  amount/state/resolution time, provider order and purchase snapshot are unchanged.
- Backend `can_resume_reserved_membership` exposes the action. UI requires explicit
  confirmation of original plan/total/wallet/online amounts before opening it.
  When another plan is selected, that plan stays selected and unpaid.
- Fresh late success returns PAID instead of reopening. Incomplete attempts,
  processing, cancellation intent and foreign ownership prevent this recovery.
- No customer records were manually reset. No deployment or server restart was
  performed. Running processes must load the updated backend/frontend code.
- Different-plan checkout remains blocked until authoritative original-order
  resolution. Finishing the monthly plan buys the monthly plan, not quarterly.

Additional changed files:

- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\routers\payments.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\tests\test_membership_reserved_resume.py`

Follow-up validation: 17 backend tests passed, 9 provider-specific skips; 505
frontend tests passed; TypeScript and production build passed. Responsive membership
browser passed including explicit consent, same provider order, no second checkout,
unchanged HELD reservation and unchanged selected quarterly price. Its initial new
Razorpay fixture lacked key_id; fixture corrected and browser rerun passed.
Provider SDK/API calls are mocked, not real customer payment verification.

Backend log: `C:\Users\ckishor\AppData\Local\Temp\fitigo-isolated-0ac817445253b763-qjp1j9hs\pytest.log`
Browser log: `C:\Users\ckishor\AppData\Local\Temp\fitigo-resume-browser-final.log`
Unit log: `C:\Users\ckishor\AppData\Local\Temp\fitigo-resume-unit.log`
Build log: `C:\Users\ckishor\AppData\Local\Temp\fitigo-resume-build.log`

Provider basis: Razorpay's official About Orders documentation describes multiple
attempts with one successful payment bound to the same order; paid orders reject
further payment requests. This supports same-order retry, not replacement/closure.
`https://razorpay.com/docs/payments/orders/`

The sections below record the earlier implementation and its validation.

Implemented locally November 18, 2026. No deployment, application-data reset,
provider payment/cancellation call, payout, pricing/commission change, financial
gate activation, new dependency, or database migration was performed.

## Provider investigation

Official documentation reviewed November 18, 2026:

- Razorpay Orders API: `https://razorpay.com/docs/api/orders/`
- Order update: `https://razorpay.com/docs/api/orders/update/`
- Late authorisation: `https://razorpay.com/docs/payments/payments/late-authorisation/`
- Webhook validation/idempotency: `https://razorpay.com/docs/webhooks/validate-test/`

The documented Razorpay Orders API exposes creation, retrieval, payment retrieval
and update. Its update request changes notes; it is not a cancellation API. No
documented authoritative unpaid-order closure operation was identified for the
existing integration. The adapter still rejects termination rather than inventing
a cancellation, deleting an order or treating a failed attempt as final closure.

Razorpay documents payments shown as Failed after timeout subsequently becoming
Authorized when the bank responds. Authorization is not capture. An unpaid order
and its failed attempt are not evidence that no future capture is possible.
Webhook deliveries can repeat and arrive out of order. No elapsed-time threshold
in this implementation proves provider closure.

Existing Cashfree integration requests termination and then re-fetches the order
and attempts. Only provider-confirmed unpaid closure, without known processing,
success or refund conflict, permits release. A termination request or HTTP timeout
is not closure. Automatic wallet-hold recovery now uses the same durable
cancellation-intent flow as customer cancellation.

**The example customer's provider record was not queried or modified.** Source
inspection, official documentation and isolated mocked-provider tests are not
live verification of that customer's payment. For the Razorpay example, retain
the INR 49 reservation, block a conflicting purchase and offer refresh/support.
Support must investigate authoritative provider evidence; closing a support
ticket is never financial authorization. No administrator force-release was added.

## Backend changes and preserved boundaries

- `present()` adds backend-derived `recovery_status`, `can_contact_support`,
  original membership `order_reference`, and a recorded `payment_reference`.
  These are owner-scoped through existing endpoints. No credential/session/signature
  is added to support metadata. Missing payment references are explicitly unavailable.
- Processing and payment-review states take priority over wallet timeout text.
- `close_unpaid()` refuses held-fund closure without safe provider evidence, except
  a locally CREATED checkout that has never started a gateway order. It also
  refuses paid/refunded/review-required/debited payment state.
- `funding.release()` refreshes and locks the funding row, checks cancellation,
  safe-closure evidence, processing flags and recorded conflicting attempts before
  changing HELD to RELEASED. Repeated release leaves the original resolution time.
- Checkout closure and reservation release share the caller's transaction. Existing
  user and checkout row locks serialize refresh/cancel/callback paths. No separate
  credit is inserted: a hold never debited the wallet balance in the first place.
- Split-provider refund reconciliation now retains a still-held wallet reservation.
  A refund is not proof of unpaid order closure. Already debited wallet transactions
  remain intact; the checkout stays review-required.
- The existing overlap guard, fixed funding split, quote validation, unique payment
  attempt/ledger identities, verified capture, webhook receipt deduplication and
  late-capture review protections remain in place.
- No financial transaction history is deleted or rewritten by this change. Existing
  payment-attempt reconciliation remains monotonic for success/refund evidence.

## Transaction-state transitions

| Evidence / event | Checkout recovery | Wallet reservation | New conflicting checkout |
| --- | --- | --- | --- |
| Failed attempt, expired local reservation, no closure proof | RESOLUTION_REQUIRED | HELD | Blocked |
| Known pending/authorized processing payment | PROCESSING | HELD | Blocked |
| Cancellation requested/pending or request timeout | CANCELLATION_PENDING | HELD | Blocked |
| Provider confirms unpaid closure; no conflicting attempt | SAFELY_CLOSED / CANCELLED | RELEASED once | Allowed after explicit current-plan/quote review |
| Verified matching capture while original hold remains | PAID if fulfillment succeeds | DEBITED once | No duplicate purchase; membership eligibility still applies |
| Capture after safe closure/release | REVIEW_REQUIRED | Remains RELEASED; no new debit | Blocked by overlap/reconciliation guards |
| Amount mismatch, refund conflict, fulfillment failure | REVIEW_REQUIRED | Preserve existing funding state | Blocked |
| Support ticket created/replied to/resolved | No payment transition | Unchanged | Unchanged |

Locally unstarted CREATED checkouts are the narrow no-provider-order exception:
there is no ambiguous create attempt. CREATING timeouts are not that exception.

## Customer and support experience

- The selected membership and current price are separate from previous payment
  recovery. NOT_STARTED is displayed as "Not started for this plan". Selected
  order IDs are collapsed into order details.
- Previous checkout shows original plan, one total/wallet/online breakdown, one
  recovery explanation, and a visible test/live indicator. Technical references,
  provider and recorded raw status are inside expandable Payment details.
- Resume and cancellation are offered only using backend capability flags. An
  unavailable Razorpay closure is not advertised as cancelable. Refresh remains
  available; support is controlled by the backend recovery capability.
- Another tab's original Multi-Gym order returned during creation is not
  automatically opened when it differs from the reviewed order.
- Safe closure requires an explicit "Review plan and payment method" action.
  It reloads the existing selected plan/quote and remounts funding selection to
  fetch the available balance. No selected plan or accepted amount is silently changed.
- Contact support reuses existing support availability, ticket creation,
  idempotency, authorization and conversation workflows. Prefill contains checkout,
  original order, provider order, recorded payment reference, purchase/wallet/gateway
  amounts and recovery state. It is an explicit allowlist, not serialized checkout
  data. Support form submission has no payment-release capability.
- Support-disabled deployments remain explicit: no ticket is claimed as submitted;
  existing configured support contact information is shown when available.
- Responsive layouts were checked at 1440, 768, 390 and 320 CSS pixels.

## Changed files (this task)

All paths are absolute; pre-existing unrelated workspace changes were preserved.

Backend:

- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\services\payment_checkout_service.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\services\checkout_funding.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\services\wallet_hold_recovery.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\tests\test_payment_recovery_safety.py`

Frontend:

- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\services\paymentService.ts`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\utils\paymentRecovery.ts`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\components\common\GatewayPayment.tsx`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\components\common\SupportContact.tsx`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\components\common\SupportRequests.tsx`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\components\membership\MembershipGatewayPayment.tsx`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\components\payments\PaymentRecoveryPanel.tsx`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\components\payments\paymentRecovery.css`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\pages\membership\MembershipOrderPage.tsx`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\scripts\paymentRecovery.test.mjs`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\scripts\membership-recovery-browser.mjs`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\scripts\checkout-recovery-browser.mjs` (null-safe initial navigation wait only)

Report:

- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\PAYMENT_RECOVERY_IMPLEMENTATION.md`

## Validation record

Frontend: 504 tests passed; TypeScript passed; production Vite build passed.
Membership recovery browser and existing split-payment browser passed with API/SDK
mocking in isolated browser storage. Coverage includes provider-unavailable expired
hold, fixed split, conflicting plan, pending cancellation, confirmed closure,
balance refresh, distinct replacement key, discovery failure, support prefill and
submission, hidden details, visible test mode and responsive overflow checks.

Backend runs use the existing disposable-MySQL runner with mocked gateway
transports and no application .env credentials. An initial support regression failed because the booking
fixture had no administrator; the test now creates a disposable administrator.
One follow-up invocation used a nonexistent expiry test filename and exited during
collection; it was replaced by the correctly named expiry-recovery suite.

Final results:

- Final payment safety/membership recovery/expiry/split-payment run: **85 passed,
  11 skipped**, exit 0, 947.19 seconds. Skips are provider-specific scenarios
  (Cashfree termination against Razorpay; the Razorpay-specific refund fixture
  against Cashfree), not waived failures.
- Separate existing support workflow suite: **11 passed**, exit 0.
- Earlier corrected recovery/expiry run: 38 passed, 10 skipped. This preceded
  the final automatic-cancellation change and is not counted as final coverage.
- The initial broad run hit its 900-second bound after the known two support
  fixture failures; it is not a passing run. The final bounded run used 1200 seconds.
- Final frontend unit run: **504 passed**, zero failures. TypeScript and production
  build passed. No application code changed after these frontend validations.
- Membership recovery, split-payment and additional cart-recovery browser suites
  passed. The latter initially failed on a null document.body during navigation;
  its initial wait is now null-safe, with its behavioral assertions unchanged.
- All owned disposable database servers were stopped by their runners. Existing
  datetime.utcnow deprecation warnings remain outside this task's scope.

Private artifacts:

- Final backend: `C:\Users\ckishor\AppData\Local\Temp\fitigo-isolated-9b967449dcfb7d9e-i64wh9pc\pytest.log`
- Final backend JUnit: `C:\Users\ckishor\AppData\Local\Temp\fitigo-isolated-9b967449dcfb7d9e-i64wh9pc\results.xml`
- Support: `C:\Users\ckishor\AppData\Local\Temp\fitigo-isolated-14dfc5ec341a8ff7-v2u0h23f\pytest.log`
- Frontend units: `C:\Users\ckishor\AppData\Local\Temp\fitigo-recovery-final-unit.log`
- Types: `C:\Users\ckishor\AppData\Local\Temp\fitigo-recovery-final-types.log`
- Build: `C:\Users\ckishor\AppData\Local\Temp\fitigo-recovery-final-build.log`
- Membership browser: `C:\Users\ckishor\AppData\Local\Temp\fitigo-recovery-final-browser.log`
- Split browser: `C:\Users\ckishor\AppData\Local\Temp\fitigo-recovery-split-browser.log`
- Cart browser: `C:\Users\ckishor\AppData\Local\Temp\fitigo-recovery-cart-browser-final.log`

## Remaining limitations

- No safe unpaid Razorpay order-closure API was identified for this integration.
  This implementation cannot promise to unlock that checkout through support.
  It retains the reservation until authoritative reconciliation allows a safe
  transition. Support ticket resolution alone is deliberately insufficient.
- Hosted provider calls, actual customer payment state, physical mobile devices,
  and real webhook delivery were not tested. Browser/provider scenarios are mocks.
- No migration or deployment was run against the working database. Backend and
  frontend contract changes must be released together in a separately authorized
  deployment. This task stops at local implementation and validation.