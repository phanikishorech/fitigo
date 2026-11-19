# FitiGo — Final dashboard revenue validation and release checks

## Decision

**Dashboard fix validated locally. NO-GO for production deployment or financial activation pending hosted payment acceptance, physical-device scanner checks, and production operational sign-off.** No deployment was performed.

The supplied environment date is November 17, 2026; the actual host clock for this run was **November 18, 2026 IST**. All API date comparisons below use explicit dates. The user's successful commission/history and INR 750 wallet retests are accepted, not repeated with working-data writes.

Workspace: `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo`. Existing unrelated work was preserved. No dependencies, pricing, commission formulas or gateway rules were changed.

## 1. Dashboard root causes

### A. Date scope

The dashboard initializes to **Today**, not the full calendar year. The authoritative existing wallet-funded consideration totalling **INR 300.00 occurred on November 17, 2026 IST**. Therefore:

- November 18, 2026: verified dated subtotal **0.00**.
- November 17, 2026 or January 1–December 31, 2026: verified dated subtotal **300.00**.
- Neither result establishes a complete total: 14 other eligible purchases have no authoritative capture date and cannot be placed inside or outside either range.

No payment creation, observation, scheduled booking or visit timestamp was substituted for capture time. The INR 300 uses the existing verified wallet-only funding resolution timestamp, not a guessed provider date.

### B. Rendering and global completeness

The prior API returned `known_dated_categories`/`known_dated_total`, but the existing category cards bound only to `collections.categories`, and total cards only to `collections.total`. The earlier partial subtotal appeared in a separate section below the cards, making all prominent revenue cards look unavailable even when verified evidence existed.

The backend also nulled **every** category whenever **any** category had incomplete evidence. That unnecessarily hid complete categories independently of other categories.

### C. Revenue sharing is not collections

Owner gross share and FitiGo commission come only from the existing allocation report, not a multiplication of collections by today's commission settings. This database lacks all six checked sharing/evidence tables:

```text
financial_source_evidence
gym_monthly_calculations
gym_visit_payouts
marketplace_allocations
membership_visit_fees
owner_payouts
```

Consequently both sharing values must remain unavailable. The latest user's saved commission version is preserved: baseline inventory now finds one test gym with a version, but no currently effective own version at inventory time. Even an effective version would not create historical allocations, source tax/fee evidence or earnings. We did not backfill or enable processing.

## 2. Fix implemented

- Added per-category completeness and excluded-purchase counts to the read-only business API.
- Category cards show a verified **positive** partial amount with “verified partial” in the title and exclusion count in the caption. A zero known subtotal for an incomplete category does **not** replace unavailable with zero.
- An independently complete category can show its verified total, including a genuinely complete zero, even if another category is incomplete.
- Overall total values remain null when incomplete. Their existing card captions now show the clearly labelled verified partial subtotal, so the INR 300 is visible without claiming a full total.
- Added explicit sharing availability/reason metadata; displayed reasons for missing allocation schema, no recorded allocations, or incomplete allocation/fee evidence. Existing non-null sharing amounts are labelled as recorded allocation subtotals, not complete population totals.
- Added explicit selected-date scope and zero-subtotal explanation to the existing partial section. No dashboard layout redesign or default date-range change.
- Existing complete revenue charts/CSV remain unavailable when the overall dataset is incomplete. No membership visit amount is added to membership purchase collections. Unallocated Multi-Gym collections never become FitiGo earnings.

### Modified/new implementation and test files

1. `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\services\admin_business.py`
2. `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\admin\businessService.ts`
3. `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\admin\BusinessOverview.tsx`
4. `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\tests\test_admin_business_cleanup.py`
5. `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\scripts\dashboard-revenue.test.mjs`
6. `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\scripts\dashboard-release-browser.mjs`
7. `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\FITIGO_FINAL_DASHBOARD_AND_RELEASE_CHECKS.md`

All amount arithmetic, eligibility checks, payment verification, fulfillment, allocation calculations and commission formulas remain unchanged. Only completeness/presentation metadata and rendering changed.

## 3. Verified values and API responses

Actual authenticated HTTP 200, no-store GET requests were exercised from the browser against the running local backend. API bodies are retained in `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\DASHBOARD_RELEASE_BROWSER.json` (collection response subset, including exact excluded IDs/reasons). No working POST was sent.

```text
GET /api/v1/admin/business/summary?date_from=2026-01-01&date_to=2026-12-31&mode=test
```

Relevant response fields after the fix:

