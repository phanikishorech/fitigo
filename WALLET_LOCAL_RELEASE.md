# Wallet balance fix — local release

## Authorization and outcome

User authorized: “fix this and deploy the changes to local”. Deployed only to the
existing local development application: frontend 5173, backend 8000, local `fitigo`
database, configured Razorpay test mode. Provider settings/secrets were unchanged.

The screenshot's wallet was identified by cancellation-credit ledger entries 58/59.
After migration and restart, both authenticated local GET endpoints returned:

- Wallet balance: INR 300.00
- Available to spend: INR 300.00
- Reserved: INR 0.00
- Spending restriction: none

No purchase, recharge, cancellation, transfer or manual balance adjustment was made.
The verification used a one-minute in-memory token matching the existing account's
session version, not a password change or stored login. An initial smoke token
without that version was correctly rejected with 401; the corrected read-only check
passed. Anonymous wallet access also returned 401.

## Fix

- Wallet API responses now expose `wallet_unavailable_reason` instead of silently
  turning a blocked wallet into an unexplained available balance of zero.
- Wallet page prominently displays the actual recorded wallet balance, followed by
  separate spendable and reserved amounts. A restriction panel explains the reason
  and offers Refresh wallet. Unknown available balance is not presented as spendable.
- Corrected accidental question-mark separators in the wallet UI.
- Wallet fetches request `cache: no-store`.
- Existing wallet holds, currency/environment eligibility and provider verification
  protections remain unchanged.

## Backup and migration

- Backup: `C:\Users\ckishor\AppData\Local\FitiGo\releases\wallet-20261113-154238\fitigo-before-wallet.sql`
- Size: 117890 bytes; dump completion marker and SHA-256 verified. Verification
  metadata is in the same private directory. No restore rehearsal was performed.
- Backup directory restricted to the current Windows user and SYSTEM. Temporary
  database credentials file removed; no credentials printed or placed in arguments.
- Stopped only two verified FitiGo backend launcher trees (including a duplicate
  launcher); did not stop MySQL or the frontend.
- Applied `b24c5ef78046` -> `c35d6fa89157`.
- Counts and deterministic row-content hashes verified unchanged for **all 50
  existing data tables**, excluding the intentional Alembic version change.
- New `checkout_funding` and `booking_funding` tables were empty after migration.
- Restarted using `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\scripts\start-dev.ps1`.
- Runtime logs: `C:\Users\ckishor\AppData\Local\FitiGo\runtime\backend-20261113-154312-a82eb22f`.
- Backend health, DB health and frontend API proxy checks passed. Existing Vite
  serves the updated source; a production build was also generated, not externally deployed.

## Tests

- **68 targeted backend tests passed** on the isolated runner, covering wallet
  history, new restriction-response cases, split payments and MySQL concurrency.
  Log: `C:\Users\ckishor\AppData\Local\Temp\fitigo-isolated-ac1afafc9bf90f3e-gk4zdy9w\pytest.log`.
- **447 frontend tests passed**, TypeScript passed, production build passed.
- Customer-account mocked browser test passed: recorded INR 300 with blocked
  spendable balance, visible reason, refresh restoring INR 300 available, recharge,
  history, profile and responsive layout at 320/768/1440px.
- Split-payment mocked browser regression passed after restart.
- Actual local wallet GET checks passed as described above. Browser payment actions
  were mocked and did not reach the working payment APIs.
- Previous split implementation full suite was 877 passing; this release reran the
  affected 68 backend tests, not the full backend suite.

Frontend evidence:
`C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\wallet-local-unit-results.txt`
`C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\wallet-local-build-results.txt`
`C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\wallet-local-browser-results.txt`

## Files changed in this fix

- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\schemas\wallet.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\routers\wallet.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\tests\test_wallet_gateway_history.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\screens\Checkout\api.ts`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\services\accountService.ts`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\pages\wallet\WalletPage.tsx`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\scripts\customer-account-browser.mjs`
- This report and the status note in the split implementation report.

## Remaining limitations

This report supersedes the earlier **not locally migrated** status in
`C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\WALLET_SPLIT_PAYMENT_IMPLEMENTATION.md`.
It does not remove that report's Razorpay pending/expired-order hold-release
limitation: uncertain still-payable orders retain funds for reconciliation. No
safety bypass was introduced. Real sandbox transactions/webhook delivery remain
untested, and this is not production certification. Do not downgrade after funding
records exist or restore a backup over subsequent customer activity without approval.