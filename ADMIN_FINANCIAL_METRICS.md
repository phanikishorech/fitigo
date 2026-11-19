# Admin financial position and analytics

## Agreed scope

The user selected: **Implement all verifiable metrics now; show unsupported metrics
as Not configured and document the remaining requirements.** This is not a new
accounting/settlement engine and does not invent historical facts or contract terms.

The prior dashboard's “Booking revenue” summed paid gateway booking allocations
by **scheduled booking date**, including cancelled/no-show bookings. It did not
require check-in. That card and its use in the main admin pages are replaced.

## Implemented UI

Existing Dashboard, Analytics and Reports routes/sidebar items are reused. The
existing admin font, green/white tokens, cards, buttons, header and sidebar remain.

- Dashboard: current total users/active gyms, completed visits, future verified
  bookings, recognized revenue availability, current customer wallet liability;
  revenue categories; booking outcomes; wallet financial health; expandable
  operations metrics and successful visit trend.
- Analytics and Reports share eight sections: Revenue, Payments, Wallet, Booking
  & attendance, Memberships, Gyms, Customers, Settlements.
- Existing date picker: Today, Yesterday, This week, This month, Last 30 days,
  Custom (maximum 366 days). Gym, funding source and test/live selectors are shared.
- Backend-supplied line charts, booking distribution bars, exact chart-data tables,
  gym breakdowns, plan popularity, filterable/paginated wallet ledger, CSV report.
- Unknown policy-dependent balances are **Not configured**, not zero. A wallet
  reconciliation failure is **Unavailable / Review required**, not a guessed liability.
- Identifiable financial detail is admin-only; ledger/most-active lists use account
  IDs rather than customer email/phone or gateway secrets. CSV escapes formula cells
  through the existing analytics CSV utility.

## Shared backend / API contracts

All endpoints require ADMIN or SUPER_ADMIN and return `Cache-Control: no-store`.
They perform SELECTs only, never reconcile providers, confirm bookings, credit a
wallet, or initiate settlement/refund/payment operations.

1. Reused `GET /api/v1/admin/dashboard/summary?financial=true`.
2. Reused `GET /api/v1/admin/analytics?financial=true`.
3. Added `GET /api/v1/admin/reports/financial`.
4. Added `GET /api/v1/admin/reports/wallet-ledger`.

The first three return exactly the same financial response for identical filters
(apart from generation time). The UI always requests this financial contract.
Filters: `date_from`, `date_to`, optional positive `gym_id`, `mode=test|live`,
`source=RAZORPAY|CASHFREE|WALLET`. The ledger uses dates, mode, direction, transaction
type, limit (max 100), and offset. Mode defaults to the configured payment mode.

Explicit source/mode filters never silently fall through to an all-mode legacy
report. Location filters on the new financial contract are rejected; gym attribution
is supported, but historical location accounting is not inferred.

Compatibility:
- Old dashboard response shape remains for callers without financial filters;
  its `revenue.in_period/last_30d` now mean **verified attended gross booking value
  by first check-in date**, with an explicit basis and null recognized platform total.
- Old `/admin/analytics` without the financial contract and
  `/admin/reports/bookings/daily` remain **legacy scheduled-booking audit** APIs.
  Their `paid_amount` fields are not earned revenue or capture-date cash, are not
  used by the redesigned financial pages, and must not be added to new totals.
  Existing external consumers must opt into the new contract. Legacy manual
  attendance fields are audit data, not the new validated visit measures.

## Evidence and metric definitions

All money aggregation is backend SQL/Decimal, never frontend arithmetic. The
browser converts values only to chart coordinates or formats amounts.

### Booking evidence

Require a fulfilled PAID internal checkout in the selected mode and INR. A positive
gateway contribution requires a matching SUCCESS PaymentAttempt with correct
external payment reference, currency and amount, no refund, and no conflicting
successful attempt. Wallet funding requires the committed checkout-linked OUT /
PAYMENT transaction matching user, currency, amount and DEBITED funding state.

Booking payment must equal the booking's authoritative full purchase amount.
Checkout/cart booking sums and explicit wallet/gateway booking allocation sums
must reconcile; never assign the full cart value to each booking. Unsupported,
unlinked legacy/DUMMY funding does not become revenue by assuming a mode.

### Attended booking value and visits

- A valid admission requires SUCCESS check-in, matching booking/customer/gym/visitor
  index and QR source, inside the recorded QR validity interval. Manual ATTENDED is
  not admission evidence. Cancelled/no-show bookings are excluded.
- **Attended gross booking value** = sum of each eligible booking's full verified
  purchase amount once, on its **first valid visitor check-in date**.