```json
{
  "date_from": "2026-01-01",
  "date_to": "2026-12-31",
  "mode": "test",
  "collections": {
    "categories": {"individual": null, "single_gym": null, "multi_gym": null},
    "category_complete": {"individual": false, "single_gym": false, "multi_gym": false},
    "excluded_by_category": {"individual": 11, "single_gym": 1, "multi_gym": 2},
    "total": null,
    "complete": false,
    "known_dated_total": "300.00",
    "known_dated_categories": {"individual": "300.00", "single_gym": "0.00", "multi_gym": "0.00"},
    "exclusion_reasons": {"PAYMENT_DATE_SCHEMA_MISSING": 14},
    "undated_purchases": 14,
    "unattributed_purchases": 0,
    "gym_gross_share": null,
    "fitigo_commission": null
  }
}
```

For both sharing fields, `sharing_availability` is `status=UNAVAILABLE`, `reason=ALLOCATION_SCHEMA_MISSING`, with the six missing tables listed above.

| Card | Verified value, full 2026/test | Full value | Display after fix |
|---|---:|---|---|
| Individual bookings | **300.00** | Unknown; 11 excluded purchases | **INR 300.00 — verified partial** |
| Single-Gym memberships | No dated amount established; known subset 0.00 | Unknown; 1 excluded purchase | Not available yet, exclusion explanation |
| Multi-Gym memberships | No dated amount established; known subset 0.00 | Unknown; 2 excluded purchases | Not available yet, exclusion explanation |
| Total customer collections / Revenue collected | **300.00 partial** | Unknown; 14 excluded purchases | Main value unavailable; caption shows verified partial INR 300.00 |
| Gym owner gross share | None recorded | Unknown | Unavailable with allocation-evidence reason |
| FitiGo commission earnings | None recorded | Unknown | Unavailable with allocation/fee-evidence reason; no residual Multi-Gym assumption |

Before and after the amount fields remain truthful: all full totals above were and remain null. The change makes the already verified subset prominent and explains why the others are not available.

For `date_from=2026-11-18&date_to=2026-11-18&mode=test`, known dated total is **0.00**, complete total remains null and the same 14 undated purchases block completeness. For the same date in **live** mode, the eligible dataset is empty and complete collections are **0.00**; sharing remains unavailable. The browser checks both scopes and verifies that yesterday's INR 300 does not leak into Today or live.

INR 750 wallet remains reconciled; no wallet code or balance was changed. No historical payments were fetched or repaired.

## 4. Cashfree payment acceptance

### Executed, with limits

**31 Cashfree adapter/API tests passed**, within the 76-test payment/dashboard run. They use the actual Cashfree adapter with an HTTP mock and disposable records, not real hosted Cashfree checkout. The Cashfree browser fixture also passed dismissal, failure, retry reuse, interrupted callback, refresh recovery and responsive checkout. These are not provider acceptance claims.

| Required case | Local execution | Hosted execution |
|---|---|---|
| Success | Passed; Individual, Single-Gym, Multi-Gym, cart fulfillment | Blocked |
| Failed checkout | Passed; no membership/QR activation | Blocked |
| Customer cancellation/dismissal | Passed; USER_DROPPED and cancelled/late-success review | Blocked |
| Webhook signature | Passed; valid raw body, missing/tampered signature/timestamp rejection | Blocked |
| Duplicate webhook | Passed; same order, one fulfillment, duplicate acknowledgement | Blocked |
| Delayed/out-of-order webhook | Passed; provider reconciliation, no duplicate fulfillment, late cancelled success review | Blocked |
| Amount mismatch | Passed; REVIEW_REQUIRED / PAYMENT_AMOUNT_MISMATCH, no access | Provider-controlled mismatch not exercised |
| Correct booking/membership fulfillment | Passed; server pricing/identity, exact visitor QR count, one membership | Blocked |

### Exact infrastructure dependency

Current inspected effective configuration:

```text
ENVIRONMENT=development
effective gateway=RAZORPAY
effective mode=test
PAYMENT_RETURN_URL=http://localhost:5173/checkout
PUBLIC_FRONTEND_URL is empty
ALLOWED_ORIGINS contains only http://localhost:5173
Cashfree client ID present: true
Cashfree client secret present: true
```

Secret values were neither printed nor stored in the report. Presence is not proof of account validity/domain approval. No separate publicly reachable hosted HTTPS frontend/API, sandbox database, merchant-dashboard access, registered callback endpoint, or access credentials for such an environment were supplied/discovered in the inspected configuration. A localhost callback cannot establish Cashfree-to-host delivery. We did not change gateway settings, expose the working machine through a tunnel, create a provider order, or use customer data.

