# Expired checkout recovery

Booking eligibility and financial settlement are independent. An expired booking
can remain PENDING financially; it must not be reopened or silently replaced.

## Behavior

- Checkout responses include blocking reason, UTC booking deadline, booked items,
  immutable checkout amount, cart item IDs, and guarded cancellation eligibility.
- With active cart items, the checkout UI starts a fresh purchase for their exact
  IDs; old orders stay in collapsed history and are not polled in the background.
  The backend rejects changed/foreign/partial carts and the frontend refuses a
  response whose item IDs do not match the purchase being reviewed.
  Without new items, an existing checkout can still be resumed.
  An exact current-cart request opens the SDK on the first payment click after
  the returned item IDs are checked. Legacy requests without item IDs still
  require review. Retries reuse the checkout; double-clicks are locked.
- Background refresh updates eligibility even if financial status is unchanged.
- Local cancellation is allowed only before any order creation, or after provider
  reconciliation confirms a closed unpaid order without processing/paid attempts.
  Previously observed attempts are retained if a response is incomplete.
- Cashfree ACTIVE and TERMINATION_REQUESTED are not proof of closure. Only
  EXPIRED/TERMINATED plus verified attempt history qualify. An explicit current
  cart POST can reconcile and terminate old failed/expired Cashfree orders via
  PATCH /orders/{id}, then fetch order/payment status again. It creates a new
  checkout only after verified unpaid closure. Timeouts, pending termination,
  processing payments and recovered success do not create replacement orders.
  The per-user lock is held across recovery and creation to serialize tabs.
  Razorpay supplies no closed-unpaid evidence and is never falsely marked
  gateway-cancelled. For an expired/failed Razorpay cart, full order and attempt
  reconciliation can offer explicit replacement acknowledgment. The user must
  close old payment windows and confirm no deduction, acknowledging delayed
  payments remain possible. Processing, paid, unknown or incomplete attempts
  block this path regardless of acknowledgment.
  The old checkout becomes SUPERSEDED, linked to the replacement in snapshots;
  its bookings are cancelled locally and it can never be reopened/fulfilled.
  New payment launches recheck the replaced orders. A late success remains PAID
  in payment history but requires review without issuing duplicate access.
  This controls fulfillment, not the remote bank: duplicate charges cannot be
  ruled out if an old gateway window completes after the recheck.
- Legacy locally cancelled cart checkouts without verified closure block a new
  cart order. Reconciliation may resolve them; no historical rows are rewritten
  by migration. Gateway changes do not rebind an existing order.
- Current-cart creation revalidates existing price/time/availability rules and
  retains old checkout, booking and payment history. There is no background
  replacement, automatic charge, refund or extension of an old booking deadline.
  Repeated requests for the same consumed item IDs resume their existing order.

## Checkout presentation and capture boundary

The themed checkout shows booked visits, contact, total and provider separately;
technical references and history are collapsible. Financial review warnings stay
visible, and backend verification alone permits success navigation.

Launching payment still requires a future visit start. For an already captured
payment, fulfillment permits crossing the start boundary only if checkout was
created before the start, the original booking payment deadline has not expired,
the visit has not ended, and all existing availability/capacity/access checks pass.
This does not extend deadlines, revive cancelled bookings, or automatically
repair existing REVIEW_REQUIRED records. Both gateway adapters have regressions
for capture across start, expired deadlines, ended visits and cancellations.

## Deployment and checks

No schema migration or environment change is required. Deploy frontend/backend
together, restart the FitiGo backend on its configured port (locally 8001), and
reload the frontend. Do not restart the unrelated application on port 8000.
Installing this change does not resolve or cancel existing customer orders.
Submitting a fresh current-cart purchase can close verified unpaid old orders.

Run backend tests only via the fail-closed disposable MySQL runner, including
test_current_cart_checkout.py, test_checkout_expiry_recovery.py, test_cashfree_payments.py,
test_gateway_payment_recovery.py and test_razorpay_payments.py. Run frontend unit
tests, typecheck/build and checkout-recovery-browser.mjs; the browser script
intercepts all API and gateway traffic and uses an isolated browser context.