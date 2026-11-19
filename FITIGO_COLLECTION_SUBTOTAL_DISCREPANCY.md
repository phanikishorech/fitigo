# Collection subtotal discrepancy — INR 300 versus INR 0

## Conclusion

The previous **INR 300.00 is still reproducible**, with unchanged financial records, for **test mode, All gyms or gym 189, and a date range including November 17, 2026 IST**. The current application returns a **0.00 known dated subtotal** when November 17 is excluded, another gym is selected, or live mode is selected.

The actual host date during investigation was **November 18, 2026 IST**. The dashboard explicitly requests Today on initial load. Both underlying bookings are scheduled for November 18, but they were paid on November 17: scheduled visit dates are not collection dates.

There is an important correction to the earlier explanation: **INR 300 is gross paid purchase consideration including wallet spending, not new gateway cash or net retained revenue.** One INR 150 purchase was subsequently cancelled and credited back to the wallet. Original paid purchases and cancellation credits are separate metrics in the existing implementation. We clarified the metric definition visibly rather than silently changing its arithmetic or subtracting cancellation credits without a defined net-revenue contract.

The user's exact existing tab/filter selection is **not observable** from this environment: its Chrome process has no debugging connection. No screenshot, network request or browser-filter values were supplied. The conclusions below are verified against the same running backend and a separate browser, not an assertion that a particular filter was selected in the user's tab.

## Exact transactions behind INR 300

Both are `CART` purchases classified as **Individual bookings**, currency INR, checkout status `PAID`, payment-row status `PAID`, funding state `DEBITED`, funding mode `test` and wallet-account environment `test`.

| Field | Purchase A | Purchase B |
|---|---|---|
| Checkout ID | `098f74ed-12e6-47e1-8052-d94ffe101eed` | `d2f3ba65-182f-4037-923e-30ca7cb1b39c` |
| Booking ID | **1281** | **1283** |
| Payment row ID | **1277** | **1279** |
| Wallet debit ID | **62** | **67** |
| Gym | **189 — PowerHouse Strength Club** | **189 — PowerHouse Strength Club** |
| Purchase amount | **150.00** | **150.00** |
| Wallet funded | **150.00** | **150.00** |
| Gateway charged | **0.00** | **0.00** |
| Actual payment method | `WALLET` | `WALLET` |
| Configured checkout provider | `RAZORPAY` | `RAZORPAY` |
| Provider payment ID | null; no provider payment | null; no provider payment |
| Provider attempts | None | None |
| Ledger direction/type | `OUT / PAYMENT` | `OUT / PAYMENT` |
| Confirmed funding resolution, UTC | **2026-11-17 17:20:37** | **2026-11-17 17:32:12** |
| Confirmed funding resolution, IST | **November 17, 2026, 22:50:37 +05:30** | **November 17, 2026, 23:02:12 +05:30** |
| Scheduled booking date | November 18, 2026 | November 18, 2026 |
| Current booking state | `CANCELLED` | `CONFIRMED` |

### Why those dates are authoritative

The existing wallet debit service atomically records the `OUT/PAYMENT` ledger row and sets `CheckoutFunding.state=DEBITED`, its debit ID, and `resolved_at`. The report validates the debit identity, user, currency, amount and checkout relationship before using that existing funding resolution timestamp for a **wallet-only** purchase. Ledger creation timestamps match both resolution timestamps, but were not substituted for missing dates.

These are not claimed to be external gateway capture dates. No capture occurred for the zero gateway portion, and no date was invented. The `RAZORPAY` checkout field describes the configured orchestrator; the booking payment row and funding breakdown establish that these purchases actually used only wallet funds.

### Cancellation qualification

Purchase A was cancelled on **November 17, 2026, 22:51:10 IST** (17:21:10 UTC):

- Cancellation record **4**, booking **1281**, payment **1277**.
- Wallet credit **63**, `IN / CANCELLATION_CREDIT`, **150.00 INR**.
- Original checkout/payment remain `PAID`; no provider refund exists because gateway funding was zero.

The existing gross consideration metric includes the original 150.00 once; the wallet activity metric includes the subsequent credit once. Purchase B is another separately paid 150.00 booking. Thus **150 + 150 = 300 gross paid consideration**. For these two wallet-only purchases specifically, debit 300 less cancellation credit 150 equals **150 net wallet consumption**, but that is **not** the full-platform collection total or an approved earned-revenue measure.

