# FitiGo — Final payment gateway and production infrastructure acceptance

## 1. Decision and execution boundary

**Automated isolated acceptance: passed. Actual hosted payment acceptance, physical-device acceptance and production infrastructure verification: blocked/not completed. Final deployment recommendation: NO-GO until the blockers below are closed and explicit deployment approval is granted.**

Task executed on the host's **November 18, 2026 IST** clock. The supplied developer environment date is November 17; evidence retains the observed clock rather than changing it.

The user explicitly confirmed: **“No hosted or device access is available; complete isolated automated validation and mark those acceptance tests blocked.”** This supersedes any expectation that local fixtures constitute actual hosted checkout or physical Android/iPhone execution.

No application code, dashboard, payment validation, pricing, commission formulas, migrations or existing tests were changed. This task produced this report and validation artifacts only. The accepted revenue findings were left untouched.

### Evidence classes

- **Automated backend:** real application routes/services, signature functions, persistence and assertions, with mocked provider responses and isolated SQLite/disposable MySQL fixtures. A MySQL test runner does not mean every test uses MySQL; concurrency/split tests explicitly use MySQL.
- **Automated browser:** isolated desktop Chrome context, mocked application APIs/provider SDKs; scanner uses a real QR decoder with simulated camera frames/network conditions. No physical-device claim.
- **Hosted provider acceptance:** not executed. No reachable isolated HTTPS deployment or merchant dashboard access was provided.
- **Physical Android Chrome / iPhone Safari:** not executed. Devices/device-lab access unavailable by user confirmation. `adb`/`idevice_id` were not found on PATH; that alone is not a device inventory.
- **Infrastructure:** read-only observations of the existing local development database plus disposable migration and dump/restore rehearsals. No production target was supplied or connected.

## 2. Current environment and exact blockers

Sanitized effective configuration was inspected without displaying secret values:

```text
ENVIRONMENT=development
effective gateway=RAZORPAY
effective payment mode=test
PAYMENT_RETURN_URL=http://localhost:5173/checkout
PUBLIC_FRONTEND_URL is empty
ALLOWED_ORIGINS=http://localhost:5173
Cashfree client ID and secret: present, validity not externally tested
Razorpay key ID, key secret and webhook secret: present, registration not externally tested
JWT configuration validation: passed locally
```

Presence of a credential is not evidence of its sandbox merchant binding, expiry, domain approval, webhook registration or production security. No credential probe, external order creation, payment, provider refund or webhook replay against working data was performed. Gateway selection and environment files were not changed.

Missing for hosted acceptance:

1. An approved isolated public HTTPS frontend/API and exact callback URLs.
2. Dedicated sandbox database and synthetic customer/owner/staff accounts, plans and gyms.
3. Securely provisioned sandbox merchant credentials and dashboard/webhook-log access.
4. Confirmed domain/return URL configuration and webhook routing that preserves raw bytes/headers.
5. Physical Android/iPhone devices or a device lab with camera and network-fault controls.
6. Named payments/platform/device-test owners and execution window.

No tunnel was created and no working database was exposed to a provider.

## 3. Cashfree results

**31 Cashfree-specific tests passed**, supplemented by shared funding, ownership, recovery and MySQL concurrency tests. All results in this section are automated with mocked provider transport, not actual hosted Cashfree transactions.

| Required case | Automated outcome / persistence check | Actual hosted outcome |
|---|---|---|
| Successful payment | Passed; verified successful provider state produces PAID and expected fulfillment | Blocked |
| Failed payment | Passed; failed state grants no membership or QR; eligible retry reuses order | Blocked |
| Customer cancellation | Passed; user-dropped state, UI dismissal and late success after cancellation handled without false activation/refund | Blocked |
| Pending payment | Passed; PENDING/NOT_ATTEMPTED do not grant access; later verified success activates once | Blocked |
| Delayed webhook | Passed; reconciliation uses original provider; delayed/duplicate success can recheck provider state; cancelled late captures need review | Blocked |
| Duplicate webhook | Passed; duplicate callback cannot create a second booking, membership or QR; repeat refresh/verify remains stable | Blocked |
| Invalid signature | Passed; tampered raw body, missing signature/timestamp rejected with HTTP 400 | Blocked |
| Amount mismatch | Passed; REVIEW_REQUIRED with PAYMENT_AMOUNT_MISMATCH; no usable QR/access | Hosted fault not performed |
| Order/payment reference mismatch | Passed for provider payment linked to a different order and currency mismatch: HTTP 409, no access; browser payment assertions rejected | Blocked |
| Booking fulfillment | Passed for Individual/cart, matching server-priced booking/payment and expected visitor QR count | Blocked |
| Membership activation | Passed for Single-Gym and Multi-Gym, one linked membership after verified payment | Blocked |
| Gateway-only | Passed; full server price charged, no wallet contribution | Blocked |
| Wallet-only | Passed; exactly one wallet debit and fulfillment, **zero external order creations** | Blocked as hosted application journey; there is intentionally no Cashfree checkout/callback in this branch |
| Split payment | Passed; exact wallet + gateway = purchase total, gateway charged only remainder, wallet debit once, retry/concurrent finalization protected | Blocked |

