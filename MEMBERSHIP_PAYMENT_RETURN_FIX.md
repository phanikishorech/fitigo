# Membership payment return and customer isolation

Local implementation, November 18, 2026. No deployment, application-server restart,
customer data reset, actual provider payment, payout, pricing/commission change or
financial gate activation.

## Findings

1. GatewayPayment labelled every created membership checkout's next action Resume,
   including a newly initiated purchase after SDK dismissal. Fresh purchases now
   use Continue payment; recovered records use Resume payment, and conflicting or
   expired-held recovery requires explicit Resume original membership consent.
2. The selected plan displayed its initial order response even after the payment
   child received PENDING/PAID. The child now reports updates to its parent. Only
   the exact matching order_reference updates that selected order's label.
3. Cashfree's configured return URL was the generic cart checkout. No exact payment
   return handler existed there, so a completed membership could return to an
   empty cart without a result.
4. Backend recovery is already user-scoped. No cross-user disclosure was reproduced.
   Added API regression proving another customer with their own new order sees no
   recovery record and cannot verify/read the first customer's checkout. Customer
   application state is also keyed by authenticated user ID as well as location.

## Return flow

Cashfree create-order now adds the exact payment_checkout_id to the configured
return URL, preserving other query parameters and replacing stale reference keys.
The return handler also recognizes legacy Cashfree fitigo_<UUID hex> order_id.
Malformed, duplicated and conflicting references fail closed. URL success flags
are not trusted.

The authenticated result page calls the existing verification/reconciliation API,
not checkout creation or cancellation. It shows the original purchase and amounts,
test/live indicator, confirmed/processing/review state, references and membership,
booking or wallet links. Pending results poll at five-second intervals for up to
12 checks; manual refresh remains available. No SDK is opened on return.

Before SDK launch, a one-hour, customer-scoped sessionStorage navigation hint stores
only user ID, checkout ID and timestamp. This supports previously created orders
whose provider return URL lacks a reference. The legacy return is normalized to an
explicit URL before terminal cleanup, so refresh keeps the payment result visible.
Storage failure is tolerated; backend ownership remains authoritative.

If an old return has no usable reference or tab hint, the empty cart exposes an
explicit recent-payment result selector. It never picks a payment automatically
or treats an empty cart as failure/success. Old provider orders were not rewritten.

Provider documentation reviewed:
`https://www.cashfree.com/devstudio/preview/pg/web/checkout`
Cashfree documents redirect to return_url with order_id and server-side transaction
status retrieval. The implementation follows that distinction: redirect is navigation,
not verified capture.

## Changed files

- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\services\cashfree_provider.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\tests\test_membership_payment_return.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\App.tsx`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\pages\CustomerApp.tsx`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\pages\profile\PaymentReturnPage.tsx`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\utils\paymentReturn.ts`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\components\common\GatewayPayment.tsx`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\components\membership\MembershipGatewayPayment.tsx`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\pages\membership\MembershipOrderPage.tsx`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\pages\booking\CartPage.tsx`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\scripts\paymentReturn.test.mjs`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\scripts\membership-recovery-browser.mjs`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\MEMBERSHIP_PAYMENT_RETURN_FIX.md`

## Validation

- Disposable MySQL: new customer/return regressions, Cashfree payments and membership
  recovery suites: **51 passed, 8 provider-specific skips**, exit 0, 239.16 seconds.
- Frontend: **508 passed**, zero failures; TypeScript and production build passed.
- Membership recovery/return browser: passed including fresh customer, live selected
  order status, original recovery, confirmed/pending/malformed/legacy returns,
  forged URL success flag, interrupted verification/retry, reload persistence and
  no SDK launch on return. Responsive checks include 1440, 768, 390 and 320 pixels.
- Cart and split-payment browser regressions: passed.
- The added verification-error browser assertion initially expected raw fixture
  error text; the API client correctly sanitizes HTTP 503 errors. Assertion updated
  to the stable customer safety message, and the full browser suite passed.
- Provider APIs/SDKs were mocked; actual customer payment outcomes and hosted mobile
  redirect behavior were not exercised. The owned disposable MySQL server stopped.
- Pre-existing datetime.utcnow warnings remain. Unrelated workspace edits preserved.

Artifacts:

- `C:\Users\ckishor\AppData\Local\Temp\fitigo-isolated-6450236770399ab8-3kkeomar\pytest.log`
- `C:\Users\ckishor\AppData\Local\Temp\fitigo-payment-return-unit-final.log`
- `C:\Users\ckishor\AppData\Local\Temp\fitigo-payment-return-types.log`
- `C:\Users\ckishor\AppData\Local\Temp\fitigo-payment-return-build-final.log`
- `C:\Users\ckishor\AppData\Local\Temp\fitigo-payment-return-browser-final.log`
- `C:\Users\ckishor\AppData\Local\Temp\fitigo-payment-return-cart-final.log`
- `C:\Users\ckishor\AppData\Local\Temp\fitigo-payment-return-split-browser.log`

The running application must load the updated backend and frontend. No deployment
or restart was performed in this task. The supplied screenshots alone do not prove
provider capture, and no claim is made that the actual customer's payment was paid.