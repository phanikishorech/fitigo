# FitiGo manual acceptance defect fixes

## Outcome and scope

Implemented and validated locally. **Stop for manual retesting; no financial activation or deployment is authorized.**

Task date: November 17, 2026. Validation crossed the host's midnight into November 18; artifact timestamps retain the actual clock. Workspace: `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo` (a junction to the existing development checkout). Pre-existing changes were retained; this was already a dirty workspace.

Commission navigation is fixed without relaxing FastAPI/Pydantic validation. The complete collection total correctly remains unavailable where authoritative payment dates are absent; verified partial collections and exact exclusions are now exposed. The working all-gym test wallet already reconciles to INR 750.00; its gym-scope limitation and reconciliation failures are now explained rather than hidden behind a generic message.

## 1. Commission settings HTTP 422 and missing selector entries

### Root cause and reproduction

`FinancialSettings` maintained zero-based page state, while the shared `Pagination` component expects one-based pages. Both the selector and configuration-history callers were wrong:

- On the initial page, Previous was enabled and requested a negative offset.
- On the second page, Previous was disabled, preventing a return to the first page.
- The selector showed only its current 20-item page; its page labels/ranges were also incorrect.
- A failed history read replaces the entire configuration resource, removing access to the editor until navigation recovers. This reproduces the reported inability to proceed with changes/history; no separate valid-POST failure was found.

Captured from the browser, forwarded unchanged to the running authenticated local API, **before implementation**:

```text
GET /api/v1/admin/financial-settings?mode=test&gym_id=188&limit=20&offset=-20
HTTP 422
```

Complete response body:

```json
{
  "detail": [
    {
      "loc": ["query", "offset"],
      "msg": "Invalid value for this field.",
      "type": "validation_error"
    }
  ],
  "request_id": "527eef05134b49249d78ba3943027f20"
}
```

The route's `offset >= 0` validation is correct. A bare GET without mode/gym also returns 422, correctly, but the captured UI defect is the negative offset above. Valid GETs with `mode=test&gym_id=188&offset=0` already returned 200.

The selector query searches all gyms with literal escaped name matching, stable name/id ordering, count, limit and offset. It does not join financial versions or omit gyms without settings. The working database has 39 gyms (37 approved, 2 draft); all 39 lack their own versions in both environments. This is not a reason to backfill settings on a GET.

### Files changed

- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\admin\FinancialSettings.tsx`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\scripts\financial-settings-browser.mjs`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\scripts\gym-financial-settings.test.mjs`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\tests\test_gym_financial_settings_mysql.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\scripts\manual-acceptance-readonly-browser.mjs`

### Fix

Translate page state at both UI boundaries (`page + 1`, returned page `- 1`). Keep API/service offsets zero-based. Add matching-gym count and navigation guidance. Do not change shared pagination behavior or unrelated callers.

Reviewed request payload, schema and service: explicit gym/mode, latest version, expected effective version ID, timezone-bearing future effective date, settings, trimmed reason, actor from authentication, acknowledgement and idempotency header. The existing UI-shaped payload validates. Existing root-scope locking, optimistic concurrency, append-only versions, per-scope request-key/hash/actor checks, percentage sums and future-only dates are preserved. Existing gym initialization remains an explicit admin future version; new-gym initialization remains atomic in its original creation transaction.

### Before/after behavior and tests

- Before: browser Previous sent offset -20 and received 422; initial fixture browser assertion reproduced the enabled button.
- After: first-page Previous is disabled; pages 1/2/3 request offsets 0/20/40; second-page Previous returns to offset 0. No negative-offset UI request.
- Backend still rejects negative offsets, omitted required query fields, invalid percentages/dates and stale versions. No backend settings production code or schema was changed.
- All 39 working gyms are reachable in the read-only browser probe. A 45-gym browser fixture and multi-page MySQL selector regression verify pagination beyond the first page.
- Disposable MySQL tests verify valid POST 200, retry returns the same version ID, changed retry payload/stale update 409, and separate gym/live state. Browser save/retry/reload uses intercepted fixtures, not working writes.