Reference mismatch claims are bounded to the tested API/provider-response relationships. Cashfree confirmation accepts no browser-supplied provider payment ID/signature/order assertion; the server fetches the order's payments. There was no adversarial live provider response or exhaustive proof against every possible malformed reference.

Database assertions include `PaymentCheckout`, `PaymentAttempt`, booking `Payment`, `Booking`, `UserMembership`, `AccessQrToken`, `CheckoutFunding`, `BookingFunding`, `WalletAccount` and `WalletTransaction` relationships/counts as applicable. Duplicate and concurrent requests are exercised on synthetic data; no observed callback is treated as authority without server reconciliation.

## 4. Razorpay final webhook results

**28 Razorpay payment tests passed**, plus cart replacement, shared security/funding/recovery and concurrency coverage. Actual internet delivery to a registered webhook endpoint was not tested.

| Acceptance requirement | Automated verified result |
|---|---|
| Valid signature accepted | Existing HMAC signature verification and webhook API accept valid signed fixture requests; successful processing returns HTTP 200 |
| Invalid signature rejected | Invalid confirmation/webhook signatures return HTTP 400; no unauthorized fulfillment |
| Duplicate webhook | Same event acknowledged as duplicate; booking payment/QR counts stay one; membership callback then repeat verification leaves one membership |
| Amount verified against original order | Tampered amount goes to review/no access; currency/order relationship mismatch rejected; browser cannot supply authoritative price |
| Delayed callback / old failure after success | Old failed event after captured event does not regress PAID or create another QR; exact event receipt counts asserted |
| Late capture after cancellation/expiry | Review required, no reactivation; captured payment is not falsely called refunded |
| Concurrent requests | Both-provider MySQL fixtures assert one order/membership, one recharge credit, safe replacement, no double-spend or duplicate finalization |

Primary cases reviewed/executed include `test_interrupted_callback_webhooks_deduplicate_and_do_not_regress_on_old_failure`, `test_bad_signatures_ownership_and_browser_amount_rejected`, `test_wrong_amount_currency_or_order_rejected`, `test_membership_only_activates_after_capture_and_only_once`, and the parameterized MySQL concurrency suites. No real webhook secret or raw customer event was used in tests.

**Conclusion:** application callback behavior passed the covered automated cases. Registered merchant endpoint, reverse proxy, internet delivery/retries and real provider-event acceptance remain blocked, not certified.

## 5. Hosted payment execution plan — pending access

This is a prepared runbook, **not an executed hosted result**. It must run only on the supplied, separately approved sandbox deployment.

### Preflight

1. Record immutable build/revision, tester and environment owner. Confirm isolated DB identity, sandbox merchant account and synthetic users. Fail closed if mode/account/host is ambiguous.
2. Configure the approved host's HTTPS frontend, return URL, exact allowed origins and API webhook routes. Set Cashfree sandbox mode on that host only for Cashfree runs; use a separately scoped Razorpay test configuration for Razorpay runs. Do not silently switch existing orders to a different provider/account.
3. Use the application's currently supported API version/configuration; verify it with the merchant account/operator before execution. Never expose secrets in frontend variables, screenshots, HAR files or report output.
4. Keep `SOURCE_EVIDENCE_ENABLED`, `MARKETPLACE_ALLOCATIONS_ENABLED`, `MARKETPLACE_LIVE_ALLOCATIONS_ENABLED`, `MARKETPLACE_PAYOUTS_ENABLED` false and all financial job deployments stopped.
5. Register the isolated callback paths `/api/v1/payments/webhooks/cashfree` and `/api/v1/payments/webhooks/razorpay` as applicable. Verify delivery logs, TLS chain and raw-body/header preservation. Use current provider-documented sandbox instruments; do not invent test card details or use real customer cards.

### Matrix and observations