- The existing product's whole-booking/first-admission convention is retained:
  a group booking's amount is not multiplied by scans or visitors. If recognition
  must instead be per consumed group place, that is a separate policy decision.
- **Completed visits** = distinct successful purchased visitor admissions plus
  distinct membership daily-access admissions, not raw QR scan counts.
- Membership visits never create another membership sale or allocate the entire
  Multi-Gym sale to visited gyms. Historical transferred-membership admissions use
  daily-access identity rather than rewriting the past purchaser.
- **FitiGo retained/net revenue** and **total recognized platform revenue** remain
  null: gross service value is not proof of the platform's principal/agent treatment
  or its contractual share.

### Booking outcomes / no-show

- Outcome counts use scheduled-date cohorts in selected payment mode. Upcoming is
  verified paid, future start, unscanned and not marked no-show.
- Attended cohort count requires a valid check-in. Confirmed includes attended and
  no-show states; it is not an additional earned category. A past unscanned booking
  is not automatically marked no-show.
- Cancellation rate = cancelled / all scheduled cohort bookings.
- No-show rate = explicitly no-show / (attended + explicitly no-show).
- **No-show gross forfeited amount** = full verified value for confirmed paid
  no-shows with no successful scan, grouped by `attendance_marked_at`.
- Existing locked owner no-show mutation rejects repeat/conflicting processing;
  reporting is read-only and cannot add another recognition event on refresh.
- No-show retained platform income and owner share are null until contracts exist.
- Refunded/partially-refunded/review-required bookings are excluded from attended
  value; original payment/attempt/refund history remains visible separately.

### Gateway collections and dates

Existing payment attempts contain `first_seen_at` and mutable `updated_at`, **not
authoritative capture/refund event timestamps**. Therefore:

- Date-filtered gateway/membership collection totals are unavailable.
- The payments section shows **undated verified provider evidence, all dates**, in
  the selected environment/provider, separately from date-filtered operations.
- Gross collected = sum of successful/refunded/partially-refunded provider attempt
  amounts; refunds = recorded cumulative refund amounts once per attempt; recorded
  net = gross minus recorded refunds. Pending/failed attempts contribute zero cash.
- A collected payment that failed fulfillment remains cash evidence, not revenue.
- Repeated provider transaction IDs across checkouts are excluded and flagged,
  not double-counted. Amount/refund mismatches are flagged for review.
- Attempt counts and success rate use the **first-observed cohort and current
  reconciled status**, explicitly not capture-date payments.
- Gateway collection from a mixed-gym cart is not attributed wholesale to one gym.
  Provider-cash metrics are unavailable under a gym or Wallet filter.
- Gateway fees are unavailable; no gross percentage or guessed charge is used.
- Wallet-funded completed purchase value uses committed wallet-debit resolution
  date and is not added to gateway collections.

### Memberships

- Separate Single-Gym and Multi-Gym verified sale counts/value at **entitlement
  creation date**, not guessed capture date or automatic recognition date.
- Require matching checkout funding and entitlement paid amount/currency/type.
  A different current owner requires completed transfer evidence from the original
  purchasing user; transfer does not duplicate sale value.
- Single-Gym sales belong to the entitlement gym. Multi-Gym sales remain platform
  sales and are excluded from selected-gym sales (no allocation method exists).
- Current active counts respect start/end, payment evidence, status and active pause
  periods. Expiring/expired inventory and completed transfers are separate.
- Membership recognized revenue remains null. Renewal lineage is not recorded and
  another purchase is not guessed to be a renewal.

### Wallet liability

- Current ledger net per account = sum(IN) − sum(OUT), including recorded payment
  and reversal/adjustment entries. Credits alone are never the liability.
- Compare ledger net to stored wallet balance **per account**, validating currency,
  user, directions and nonnegative amounts/net. Opposite account mismatches cannot
  cancel each other out to produce a falsely reconciled platform total.
- Reconciled outstanding liability = sum of mode-classified ledger nets. If any
  classified account fails reconciliation, authoritative liability is null while
  recorded/ledger totals and mismatch counts remain visible for review.
- Holds do not remove liability: reserved value is still owed to the customer.
  A completed wallet debit decreases wallet liability, but does not by itself earn
  booking revenue; check-in is still required.
- Period movement equation: opening ledger balance + credits − debits = closing
  ledger balance. Current liability is not restricted to transaction-date filter.
- Cancellation credits are classified from the existing transaction type.
  Booking/membership spending is classified by durable checkout/entitlement links;
  ambiguous historical spending remains explicitly unallocated.
- Unknown-mode wallets are excluded from test/live totals and shown as an
  unclassified balance, not assumed production value.
- Wallet liability is platform-wide. It is unavailable under a gym or gateway
  source filter because remaining credit-origin consumption is not tracked.
  CSV uses “Not attributable” rather than false zero movements in those views.