### Limitations

Working gyms were **not initialized or updated** during this task. Manual retesting must deliberately review and save a future version. Scheduled settings are visible immediately in history but do not become currently effective before their start time. Missing financial processing evidence still blocks financial processing, not configuration editing.

## 2. Revenue collected unavailable

### Root cause and evidence

The current database revision is `d46e70ba9268`; `financial_source_evidence` is absent. Payment attempts store `first_seen_at`/`updated_at`, checkouts and booking payments store `created_at`/`updated_at`. None is an authoritative provider capture date. Verified status/amount and fulfilled purchase links are not enough to assign a payment to a reporting day.

For January 1–December 31, 2026 in test mode:

- Verified dated consideration: **INR 300.00**, Individual wallet-only purchases using their existing resolved funding timestamp.
- 14 otherwise eligible purchases lack reliable capture dates: **11 Individual, 1 Single-Gym, 2 Multi-Gym**.
- Full total and all full category totals therefore remain null, not zero.
- The working ledger contains no live purchases; the live verified collection projection is 0.00, not a substitute for test data.

The previous API already returned a `known_dated_total`, but the active dashboard did not display it and exposed only a generic exclusion warning. Inspection also found the read projection did not check source evidence status/amount/currency before accepting its timestamp; additional negative regressions now protect these checks.

### Files changed

- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\services\admin_business.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\admin\businessService.ts`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\admin\BusinessOverview.tsx`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\tests\test_admin_business_cleanup.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\scripts\admin-cleanup.test.mjs`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\scripts\admin-cleanup-browser.mjs`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\scripts\manual_acceptance_diagnostics.py`

### Fix and before/after API behavior

GET remains read-only, HTTP 200. Existing full-total semantics stay unchanged. Added:

```json
{
  "total": null,
  "complete": false,
  "known_dated_total": "300.00",
  "known_dated_categories": {
    "individual": "300.00",
    "single_gym": "0.00",
    "multi_gym": "0.00"
  },
  "exclusion_reasons": {"PAYMENT_DATE_SCHEMA_MISSING": 14}
}
```

The admin API also lists excluded eligible checkout IDs, category and reason. Reasons distinguish missing schema/date, conflicting dates, invalid evidence and cross-gym allocation gaps. IDs and exact record lists are in the local diagnostic artifact, not customer-facing output.

The existing dashboard now displays a clearly labelled **verified partial subtotal**, separate categories and reasons. Main collected total remains unavailable if incomplete. Zero in a partial category means no known eligible dated subtotal, not proof of zero total collections. Complete charts and CSVs remain unavailable when evidence is incomplete.

Retained verified funding, fulfillment, transfer ownership, currency, refund and environment safeguards. New timestamp validation checks evidence status, amount, currency, hash and payment identity. An initial `EVENT_TIME_UNAVAILABLE` observation does not prevent a later append-only verified timestamp from completing the evidence. Conflicting dated evidence remains unavailable. No creation/observation timestamp fallback was introduced.

### Tests and limitations

Backend tests cover separate membership categories, no repeat collections through visits, wallet/gateway split, missing/invalid/conflicting evidence, later verified details and environment separation. Browser tests cover partial display and unavailable main total. No Multi-Gym residual is classified as FitiGo earnings; recorded commission remains independently unavailable.

**Full historical collection totals cannot reliably be calculated.** Missing historical capture evidence is not repaired, inferred, migrated or fetched from providers. Undated purchases cannot be safely assigned inside or outside a selected date range. The exclusion list addresses otherwise eligible purchases rejected for date/attribution evidence; unpaid, refunded, unverified or unfulfilled records remain excluded by the existing eligibility projection rather than being presented as collections.

## 3. Unused customer wallet balance unavailable

### Root cause and reproduction

Reproduced the unavailable response with a gym filter. Wallet credits are platform-wide and have no authoritative remaining-credit allocation to individual gyms. The existing service correctly returned `applicable=false`, `outstanding=null` and a scope reason; the UI discarded that reason.

With All gyms/test selected, the existing verified wallet ledger already returns **750.00**. Read-only comparison against individual customer balances:

| Wallet account | Stored balance | Individual verified balance |
|---|---:|---:|
| 7 | 200.00 | 200.00 |
| 14 | 550.00 | 550.00 |
| Total | **750.00** | **750.00** |

Working ledger: TOPUP credits 500.00 + five cancellation credits totalling 750.00 - four PAYMENT debits totalling 500.00 = **750.00**. Two unclassified-mode accounts have zero balances; no nonzero unclassified balance was silently assigned to test/live. No working ledger mismatch prevents aggregation.

### Files changed

- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\services\admin_financial_service.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\admin\BusinessOverview.tsx`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\tests\test_admin_business_cleanup.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\scripts\admin-cleanup.test.mjs`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\scripts\admin-cleanup-browser.mjs`
- The two diagnostic/browser probe scripts listed above.