Cashfree's current webhook documentation permits HTTP **or** HTTPS in sandbox and requires HTTPS in production. Therefore HTTPS is the requested hosted/mobile acceptance environment requirement here, not a claim that Cashfree rejects every sandbox HTTP callback. Hosted checkout also requires domain whitelisting and server-owned order creation. See official references below.

### Manual hosted-sandbox procedure (not executed)

**Preflight owner: named Payments QA lead + platform operator, not yet assigned.**

1. Supply an approved isolated staging host with valid HTTPS, dedicated synthetic users/gyms/plans and database. Do not point staging at the working or production database. Record commit/build identifier, backend revision and operator approval. No real customer instruments or live credentials.
2. Configure only that approved sandbox deployment: `PAYMENT_GATEWAY=cashfree`, `PAYMENT_ENV=sandbox`, the existing adapter's `CASHFREE_API_VERSION=2026-01-01`, sandbox `CASHFREE_CLIENT_ID`/`CASHFREE_CLIENT_SECRET`, HTTPS `PAYMENT_RETURN_URL` ending in `/checkout`, matching `PUBLIC_FRONTEND_URL` and exact `ALLOWED_ORIGINS`. Avoid conflicting legacy payment modes. Keep all four financial gates false and financial job deployments stopped. Do not change the local environment as part of this checklist.
3. Payments owner verifies the domain's checkout approval, secret-store binding, sandbox account and API/webhook-version compatibility. Register the isolated API path `/api/v1/payments/webhooks/cashfree` for success, failure and user-dropped events. Preserve raw request bytes and `x-webhook-signature`/`x-webhook-timestamp` through the proxy. Retain sanitized delivery/correlation evidence, never secret keys or instrument data.
4. Select current Cashfree-documented sandbox instruments or simulator outcomes (official reference below). Do not invent test card numbers. For each of Individual, Single-Gym and Multi-Gym, record FitiGo checkout ID, provider order/payment IDs, expected server quote, environment and starting fulfillment counts.
5. **Success:** complete hosted test checkout, confirm server PAID and amount/currency/order match; verify one correct membership or confirmed booking, expected visitor passes, refresh/reload persistence. Do not accept a frontend “success” message alone.
6. **Failure:** choose a documented failure; confirm no fulfillment/usable access. Retry via existing UI and verify order reuse where still payable. For dismissal/user cancellation, refresh status first; closing a modal is not proof of provider failure. A late success for a locally cancelled order must require review, not create access.
7. **Signature:** allow a real sandbox delivery and verify processing. On the isolated endpoint only, replay its exact bytes and headers; then alter one body byte or signature without recomputing it. Expect HTTP 400 and unchanged state. Do not bypass signature checking or log the raw payload in a shared report.
8. **Duplicate:** use a supported merchant-dashboard resend or exact signed-body replay for a test order. Compare booking/membership/payment/QR counts before and after; no extra fulfillment. Also send an older failure after success; paid state must not regress.
9. **Delayed:** use a controlled staging proxy to delay delivery for one synthetic order while avoiding browser refresh reconciliation. Restore delivery; expect one fulfillment. Repeat separately with manual refresh preceding webhook and with a locally cancelled order. If a provider cannot simulate the chosen timing, record the case as controlled fault injection rather than native hosted-provider behavior. Never disrupt a shared/production webhook endpoint.
10. **Amount mismatch:** a normal provider checkout cannot legitimately pay a different server-owned amount. Retain the passing isolated adapter regression. If hosted qualification requires this case, use a separately approved test-only transport harness with synthetic data and no real gateway call; expect review/no access. Do not alter a real checkout, existing financial row or provider evidence to manufacture the mismatch. An altered signed webhook is a signature test, not an authoritative amount-mismatch test.
11. Capture redacted HTTP statuses, environment, correlation IDs and before/after counts per case. Record browser/device versions, test time, operator, outcome and link to private artifacts. Stop for review on any ambiguous settlement/payment state; no automatic refund/payout or financial gate activation.

### Official Cashfree references checked during this task

These are references for operator review, not evidence that hosted tests were run:

```text
https://www.cashfree.com/docs/payments/online/web/redirect
https://www.cashfree.com/docs/payments/online/webhooks/configure
https://www.cashfree.com/docs/payments/online/webhooks/signature-verification
https://www.cashfree.com/docs/payments/online/resources/sandbox-environment
```