- Promotional/adjustment/expiration policy is absent. Actual recorded transaction
  types are visible, but no unsupported business meaning is invented.
- Remaining liability by original credit source and age is unavailable: the ledger
  does not link debits to credit lots. No FIFO/LIFO assumption is introduced.

### Owner payable and settlements

No agreement, commission, owner allocation, payout, settlement, or adjustment model
exists in the inspected schema. All requested payable/settlement metrics are null
with a reason. There is no new payout UI, fake zero payout history or default share.
Payment source (wallet versus gateway) is separate from contractual allocation;
one booking never becomes two owner entitlements because it is split-funded.

### Customer / gym analytics

- New customer registrations use CUSTOMER role and registration date, platform-wide.
- Active accounts have a valid visit in range; repeat accounts have more than one.
- Retention = previous equal-length visiting cohort returning this period / previous
  cohort. It is unavailable with funding-source filtering rather than mixing cohorts.
- Group guest visits remain attributable to the purchasing account; this is not
  unique guest retention. Most-active lists expose account IDs and counts only.
- Membership conversion requires a defined funnel/cohort window and is unavailable.
- Gym performance shows visits, attended value and Single-Gym sale value. Utilization
  is unavailable until capacity/time denominators are agreed; rankings use visits.
- Catalog current active/pending gyms and user totals are labelled current, not
  historical inventory at the end of the selected range.

## Reconciliation examples

| Event | Gateway evidence | Attended booking value | Wallet liability movement | Owner share |
|---|---:|---:|---:|---|
| INR 150 gateway-funded booking, confirmed only | +150 (undated if capture time missing) | 0 | 0 | Not configured |
| First valid admission to that booking | no new cash | +150 once | 0 | Not configured |
| Eligible INR 150 cancellation before admission | original cash retained | 0 | +150 credit | Not configured |
| INR 40 wallet + INR 110 gateway, confirmed | +110 | 0 | −40 debit | Not configured |
| First valid admission to split purchase | no new cash | +150 once (wallet subset 40) | no additional debit | Not configured |
| Confirmed paid no-show INR 150 | no new cash | 0; no-show gross 150 separately | 0 | Not configured |
| Multi-Gym sale INR 1000 followed by visits at two gyms | one sale/collection | no booking value | debit only if wallet funded | No Multi-Gym gym allocation |

No claim is made that attended gross value is FitiGo profit or that wallet deposits
are earned income. These are operational financial evidence projections, not a
closed-period general ledger. Later refunds/corrections can change current-state
eligible historical value; immutable reversal journals are not yet implemented.

## Proposed backward-compatible data additions (NOT applied)

No migration is necessary for this read-only phase. Current schema remains
`c35d6fa89157`. No customer/payment/attendance/settlement rows were changed for tests.

For a future approved accounting phase:

1. **Capture/refund timing evidence:** nullable authoritative capture timestamp,
   timestamp source, verified observation timestamp and actual fee fields linked
   to existing provider attempts; unique refund-event identities and timestamps
   rather than mutable cumulative refund totals alone. Populate only from verified
   provider evidence; historical nulls remain null unless explicitly reconciled.
2. **Effective-dated agreements:** gym/owner, signed agreement reference, applicable
   booking/membership/no-show allocation rules, tax/fee base, rounding rule and
   effective interval. No default percentages. Validate no overlapping active rules.
3. **Immutable allocations / reversals:** unique source event + agreement version,
   gross, owner share, platform share, recognition date/currency/environment.
   Reversals reference original allocations. Missing contracts block posting.
4. **Settlements:** idempotent payout references, actual transaction dates/status,
   currency/mode, owner/gym, linked settled allocation rows and audited adjustments.
   Approvals, failed/reversed payouts and reconciliation must be defined first.
5. **Membership recognition:** approved recognition method, performance-obligation
   start/end, treatment of pauses/transfers/refunds/tax, and explicit Multi-Gym
   allocation policy. Preserve existing entitlement identity; no duplicate sale.
6. **Wallet credit-consumption evidence:** credit lots with origin/mode/expiry and
   debit-to-credit allocations under an approved FIFO/LIFO/proportional policy.
   Backfill only where provable; otherwise maintain an unknown-origin opening lot
   explicitly approved by accounting, not a fabricated recharge.

These are proposals, not deployed tables or working settlement functionality.

## Tests and validation

- New tests run on disposable MySQL (including strict ONLY_FULL_GROUP_BY) with
  mocked Razorpay/Cashfree. Working DB was not used as a test fixture.