### Fix, API behavior and tests

Preserve authoritative signed ledger reconciliation per account and payment mode; do not derive balance from booking or payment totals. Display the backend reason when unavailable. Provide an All gyms button that clears only the gym filter, preserving dates and environment. Display nonzero unclassified-mode balances separately.

For mismatches, the admin API now returns a specific reason and `review_accounts` (account/user IDs, stored balance, ledger net and invalid-record indicator). Full outstanding remains null; mismatched balances are not silently excluded to make a plausible total.

Before/after all-gym test GET: HTTP 200, `outstanding="750.00"`, reconciliation difference 0.00. Before/after gym-scoped GET: HTTP 200, null outstanding; after, the UI explains why and lets the admin return to platform scope. Live has no classified balances and returns 0.00.

Tests cover cancellation credits, debits, signed compensating reversal credits, booking-total independence, test/live separation, mismatch diagnostics and browser scope recovery. Existing wallet ledger/workflow tests remain intact. Ledger rows have no separate reversal-status field: recorded compensating movements contribute once with their sign; invalid ledger records fail reconciliation rather than being guessed away. No customer wallet/cancellation workflow was changed.

### Limitations

Remaining wallet credits cannot be attributed to one gym/provider without evidence not currently stored. Nonzero mode-unclassified accounts, if present later, are disclosed separately, not allocated by assumption. A reconciliation failure requires record review, not balance repair by this dashboard.

## 4. Commission history

Root cause: the same zero-based/one-based pagination mismatch described in Issue 1. Files changed: `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\admin\FinancialSettings.tsx`, `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\scripts\financial-settings-browser.mjs`, and `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\tests\test_gym_financial_settings_mysql.py`.

Before: first-page Previous causes HTTP 422 and removes the loaded editor/history. After: valid page offsets return HTTP 200. Existing version storage and response contracts remain unchanged.

Final MySQL regressions create 22 explicit future fixture versions, retry every request, load both history pages, compare original terms/reason/actor/effective/creation timestamps, and verify another gym/live history is empty. Existing tests also verify effective-date boundaries, current-vs-scheduled versions, immutable previous rows, legacy contract acknowledgement and concurrent updates (one succeeds, the other receives 409). Browser tests verify save, retry, reload, full page reload and gym/environment isolation.

Limitation: the working gyms have no own historical versions, so nonempty working history cannot be demonstrated without creating real settings. Nonempty histories and writes were verified only on disposable synthetic data; no working configuration was fabricated.

## 5. Regression validation

No existing test was removed, weakened or skipped to obtain a pass. Test-only setup corrections preserved source-evidence immutability and required observation timestamps.

