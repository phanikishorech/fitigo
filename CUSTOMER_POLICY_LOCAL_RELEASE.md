# Customer policy — local release

## Scope and authorization

User selected: “Release to my local FitiGo app: back up and migrate the local working database after all checks pass.” This release is the existing local Windows/Vite/FastAPI application, not an external production deployment. The existing frontend port 5173 and proxy were preserved. No payment/provider secret or customer password was changed.

## Resolved failures

All prior backend/frontend failures are resolved. No tests were deleted or skipped to obtain these results.

- Updated old no-wallet-credit expectations to the approved eligible-wallet-credit policy; unverified funding still cannot issue credits, and the authorized admin override still preserves payment evidence.
- Added a test-only balanced wallet funding helper so cancellation fixtures carry a real linked debit, rather than silently trusting DUMMY or unlinked payments.
- Preserved QR invalidation, capacity release, rescheduling, owner authorization, audit actor/privacy, and one-notification assertions with valid policy clocks/payment fixtures.
- Duplicate customer/owner cancellations now assert 409 while verifying one cancellation record, one credit and one capacity release.
- Open gateway-order cancellation remains rejected. Tests verify that subsequent captured payments are credited exactly once, and that operationally cancelled bookings cannot reactivate after late capture.
- Cashfree refund-after-wallet-credit regression checks REVIEW_REQUIRED and retained actual provider refund evidence, not a fabricated refund or second credit.
- Migration-head check now resolves Alembic's actual current head while preserving original-data and downgrade-history safeguards.
- Fixed a repeatable-read snapshot in the capacity-test setup; the fixture now sees the API's committed booking before adding funding evidence.
- Staff scanner browser fixtures now include the existing notification preferences API. Camera, decoder, duplicate scan, permission, network and teardown assertions remain intact.

## Verification

| Check | Result |
|---|---|
| Full isolated backend suite (`tests -q`) | **829 passed**, 0 failed |
| Frontend unit suite | **442 passed**, 0 failed |
| TypeScript | Passed |
| Production build | Passed |
| Customer cancellation/transfer browser suite | Passed, including 360/768/1440px dialogs |
| Customer activity/cart-edit browser suite | Passed |
| Owner/admin notification workflow browser suite | Passed |
| Staff scanner browser suite | Passed: decoder, sustained stream, duplicates, failures, permissions, cleanup |
| After-restart API/database/discovery smoke checks | Passed on ports 8000 and 5173 |
| Protected endpoint anonymous access | Correct 401 responses |
| Actual local booking/membership policy reads | Passed, read-only |

Backend run artifacts: `C:\Users\ckishor\AppData\Local\Temp\fitigo-isolated-d8a688c8ec443d80-pnnmsetd` (829 passed in 427.49s). The test server shut down cleanly. Existing datetime deprecation warnings remain; these were not failures.

Frontend evidence:
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\policy-release-unit-results.txt`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\policy-release-build-results.txt`

## Local deployment and backup

- Target: development database `fitigo` on localhost:3306; test payment mode.
- Stopped only the verified FitiGo backend launcher process tree; did not stop MySQL or unrelated services.
- Private release directory: `C:\Users\ckishor\AppData\Local\FitiGo\releases\policy-20261113-081416`
- SQL backup: `C:\Users\ckishor\AppData\Local\FitiGo\releases\policy-20261113-081416\fitigo-before-policy.sql`
- Backup size: 105713 bytes; completion marker verified. This is a successful dump with hash verification, not a claimed restore drill.
- SHA-256: `e44dff22604a2f616a6e969384e90016c4fab62d1cdbcc28c3454dfb45620973`
- Backup directory ACL restricted to the current Windows user and SYSTEM. Temporary credential file removed; credentials were not placed in command arguments or report output.
- Applied migration: `a13b4df67935` → `b24c5ef78046`.
- Verified counts/checksums unchanged for all **48 existing data tables**, excluding the intentional Alembic version change. Both new policy tables started empty.
- Restarted backend using `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\scripts\start-dev.ps1`.
- Runtime logs: `C:\Users\ckishor\AppData\Local\FitiGo\runtime\backend-20261113-081420-293c5cb7`.
- Existing Vite frontend serves the current source; production build also generated successfully. This does not convert the development server into a production hosting service.

No test cancellation, wallet credit, transfer, purchase, or check-in was executed on working customer records. Browser mutation tests intercepted APIs in isolated contexts. Local post-release checks were read-only or unauthenticated rejection checks.

## Changes in this release-fix pass

- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\tests\policy_fixtures.py` (new)
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\tests\test_admin_financial_integrity.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\tests\test_booking_access_qr.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\tests\test_booking_capacity.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\tests\test_cashfree_payments.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\tests\test_notification_workflows.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\tests\test_phase5_mysql.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\tests\test_phase5_workflows.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\tests\test_phase6_operations.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\tests\test_razorpay_payments.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\tests\test_support_migration_mysql.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\tests\test_wallet_gateway_history.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\scripts\financialScope.test.mjs`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\scripts\owner-scanner-browser.mjs`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\CUSTOMER_POLICY_IMPLEMENTATION.md`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\CUSTOMER_POLICY_LOCAL_RELEASE.md` (this report)

The application implementation inventory remains in `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\CUSTOMER_POLICY_IMPLEMENTATION.md`. No unsafe relaxation of application payment/cancellation/transfer rules was needed to resolve the tests.

## Operational limits / rollback

- Existing unverified legacy/DUMMY payments and unsupported split funding remain ineligible for automatic wallet credits; they require review, not guessed amounts.
- A separately initiated external provider refund after wallet credit remains a review case. No new arbitrary refund or wallet adjustment interface was introduced.
- Do not downgrade after policy audit records exist: the migration deliberately refuses their deletion. Prefer a forward fix. Restoring the pre-release SQL would discard subsequent activity and requires explicit maintenance approval; no restore was performed here.
- Git CLI was unavailable, so no Git commit/tag/push was made. This is an activated local release with backup/build/test evidence, not a repository release tag or external deployment.