For Individual, Single-Gym and Multi-Gym purchases, cover gateway-only and split funding; cover wallet-only separately without an external gateway order. Run success, failure, dismissal/cancellation and pending outcomes where the provider supports a documented simulation.

For every case, retain a restricted evidence row containing:

```text
case ID; build; operator; UTC/IST time; provider; test environment;
FitiGo checkout ID; expected total/wallet/gateway/currency;
provider order/payment IDs; before/after checkout/payment state;
booking/membership/QR counts; wallet debit count and balance delta;
webhook event/receipt and correlation IDs; HTTP statuses;
result; redacted artifact location; reviewer.
```

- **Success:** confirm provider server state and amount/currency/order, then exactly one correct booking or membership. Refresh/reopen must preserve result; browser “success” alone is insufficient.
- **Failure/pending:** no usable entitlement until verified success. Retry must not duplicate order/debit/fulfillment.
- **Cancellation:** closing a hosted modal is not proof of failed payment. Refresh/reconcile first; a late captured payment against a closed purchase requires review, not fabricated refund/access.
- **Delayed webhook:** controlled isolated proxy delays one synthetic event; compare no browser refresh, refresh-first, and already-cancelled variants. Record fault injection separately from native provider delay.
- **Duplicate/out-of-order:** replay through supported merchant tools or exact signed fixture bytes on staging; deliver old failure after success. Assert final state/counts are stable. Never replay working customer events.
- **Invalid signature:** alter one byte/header without resigning; expect rejection and unchanged fulfillment. Preserve raw bytes securely; never log secrets.
- **Amount/order/payment mismatch:** normal checkout uses server-owned values and cannot legitimately produce arbitrary mismatches. The automated transport tests are the current evidence. If hosted qualification requires fault injection, use an explicitly approved synthetic test transport—not edited historical rows or fabricated production evidence. Tampering with a signed body is only a signature test unless independently valid provider evidence is controlled.

Acceptance requires matching database outcomes and reviewed delivery evidence for each supported case. Unsupported provider simulation stays “not tested/controlled injection,” never “passed hosted.”

## 6. Mobile-browser scanner acceptance

### Automated results

**39 backend access tests passed** (included in the 53-test access/infrastructure run), including MySQL concurrent booking scans, rotated membership tokens, expired access, wrong gym, scanner authorization and one-time admission. The desktop Chrome scanner browser suite passed:

- Valid member and booking QR decoding/approval; two successive scans without camera restart.
- Duplicate/stationary suppression and deliberate used-QR rejection.
- Wrong-gym/unauthorized, expired membership/booking, paused/cancelled/unpaid and invalid-QR UI rejection.
- Permission denial/revocation/grant, camera loss/retry and missing/busy camera.
- Network/server/malformed responses, validation timeout, stale result suppression and recovery.
- Manual-token duplicate-submit lock and stream cleanup after unmount.

Physical **Android Chrome: BLOCKED**. Physical **iPhone Safari: BLOCKED**. Desktop responsive viewport checks are not physical/mobile-browser qualification.

### Prepared physical-device matrix

Execute every row on each device with HTTPS staging, synthetic staff assigned to the gym, a second display holding synthetic QRs and read-only database observation. Record model/OS/browser version, camera permission state, Wi-Fi/cellular route and tester.

| Case | Expected behavior / DB evidence |
|---|---|
| Valid QR | Authorized success only; one successful check-in and correct booking visitor/daily membership consumption |
| Expired QR | Rejection; zero additional successful visits/consumed entitlement |
| Duplicate QR | Already-used response; successful admission count remains one, including deliberate rescan after cooldown |
| Wrong gym | Rejection for entitlement or staff assignment mismatch; no successful visit |
| Permission denial | Explicit browser permission guidance; no camera scan/validation request until permission restored |
| Network lost before request | Verification error/uncertainty, no assumed approval; zero server admission if request never arrives |
| Response lost after commit | Do not treat UI error as proof of no admission; read-only server confirmation; deliberate retry cannot create a second successful visit |
| Slow/delayed response | Timeout recovers; stale response cannot overwrite a later scan; camera remains usable or offers explicit recovery |
| Reconnect / route change | Fresh valid QR works after network restoration; no automatic queued admissions or duplicate consumption |

Include background/lock/resume and permission recovery on both platforms. A rejected or uncertain scan must not count as an authorized successful visit. Any technical/audit record is not a successful admission; compare successful check-in and entitlement-consumption counts. Do not authorize admission offline, weaken validation or manually mark a test as successful to bypass a network problem.

## 7. Database and infrastructure review

### Verified local observations