The signature contract reviewed is Base64 HMAC-SHA256 over timestamp + exact raw body with the Cashfree PG secret; the existing adapter implements that contract. No gateway implementation was changed.

## 5. Android Chrome / iPhone Safari scanner interruption plan

**Status:** prepared, physical execution blocked by unavailable devices/hosted test access. Desktop Chrome with mocked network/camera and real QR decoder passed. Device emulation is not iPhone Safari or physical Android acceptance.

Run the following on **both a physical Android device in Chrome and a physical iPhone in Safari**. Record device model, OS/browser version, test build, camera permissions, Wi-Fi/cellular route and operator. Use HTTPS staging, an assigned synthetic staff account, and independently generated valid synthetic booking-visitor and membership daily-access QRs. No customer check-in records.

| Scenario | Steps | Required result/evidence |
|---|---|---|
| Baseline | Scan one valid QR while online | One successful check-in; correct member/gym/time; camera remains usable |
| Offline before request | Disconnect all network routes before presenting a fresh QR | No APPROVED result; safe verification error; no server check-in |
| Request reaches server, response lost | Controlled proxy drops response after the test server commits | UI reports uncertainty/error, not presumed approval; after recovery deliberate rescan cannot create a second check-in; inspect original server record |
| Request lost before server | Block outbound validation request, then restore network | No check-in before restoration; deliberate retry can produce exactly one |
| Slow response | Delay validation beyond the current 12-second client timeout | Spinner ends; camera/error state recovers; late stale response cannot overwrite a later scan |
| Recovery | Restore connectivity; remove stationary QR, allow suppression/cooldown, scan fresh QR | New scan works without full reload where camera remains available; no burst of queued validations |
| Background/lock | Background or lock during a validation, then return | No stale approval; permission/camera recovery prompt if needed; no duplicate requests/consumption |
| Camera/network transition | Switch Wi-Fi/cellular; revoke/regrant camera permission | Explicit recoverable state, no silent access grant; no leaked stream after navigating away |
| Repeat-use protection | Present same booking visitor/daily-access QR again after recovery | Backend rejects already-used access; exactly one durable successful consumption |

Evidence per row: safe screen recording, request/correlation ID, timing, final UI state and read-only check-in/access-row counts. Do not record QR secrets, bearer tokens, or customer PII. A timeout cannot prove whether the server committed: staff must not treat network failure as authorization to admit. Escalate uncertain outcome for read-only confirmation.

The existing scanner browser suite verifies network/server/malformed responses, timeout/stale-cycle handling, camera continuity, stationary suppression, permission recovery and unmount cleanup. Backend MySQL concurrent scans and access regression tests passed. No scanner workflow was modified.

## 6. Infrastructure readiness and owners

Production access, named owners and approvals were not supplied. Local observations must not be represented as production certification.

| Area | Observed / blocker | Required evidence and accountable role |
|---|---|---|
| Release artifact | Workspace already contains unrelated changes | Release lead: reviewed immutable commit/build, dependency lock and scoped change approval |
| Production database | Unknown target/version/privileges; local MySQL 26.7.0, revision d46e70ba9268 | DBA: exact target compatibility, capacity, least-privilege runtime/migration/backup users, connection/TLS policy |
| Schema/migrations | Working schema unchanged; sharing tables absent | DBA + finance: approved migration rehearsal and target revision; never assume migration fixes historical evidence; no working/production migration run here |
| Backup | No production backup verified | DBA: encrypted verified backup, retention/access controls, independent copy, restore point and owner |
| Restore/PITR | Synthetic dump/restore test passed; local binlog enabled, ROW, sync_binlog=1, flush_at_trx_commit=1 | DBA: production-sized isolated restore drill, hashes/constraints/triggers, GTID/binlog recovery, measured RPO/RTO and signed recovery instructions |
| Environment | Local HTTP only; secrets present is not validation | Platform/security: secret store/rotation; DATABASE_URL, JWT_SECRET/algorithm, exact origins, HTTPS URLs, storage paths/permissions and sandbox/live separation |
| Payments/webhooks | No supplied hosted sandbox endpoint/merchant access | Payments owner: successful matrix above, callback registration, raw-body proxy behavior, certificate/domain approval and safe retry monitoring |
| Monitoring | No production sink, alert destination or dashboard evidenced | SRE: health/latency/5xx, pending/review payments, webhook errors/duplicates, wallet reconciliation, scan failures, DB locks/connections, backup failure/restore freshness, gate drift and stopped-job alerts |
| Logs | Safe error handling tested; production access/retention unverified | Security/SRE: sanitized structured correlation logs, restricted access, retention, no credentials/QRs/payment instruments |
| Operations | No named on-call/escalation roster | Release, DBA, payments, SRE, support and finance owners: names, backups, incident runbooks, response times and explicit sign-offs |
| Rollback | Historical financial data is append-only | Release/DBA: app compatibility rollback, restore/PITR approval; no erasure of history as rollback |
| Financial processing | All four gates false | Platform/finance: keep gates false and workers/schedulers stopped; separate activation approval outside this task |