- Covered confirmed exclusion; valid admission once; cancelled exclusion and wallet
  credit; net wallet liability/debit; split attendance and funding; no-show separate
  and duplicate processing rejection; pending/failed/unverified exclusion; refunds;
  duplicate provider IDs; modes; exact IST day boundaries; first-check-in date;
  membership sale/visit nonduplication and Single/Multi gym attribution; admin-only
  scope; matching dashboard/analytics/report responses; SQL read-only enforcement.
- Unsupported contractual payable/retention policies are tested as null, not tested
  against invented contracts. Settlement reconciliation cannot be tested without
  settlement records; this is an explicit unresolved requirement.
- Targeted existing/new reporting suite checkpoint: **91 passed**.
- Full regression checkpoint: **912 passed**, zero failed, in 780.49 seconds.
  Log: `C:\Users\ckishor\AppData\Local\Temp\fitigo-isolated-03609b4fc92fd03f-_lnbjlod\pytest.log`.
  This run started before the final financial-filter refinements and five additional
  tests. The final affected financial suites were rerun after those changes:
  **34 passed**, zero failed, in 85.14 seconds.
  Log: `C:\Users\ckishor\AppData\Local\Temp\fitigo-isolated-f2866b3e1f6e6780-5qffzobu\pytest.log`.
  Both runners exited 0 and stopped their owned disposable servers. Do not interpret
  these as 946 distinct tests or a second full-suite run on the final snapshot.
- Existing datetime deprecation warnings remain (35,607 warnings in the full run).
- Frontend checkpoint: **451 passed**, TypeScript passed, production build passed.
- New mocked browser regression passed all eight analytics sections, dashboard,
  Reports, wallet ledger, unknown states, filters, CSV, error handling, 360/768/1440px.
- A read-only transaction against local data completed without writes. At that
  observation: attended value 0.00, three cancelled scheduled bookings, reconciled
  wallet liability 200.00. Policy-dependent metrics were Not configured. This was
  a live-data smoke observation, not a seeded test or immutable historical report.
- All 18 changed source/test files were checked for existence, nonempty content,
  conflict markers and Python AST parsing. Browser/unit script syntax checks passed.

Commands executed from `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend`:

```powershell
.\.venv\Scripts\python.exe scripts\run_isolated_tests.py --mysql-bin 'C:\Program Files\MySQL\MySQL Server 26.7\bin\mysqld.exe' --test-timeout 3600 tests -q
.\.venv\Scripts\python.exe scripts\run_isolated_tests.py --mysql-bin 'C:\Program Files\MySQL\MySQL Server 26.7\bin\mysqld.exe' --test-timeout 900 tests/test_admin_financial_position.py tests/test_admin_financial_gateway_reconciliation.py -q
```

Commands executed from `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend`:

```powershell
npm test
npm run typecheck
npm run build
node scripts\admin-financial-browser.mjs
```

The new browser suite covers the redesigned financial pages. The older
`C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\scripts\admin-analytics-browser.mjs`
targets the retired location/cohort UI and is not evidence for these new pages.
Its old nonfinancial backend audit APIs remain available for compatibility.

## Files changed

Backend:
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\services\admin_financial_queries.py` (new)
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\services\admin_financial_service.py` (new)
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\services\admin_dashboard_service.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\routers\admin.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\tests\test_admin_financial_position.py` (new)
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\tests\test_admin_financial_gateway_reconciliation.py` (new)
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\tests\test_admin_financial_integrity.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\tests\test_admin_financial_mysql.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\tests\test_dashboard_date_ranges.py`

Frontend:
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\admin\Dashboard.tsx`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\admin\Analytics.tsx`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\admin\Account.tsx` (Reports branch)
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\admin\FinancialOverview.tsx` (new)
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\admin\financialService.ts` (new)
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\admin\financial.css` (new, admin financial pages only)
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\scripts\admin.test.mjs`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\scripts\admin-financial.test.mjs` (new)
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\scripts\admin-financial-browser.mjs` (new)

Report: `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\ADMIN_FINANCIAL_METRICS.md`.
Frontend evidence: `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\financial-unit-results.txt`,
`C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\financial-build-results.txt`,
`C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\financial-browser-results.txt`.

## Deployment boundary / open decisions

No production deployment, gateway calls, accounting migration, payout, or manual
balance adjustment was performed. Existing local reload servers can serve the
edited code, but there is no claim of external deployment or production accounting
certification. No customer/owner/staff business mutation workflow was modified.

Still required: signed sharing agreements; no-show disposition; principal/agent and
tax/fee treatment; membership recognition and Multi-Gym allocation; wallet lot
consumption/expiration/promotion rules; settlement approvals and actual payout data;
authoritative provider capture/refund dates; closed-period adjustments; utilization
denominators and membership conversion cohort. No percentages are hardcoded.