| Item | Observed result | Interpretation |
|---|---|---|
| MySQL | **26.7.0** | Isolated tests use the installed binary; production version remains unknown |
| Working schema revision | **d46e70ba9268** | Unchanged |
| Repository migration head | **eb3f70126935** | Single ordered chain; fresh-install and upgrade rehearsed only on disposable schemas |
| Binary logging | ON, ROW | Prerequisite only, not proof of recoverable archives |
| GTID | ON | Does not prove PITR procedure or replica/backup coverage |
| Durability | sync_binlog=1; innodb_flush_log_at_trx_commit=1 | Local values only |
| Binlog expiry | 2,592,000 seconds (30 days) | Local retention setting; no independent archive verified |
| Secure transport enforcement | require_secure_transport=0 | Local server does not enforce TLS; actual session encryption/production TLS not established |
| Current connection grants | GRANT OPTION present | Unsuitable as evidence of least-privilege production runtime access; no grant was changed |
| JWT configuration validation | Passed | Only local configured checks; entropy origin, rotation, secret-store controls and production bindings unverified |
| HTTPS/public callbacks | Localhost HTTP only | Hosted delivery blocked |

Pending migration order, **not executed on working/production DB**:

```text
e57f81cb0379 -> f68a92dc1480 -> a79ba3ed2591 -> b80cb4fe3602
-> c91dc50f4713 -> da2e6f105824 -> eb3f70126935
```

No recommendation is made to deploy that chain automatically. Target compatibility, backup, approvals and separate data-readiness review are required. New tables must not be populated with invented historical financial evidence.

### Production verification still required

| Requirement | Required evidence / owner role | Status |
|---|---|---|
| Compatibility/capacity | Exact target MySQL version/edition/config, production-sized workload and migration rehearsal — DBA | Blocked: no target |
| Privileges | Separate runtime/migration/backup identities; runtime lacks grant/DDL authority; append-only safeguards verified — DBA/security | Unverified |
| Backup | Encrypted production backup, retention, access control, independent copy, integrity check and recovery point — DBA | Unverified |
| PITR | Archived binlogs/GTID chain plus isolated replay to a defined recovery point; measured data loss/recovery time — DBA | **Not executed** |
| Restore | Production-sized isolated restore with hashes, triggers, constraints, business checks and measured RTO — DBA | Synthetic rehearsal passed only |
| Secrets | Secret store, least privilege, rotation/revocation, no frontend leakage, sandbox/live separation — security/platform | Local presence only |
| HTTPS/webhooks | DNS/certificate, exact domains/return URLs, raw-body proxy, merchant registration, retry logs — platform/payments | Blocked |
| Monitoring | Health, latency/errors, pending/review payments, signature failures/duplicate events, wallet mismatches, DB locks, backup failures, gate drift — SRE | No production alert pipeline evidenced |
| Ownership | Named accountable and backup contacts for release, DBA, payments, SRE, security, finance/support — release owner | Not supplied |
| Rollback | Tested app/schema compatibility rollback, forward-only financial migration policy, controlled restore/PITR with approvals — release/DBA | Plan prepared; target drill outstanding |

Roles listed above are **unassigned roles, not named operational owners**. A deployed check/dashboard without a tested alert recipient and escalation path is not monitoring acceptance.

## 8. Backup and restoration results

The existing isolated rehearsal **actually executed** `mysqldump` and `mysql` restore against newly created synthetic schemas. It did not dump/restore working or production data.

Verified by the passing tests:

1. Fresh migration to repository head, expected constraints/indexes and append-only triggers.
2. Upgrade of a synthetic schema at the working revision to head preserves every pre-existing row fingerprint; new financial tables remain empty.
3. Dump using transactional options and triggers/routines/events; restore into another disposable schema.
4. Identical source/target table sets and row fingerprints.
5. Matching trigger names; attempted update/delete of restored immutable review records still rejected.
6. Forward-only financial downgrade safeguard still rejects unsupported downgrade.

**Limitations:** this is a small synthetic logical-backup restore, not production-size recovery, disaster recovery from independent storage, or PITR. No binlog replay was executed. Local logging/retention settings cannot substitute for a recovery drill. RPO/RTO and production backup freshness remain unapproved.

Prepared PITR rehearsal: DBA selects an isolated approved target, restores a verified base backup, validates its GTID/position, replays the archived binlog chain up to a documented point before a synthetic fault, checks expected included/excluded marker transactions and financial hashes/constraints, measures RPO/RTO, and obtains a second reviewer. Never overwrite the source/production database or remove immutable history as rollback.