Synthetic fresh-install, upgrade-preserves-records and dump/restore tests passed only on disposable schemas. No production backup was downloaded or restored. No production environment was connected or modified.

## 7. Validation evidence

| Check | Result |
|---|---|
| Backend dashboard/payment selection | **76 passed**: 19 business metrics, 31 Cashfree, 15 payment configuration, 5 recovery, 6 purchase journeys |
| Final business-metric suite including recorded-sharing projection tests | **21 passed** (overlaps previous 19) |
| Access/infrastructure selection | **30 passed**: 2 MySQL concurrent-scan, 14 access regressions, 11 gate/operations, 3 migration/restore |
| Frontend unit tests | **497 passed**, no failures/skips |
| TypeScript | Passed |
| Production build | Passed |
| Actual read-only API dashboard browser | Passed: full-2026 INR 300 partial, Today, live, category exclusions, sharing reasons and 360/768/1440 layouts |
| Existing business dashboard browser | Passed; existing routes/reports/CSV/scope behavior retained |
| Cashfree browser fixture | Passed, mocked SDK/API only |
| Scanner browser | Passed, desktop Chrome simulated camera/network only |
| Hosted provider / physical mobile tests | **Not executed — blocked**, procedures above |

Backend tests use the existing `run_isolated_tests.py` runner; migrations target only a newly created disposable MySQL instance. Runner-owned servers stopped. Existing datetime deprecation warnings remain. No existing test assertions were removed or weakened. Initial new negative tests failed before implementation as expected. The new browser harness initially read the previous API result while the next date-range response was loading; its wait was corrected to require the completed dashboard render, then the full probe passed. This was a test synchronization issue, not a payment-date fallback.

### Artifacts

- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\DASHBOARD_RELEASE_ENVIRONMENT.json` — sanitized configuration/local DB observations and before-fix ranges.
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\DASHBOARD_RELEASE_BEFORE.json`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\DASHBOARD_RELEASE_AFTER.json`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\DASHBOARD_RELEASE_DIAGNOSTICS_BEFORE.json`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\DASHBOARD_RELEASE_DIAGNOSTICS_AFTER.json`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\DASHBOARD_RELEASE_BROWSER.json`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\DASHBOARD_RELEASE_TESTS.json`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\DASHBOARD_RELEASE_FINAL_METRICS_TESTS.json`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\DASHBOARD_RELEASE_INFRA_TESTS.json`
- Frontend logs: `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\dashboard-release-unit.txt`, `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\dashboard-release-typecheck.txt`, `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\dashboard-release-build.txt`, `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\dashboard-release-browser.txt`, `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\dashboard-release-regression-browser.txt`, `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\dashboard-release-cashfree-browser.txt`, `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\dashboard-release-scanner-browser.txt`.

Run pointers identify private pytest logs/JUnit results. Internal checkout IDs in diagnostic artifacts are for restricted review, not public distribution.

## 8. Safety attestation and stop

**All 55 working-table row counts and fingerprints match this task's before/after snapshots.** The user's earlier manual commission save is included in the new baseline and was preserved. No historical financial records, wallet balances, funding evidence or configuration rows were changed by this task. Schema revision remains `d46e70ba9268`.

| Gate | Before | After |
|---|---|---|
| source_evidence_enabled | false | false |
| marketplace_allocations_enabled | false | false |
| marketplace_live_allocations_enabled | false | false |
| marketplace_payouts_enabled | false | false |

No production deployment, real customer payment, payout, financial worker/scheduler startup, historical modification, price/formula change or working/production migration occurred. Existing application services were not started/restarted by this task; disposable test servers and the owned acceptance browser were used for validation only.

**Recommendation:** accept the scoped dashboard display fix for further manual retesting; do not authorize production release until the hosted sandbox matrix, both physical scanner platforms and named operational sign-offs are complete. Do not authorize financial activation on the basis of these display tests.

**Stop after validation/report preparation. Await manual retesting and infrastructure provision.**