The earlier phrase “fulfilled and unrefunded purchases” was too broad/misleading for wallet-credited cancellations. We replaced it with the actual metric definition: gross verified paid purchase consideration, including wallet-funded purchases and later wallet-credited cancellations, excluding wallet top-ups/provider-refunded payments, with cancellation wallet credits separately reported. No totals, financial formulas or eligibility safeguards were weakened to maintain INR 300.

## Other related transactions do not contribute to INR 300

1. Checkout `c0d86825-0aef-4e1d-a035-461b94f699db`, booking **1282**, gym **189**: 150.00 purchase = wallet debit **64** for 100.00 + gateway 50.00. Funding resolution is November 17, 2026, 22:52:24 IST, but this does **not** establish the gateway capture date. It is excluded from dated collections. Cancellation record **5** later credited 150.00 through wallet row **66** at 22:56:52 IST. No date is inferred from either funding resolution or cancellation.
2. Checkout `528518a8-be7f-4d81-8f99-c8478ef4aff6`, booking **1277**, **Max Fit Gym #1666**: 139.00 purchase = wallet debit **60** for 100.00 + gateway 39.00. Its funding resolution on November 13 does not establish the provider capture date, so it is also excluded from the dated subtotal.
3. Wallet top-up checkout `f9c7f179-b84d-4604-8446-3463118b258a`, wallet credit **65**, **500.00**: recharge is excluded from purchase collections. Adding the top-up again would mix wallet funding with wallet-spent consideration.

## Independent category verification

Full-2026 / test / All gyms:

| Category | Known dated subtotal | Exclusions without authoritative dates | Complete total |
|---|---:|---:|---|
| Individual bookings | **300.00** | **11** | null / unavailable |
| Single-Gym memberships | **0.00 known dated subset** | **1** | null / unavailable |
| Multi-Gym memberships | **0.00 known dated subset** | **2** | null / unavailable |
| Overall | **300.00 partial** | **14** | null / unavailable |

The membership records are independently verified paid amounts but cannot be assigned a payment date:

| Category | Checkout | Membership | Gym | Paid / successful attempt amount |
|---|---|---:|---|---:|
| Single-Gym | `4e00cb45-3886-470d-aeeb-d0f2240cf558` | 431 | 237 | 1399.00 |
| Multi-Gym | `146011bf-e851-46f4-816a-8c3a4ac73940` | 430 | None: platform membership | 2199.00 |
| Multi-Gym | `b8496332-cde8-48b6-92ec-6b24aaf53522` | 432 | None: platform membership | 2199.00 |

All three are test-mode `PAID` checkouts/memberships with matched `SUCCESS` payment attempts and zero provider refunds recorded. **1399.00 and 4398.00 are undated paid evidence, not verified full-2026 dated totals.** Creation/first-observed dates cannot prove that capture occurred in 2026. Their visits do not contribute additional collections. Multi-Gym amounts are neither allocated to gym 189 nor classified as FitiGo earnings.

## API/filter matrix

Every following request returned authenticated HTTP 200 with `Cache-Control: no-store`. The diagnostic script independently compared each response with the current service result in a database-enforced read-only transaction.

| Requested scope | Known dated Individual | Single / Multi known subset | Known overall subtotal | Complete overall |
|---|---:|---|---:|---|
| Jan 1–Dec 31, 2026; test; All gyms | 300.00 | 0.00 / 0.00 | 300.00 | null |
| Nov 17, 2026; test; All gyms | 300.00 | 0.00 / 0.00 | 300.00 | null |
| Nov 18, 2026; test; All gyms | 0.00 | 0.00 / 0.00 | 0.00 | null |
| Full 2026; test; gym 189 | 300.00 | 0.00 / 0.00 in selected gym scope | 300.00 | null |
| Full 2026; test; gym 188 | 0.00 | 0.00 / 0.00 | 0.00 | null |
| Full 2026; live; All gyms | 0.00 | 0.00 / 0.00 | 0.00 | 0.00: empty eligible live dataset |
| Bare API GET without dates | 300.00 | 0.00 / 0.00 | 300.00 | null |