## 9. Test results and reproducibility

### Backend: 146 gateway/payment tests passed

| Suite | Passed |
|---|---:|
| Cashfree payments | 31 |
| Razorpay payments | 28 |
| Both-provider MySQL concurrency (historical filename `test_razorpay_mysql`) | 6 |
| Razorpay cart replacement | 10 |
| Gateway recovery | 5 |
| Payment configuration | 15 |
| Security/payment ownership | 3 |
| Both-provider split/wallet funding | 46 |
| Both-provider concurrent wallet spend/finalization | 2 |
| **Total** | **146** |

Run duration: 475.42 seconds. Zero failures/errors/skips.

### Backend: 53 access/infrastructure tests passed

| Suite | Passed |
|---|---:|
| Booking access MySQL concurrency | 2 |
| Booking QR API | 17 |
| Access regressions | 14 |
| Membership daily access | 1 |
| Customer QR system | 5 |
| Gate/startup/read-only operations | 11 |
| Migration/backup/restore | 3 |
| **Total** | **53** |

Run duration: 107.25 seconds. Zero failures/errors/skips. These are two separate selected-suite runs, not a new full-repository backend certification. Existing datetime deprecation warnings remain.

### Frontend/browser

- **499 frontend unit tests passed**, zero failures/skips.
- Razorpay checkout browser: passed, intercepted APIs/SDK only.
- Cashfree checkout browser: passed, intercepted APIs/SDK only.
- Split payment browser: passed, both provider remainders/custom amount/zero balance/wallet-only.
- Scanner browser: passed, desktop Chrome simulated camera/network with real decoder.
- No frontend source changes; TypeScript/production build were not rerun in this validation-only task (their previous pass is not claimed as a new execution).

Existing isolated runner command used `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\scripts\run_isolated_tests.py` with binary `C:\Program Files\MySQL\MySQL Server 26.7\bin\mysqld.exe`. It creates its own private instance and synthetic credentials, migrates only that isolated schema, runs selected tests, and stops its owned MySQL server. No financial worker command or source-evidence activation option was used. Safety tests may create in-memory invalid gate combinations to prove rejection; working/runtime gates remained false.

### Artifacts

- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\PAYMENT_INFRA_ENVIRONMENT.json` — sanitized current environment/DB observations.
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\PAYMENT_INFRA_BEFORE.json`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\PAYMENT_INFRA_AFTER.json`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\PAYMENT_INFRA_GATEWAY_TESTS.json` — private test-directory pointer.
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\PAYMENT_INFRA_ACCESS_RESTORE_TESTS.json` — private test-directory pointer.
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\PAYMENT_INFRA_TEST_SUMMARY.json` — JUnit-derived counts, failures/skips and run summaries.
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\payment-infra-razorpay-browser.txt`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\payment-infra-cashfree-browser.txt`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\payment-infra-split-browser.txt`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\payment-infra-scanner-browser.txt`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\payment-infra-frontend-tests.txt`

Private runner directories contain pytest logs, JUnit results, migration logs and retained disposable database files. Treat them as restricted diagnostics, not production backups. No secret values were added to report artifacts.

## 10. Release blockers and final safety attestation

Outstanding blockers:

1. Hosted Cashfree success/failure/cancellation/pending/funding/fulfillment acceptance and recorded delivery evidence.
2. Actual Razorpay test webhook endpoint and delivery/retry acceptance.
3. Both physical mobile browser scanner matrices.
4. Target production DB compatibility, least privilege/TLS and approved migration plan.
5. Verified production backup, production-sized restore and PITR/RPO/RTO evidence.
6. Secrets/domain/callback configuration, tested monitoring/escalation and named operational ownership.
7. Reviewed immutable release artifact and explicit deployment approval.

All four financial gates remain false:

| Gate | Before | After |
|---|---|---|
| `source_evidence_enabled` | false | false |
| `marketplace_allocations_enabled` | false | false |
| `marketplace_live_allocations_enabled` | false | false |
| `marketplace_payouts_enabled` | false | false |

**All 55 working-table row counts and SHA-256 fingerprints match before/after; schema revision remains `d46e70ba9268`.** No working/production migration, historical financial modification, provider payment, payout or financial worker/scheduler start occurred. No pricing/formula/dashboard changes or validation weakening occurred. Existing working application/database services were left untouched; runner-owned test servers and the owned browser were stopped after validation.

**Stop here. Await infrastructure/device provision, completion of blocked checks, and explicit deployment approval. Passing isolated tests is not authorization to deploy or activate financial processing.**