| Check | Result |
|---|---|
| Broad backend selection: settings, agreements, admin metrics/integrity/reconciliation, wallet and purchase journeys | **186 passed**, 1263.96 seconds |
| Final affected backend selection: business metrics, MySQL settings/history, wallet history migration | **38 passed**, 259.72 seconds |
| Append-only later-evidence focused rerun | **1 passed**, also included in the final 38 |
| Frontend tests | **494 passed**, zero failed/skipped |
| TypeScript | Passed |
| Production build | Passed |
| Commission browser | Passed: 45 gyms/three pages, validation, save/retry, reload, history, environment/gym isolation, missing schema, 360/768/1440 layouts |
| Active business dashboard browser | Passed: existing seven modules/CSV/responsive checks plus partial collections, exact exclusions, wallet scope recovery and mismatch message |
| Working read-only API browser | Passed before/after probes; captured actual 422 before, 39 selectable gyms after, wallet scope/all-gym responses |
| Legacy `admin-financial-browser.mjs` | **Failed: obsolete target** expects retired financial dashboard and does not mock `/admin/business/summary`. Left unchanged; not counted as an affected-workflow pass |

Counts overlap and must not be added. This is the requested affected-area validation, not a new full-repository backend-suite claim. Existing datetime deprecation warnings remain.

An intermediate targeted run had 37 passed/1 failed because the new undated-evidence fixture also set the required **observation** `created_at` to null. Corrected the fixture to preserve an observation time while keeping capture time missing; final complete targeted rerun passed all 38. An initial negative-evidence test fixture attempted to edit immutable inserted evidence; corrected to construct the synthetic invalid row before insertion, without disabling immutability. A browser startup race was corrected by waiting safely for `document.body`; final suite passed. A working API probe briefly encountered development-server reload connection failures and passed when rerun after reload settled.

### Artifacts and commands

Root evidence files under `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo`:

- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\MANUAL_FIXES_BEFORE.json`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\MANUAL_FIXES_AFTER.json`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\MANUAL_FIXES_METRICS_BEFORE.json`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\MANUAL_FIXES_METRICS_AFTER.json`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\MANUAL_FIXES_DIAGNOSTICS.json`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\MANUAL_FIXES_BROWSER_BEFORE.json`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\MANUAL_FIXES_BROWSER_AFTER.json`
- Backend run pointers: `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\MANUAL_FIXES_BACKEND_TESTS.json`, `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\MANUAL_FIXES_FINAL_GREEN.json`. These point to private logs/results and isolated server shutdown evidence.
- Frontend logs: `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\manual-unit-results.txt`, `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\manual-typecheck-results.txt`, `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\manual-build-results.txt`, `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\manual-settings-browser-results.txt`, `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\manual-dashboard-browser-results.txt`.

The existing isolated MySQL runner was used with `--mysql-bin` pointing to `C:\Program Files\MySQL\MySQL Server 26.7\bin\mysqld.exe`. It creates a new private instance/schema, migrates **only that disposable schema**, runs pytest, and shuts down its owned server. Frontend commands: `npm test`, `npm run typecheck`, `npm run build`, and the two affected browser scripts. No dependency was added.

## Safety attestation and manual retest handoff

**All 55 working-table row counts and SHA-256 fingerprints match before/after. No historical financial records, working configuration versions, funding evidence, wallet rows or customer records were modified.** Working revision remains `d46e70ba9268`. No working or production migration was deployed.

| Financial processing gate | Before | After |
|---|---|---|
| `source_evidence_enabled` | false | false |
| `marketplace_allocations_enabled` | false | false |
| `marketplace_live_allocations_enabled` | false | false |
| `marketplace_payouts_enabled` | false | false |

No financial worker/scheduler was started, no payout initiated, and no provider payment/refund request made. Tests use disposable synthetic fixtures; financial gates were not activated in the working environment. No commission defaults/formulas, membership prices, gateway business rules, historical records or customer booking/QR/cancellation/wallet workflows were changed. No dashboard redesign was performed.

Manual retest: navigate both selector pages; select a gym without settings; review defaults, percentages, reason and a future India-time start; save; reload history; verify another gym is unchanged; inspect test/live separately. In the dashboard use All gyms for the INR 750 test wallet. Use the full 2026 range to inspect the INR 300 verified partial collection subtotal; expect the complete total to remain unavailable because of the 14 undated purchases.

**Implementation and validation stop here. Await manual retesting.**