**Important default mismatch:** a bare API request defaults to the trailing 30-day range, which was October 20–November 18, 2026. The Dashboard does **not** send a bare request: it explicitly sends Today, November 18–18. Comparing the bare API to the default Dashboard therefore compares different ranges. The previous full-year validation explicitly sent Jan 1–Dec 31.

For the matching full-year scope:

```text
GET /api/v1/admin/business/summary?date_from=2026-01-01&date_to=2026-12-31&mode=test
```

returns:

```json
{
  "known_dated_total": "300.00",
  "known_dated_categories": {"individual": "300.00", "single_gym": "0.00", "multi_gym": "0.00"},
  "categories": {"individual": null, "single_gym": null, "multi_gym": null},
  "total": null,
  "complete": false,
  "excluded_by_category": {"individual": 11, "single_gym": 1, "multi_gym": 2}
}
```

### Should INR 300 appear now?

**Yes**, as a **verified partial gross purchase-consideration subtotal**, when selecting Test payments, All gyms (or PowerHouse Strength Club #189), and a range including November 17, 2026. This was verified in a browser against the actual running API, including changing gym 189 → gym 188 → All gyms.

**No**, for Today November 18, a nonmatching gym, or Live payments. In an incomplete test dataset, 0.00 is only the known dated subtotal; the full total must still be unavailable. It should never be labelled INR 300 of new provider cash, retained revenue, owner share or commission.

If a browser still shows a 0.00 partial subtotal with **all three matching filters**, retain its exact `/api/v1/admin/business/summary` request URL/response and the visible date label. That would be a different, currently unreproduced discrepancy; do not change the dates or force a 300 fallback.

## Code changes and tests

Production changes are explanatory only:

- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\services\admin_business.py`: correct collection-definition wording; arithmetic/query eligibility unchanged.
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\admin\BusinessOverview.tsx`: expose that definition immediately beside the partial subtotal.

Added/extended diagnostics and regressions:

- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\scripts\collection_discrepancy_audit.py`: SELECT-only trace, exact timestamps and authenticated GET matrix, no provider calls.
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\tests\test_admin_business_cleanup.py`: two wallet-only purchases, cancellation credit kept separate, payment day versus booking day, gym and environment filters, missing funding date never inferred.
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\scripts\dashboard-revenue.test.mjs`: incomplete zero cannot become complete zero or reuse an earlier scope's amount; basis rendered beside subtotal.
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\scripts\dashboard-release-browser.mjs`: working read-only gym-filter matrix and separately named output artifact.

Backend: **48 passed**, zero failed, in 386.84 seconds, covering business collections and admin financial-position regressions on a disposable database. Existing datetime deprecation warnings remain; the runner shut down its owned MySQL server. Frontend: **499 tests passed**, TypeScript passed, production build passed. Actual API/browser date/gym/environment checks passed. Existing tests were not removed or weakened. The owned acceptance browser was stopped; unrelated application/browser services were left untouched.

## Evidence and safety

- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\COLLECTION_DISCREPANCY_TRANSACTIONS.json`: exact purchase, cancellation and membership records plus seven API requests/responses; no secrets or customer names/contact data.
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\COLLECTION_DISCREPANCY_BROWSER.json`: read-only browser/API capture.
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\COLLECTION_DISCREPANCY_TESTS.json`: disposable backend test artifact pointer.
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\COLLECTION_DISCREPANCY_BEFORE.json`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\COLLECTION_DISCREPANCY_AFTER.json`
- Frontend logs in `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend`: `collection-discrepancy-browser.txt`, `collection-discrepancy-unit.txt`, `collection-discrepancy-typecheck.txt`, `collection-discrepancy-build.txt`.

All **55** working-table row counts/fingerprints match this investigation's before/after snapshots; working revision remains `d46e70ba9268`. Comparing the previous release snapshot to this investigation's starting snapshot, only `refresh_tokens` had changed; all relevant financial tables already matched before any action in this task. Thus the historical subtotal difference is not explained by changed payment/funding records.

All four gates remain **false**: `source_evidence_enabled`, `marketplace_allocations_enabled`, `marketplace_live_allocations_enabled`, `marketplace_payouts_enabled`. No historical financial record, commission setting/formula, financial safeguard or wallet balance was modified. No working/production migration, deployment, provider payment, payout or financial worker/scheduler was initiated. Test writes occur only in disposable synthetic databases.

Stop for manual review/retesting; no activation or deployment authorization is implied.