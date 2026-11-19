# Cancellation and one-time membership transfer

## Release status

**Released to the authorized local development application.** The user explicitly approved backing up and migrating the local working database after verification. The full backend suite passed **829 tests**; all **442 frontend tests**, TypeScript and production build passed. Customer policy/cart, owner/admin notification, and staff scanner browser checks passed. The previous blocked-release findings and historical test counts below are retained as development history and are superseded by `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\CUSTOMER_POLICY_LOCAL_RELEASE.md`.

The local database was backed up, migrated from `a13b4df67935` to `b24c5ef78046`, and the backend restarted. Existing records were verified unchanged. No external production deployment was performed. Existing tests were retained and updated to the approved policy with explicit verified-payment fixtures, duplicate-credit assertions, and gateway closure protections.

The rule is `now <= scheduled_start - 3 hours`, using the actual slot date/start in Asia/Kolkata, not creation time or the QR entry window. For an 18:00 visit, 14:59 and 15:00 are eligible; 15:01 is not. The contradictory 14:59 example in the request was resolved in favor of its formula and acceptance tests.

## Backend / APIs

Reused:
- `POST /api/v1/bookings/{id}/cancel`: centralized cutoff, identity, attendance, payment and wallet-credit policy.
- Existing owner cancellation: same policy and cutoff; no ordinary owner bypass.
- Existing admin cancellation: standard eligible requests use the same credit policy. The pre-existing administrator operational override remains for other permitted cases, does not invent a wallet credit, and cannot cancel used/attended visits.
- Booking, owner/admin booking, and customer profile-booking responses include `cancellation`: eligibility, reason, deadline, scheduled start, refundable amount, credit amount/reference, timestamp and reason.
- `POST /api/v1/memberships/me/{id}/cancel`: rejects customer membership cancellation, without modifying access or funds.
- `GET /api/v1/memberships/me`: includes original-owner transferred history and recipient ownership/transfer status.

Added:
- `GET /api/v1/memberships/me/{id}/transfer`: eligibility/history.
- `POST /api/v1/memberships/me/{id}/transfer/preview`: exact verified-email recipient lookup, limited first-name/last-initial identity, five-minute signed confirmation. Existing persistent throttling limits lookups to 10 per customer per 15 minutes.
- `POST /api/v1/memberships/me/{id}/transfer`: explicit confirmation plus Idempotency-Key; atomically transfers the existing entitlement.
- `GET /api/v1/admin/memberships/transfers`: paginated, admin-only audit view; no transfer reversal or arbitrary credit controls.

The existing schema uses `MULTI_GYM`, which represents the requested Multi-Gym access product. It was not renamed or duplicated. Single-Gym and inferred multi-gym access from multiple single-gym purchases never qualify.

## Cancellation / ledger

Only CONFIRMED individual BOOKING_ACCESS, with no attendance or successful partial/group check-in, is eligible. Payment/booking amounts and currency must match. Pending, failed, refunded, unknown and synthetic DUMMY payment sources are rejected for automatic credit. Complimentary zero-value confirmed bookings cancel without a credit.

Wallet-funded bookings require the original linked PAYMENT debit, matching owner/currency, and matching aggregate booking allocations. Gateway-funded bookings require a paid linked checkout, matching provider/transaction, SUCCESS attempt evidence, no recorded provider refund, and matching allocation totals. Credit equals the actual per-booking paid allocation—not an entire multi-booking checkout total. No gateway refund API is invoked and original paid history is not relabeled REFUNDED merely because wallet credit was issued.

**Split funding is not supported by the current one-Payment-per-booking schema.** No split funding was fabricated. Partial/mismatched funding fails closed for review. Test/live wallet mode and currency checks prevent cross-mode credits. A later external provider refund after a wallet credit is flagged REVIEW_REQUIRED/WALLET_CREDIT_EXTERNAL_REFUND; its evidence is retained, with no second credit or automatic wallet debit. Resolving that externally initiated double-benefit risk is an operational review, not an implemented refund-recovery UI.

Existing WalletAccount balance and WalletTransaction ledger are updated in the cancellation transaction. Transaction type is `CANCELLATION_CREDIT` (fits existing VARCHAR(20)); the unique cancellation record links booking, Payment and wallet transaction. Failure rolls everything back. Duplicate cancellation returns conflict and cannot create another credit. Existing checkout APIs remain responsible for closing unresolved unpaid gateway orders.

Locks coordinate payment reconciliation and booking check-in. Check-in now locks customer → gym → booking before recording admission. Cancellation also locks checkout where present. Cutoff is rechecked after lock waits. Rescheduling a confirmed booking cannot be used to evade an already-passed cancellation deadline.

Capacity is released from verified server-owned cart/class linkage or the direct slot reservation. Unverifiable legacy class linkage fails safely rather than guessing a session or decrementing unrelated capacity.

## Transfer / QR / privacy

Only owned, paid, active, unexpired, unpaused, never-transferred Multi-Gym memberships qualify. Recipient must be an active registered CUSTOMER/USER with the exact verified email, not self, and must not already have an overlapping/current or upcoming paid membership under existing purchase rules. Account-scoped legacy future pauses require support resolution; membership-scoped past/future pause records and allowance are preserved.

Transfer locks both accounts in ascending ID order, then the membership and access records. Unique membership_id in the audit table guarantees at most one completed transfer. Same-key/same-recipient retries within the confirmation lifetime return the original result; other attempts reject. Tampered, expired, wrong-owner or changed-validity confirmations reject.

The membership ID, type, plan, dates, original expiry, payment/purchase references, terms snapshot and pause history remain unchanged. Only current user ownership changes. No new purchase, payment or membership is created.

Unused old ownership daily access and active QR tokens are revoked. Existing scans remain historical records belonging to the actual visitor. QR issuance shares ownership locks; scan validation rechecks current membership owner. Membership-level daily usage and an audited consumed transfer-day marker prevent a second visit after transfer, including legacy scanned visits. Calendar entitlement intervals are clipped to transfer time while actual visit history stays with the visitor.

Backend confirmation is the authority. Frontend cannot grant eligibility or choose credit amounts. Recipient lookup does not expose phone, addresses, passwords, OTPs or a searchable directory. Confirmation tokens contain only bounded identity/confirmation claims, are signed, are not persisted in audit and should not be logged.

## UI

- My Bookings and Details use the returned policy/deadline and shared confirmation dialog, with wallet-only amount and result.
- Membership / Details show eligible one-time transfer, explicit recipient confirmation, permanent-transfer notice, remaining expiry and history. Transferred records move to original-owner history; recipient cannot retransfer.
- My Access reflects changed ownership and transfer history; original-owner QR cannot admit after transfer even if a stale page is open.
- Profile retains the historical membership visit link for original owners.
- Owner details show current membership coverage without revealing another gym's payment data, and booking wallet-credit results.
- Admin booking details show original amount, cancellation deadline/eligibility, reason, timestamp and wallet reference. Membership-plan management includes transfer history.
- Existing fonts, tokens, buttons, cards and navigation are reused; no global theme edits or new dependencies.

## Migration and deployment

`b24c5ef78046_customer_policies.py` follows `a13b4df67935` and creates only:
- `booking_cancellations`: unique booking_id and wallet_transaction_id; original payment reference and cancellation evidence.
- `membership_transfers`: unique membership_id, indexed original/recipient IDs, actor, request key, completed status, validity snapshot, transfer time and optional consumed_access_date.

Upgrade and downgrade were tested on disposable MySQL. Downgrade refuses to delete tables containing audit evidence. Original membership/payment/wallet records are not rewritten by migration.

**Applied locally after explicit user authorization and green verification.** Backup and migration details are in the local release report. External staging/production deployment still requires its own authorized target, backup and acceptance. No automatic migration or activation occurs at app startup.

## Verification

- Broader focused backend run: **91 passed**, covering new cancellation/transfer tests, MySQL concurrency, upgrade/downgrade, existing QR/access, membership pause and customer-review history tests. Run artifacts: `C:\Users\ckishor\AppData\Local\Temp\fitigo-isolated-b8798897fa778b86-9gmj5x7p`.
- Final focused run after ownership-lock hardening and an additional old-booking-QR test: **37 passed** across `test_customer_policy.py` and `test_customer_policy_mysql.py`. Artifacts: `C:\Users\ckishor\AppData\Local\Temp\fitigo-isolated-aa354571344ccf00-t_akny_w`.
- Initial full backend suite: **801 passed, 23 failed**, before the discovered scanner lock-order fix. A final full rerun is reported separately below; don't treat this initial count as the final code's full result.
- Completed full rerun after the scanner fix: **805 passed, 22 failed** in 18m16s. Artifacts: `C:\Users\ckishor\AppData\Local\Temp\fitigo-isolated-5427e52d9e6f5d9b-1wyj2wcq`. This run was started before the final small ownership/history refinements; those refinements were covered by the final focused run, not a third full-suite run.
- Latest frontend suite: **441 passed, 1 failed** of 442. Failure is the unchanged legacy assertion in `financialScope.test.mjs`, requiring text that cancellation never credits wallets. This conflicts with the new business policy. TypeScript and production build pass.
- New isolated mocked browser suite passes cancellation confirmation/denial/conflict/credit results, transfer explicit confirmation/stable retry key, original/recipient views and single-gym restrictions. Dialog overflow checks pass at 360/768/1440px. This uses synthetic fixtures, not real customer funds or accounts.

Known old-policy backend conflicts include cancellation of pending/near-start or synthetic-payment bookings, unlimited/repeated owner cancellation, no-wallet-credit assertions, and rescheduling a confirmed booking past its cutoff. The support migration test hardcodes an earlier `head` revision. Two wallet-topup cancellation tests expect cancellation of unverified/open gateway orders and currently fail 409; do not weaken that payment safety check. These need explicit test/spec reconciliation before release.

The 22 full-run failures are: 8 customer/owner cases in `test_admin_financial_integrity.py`; 3 in `test_booking_access_qr.py`; 1 each in booking capacity, Cashfree payments, notification retry, Phase 5 MySQL, Phase 5 workflows, and Phase 6 operations; 2 Razorpay cancellation cases; 1 support migration-head assertion; and 2 wallet gateway-history cancellation cases. The latter two also fail when run separately; a clean pre-change baseline was not available, so they are not claimed to be proven pre-existing failures.

Read-only verification confirmed the working database remains at `a13b4df67935`, with neither new policy table present. Both isolated MySQL runner instances shut down their owned servers after completion.

## Files

All paths below are under `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo` (absolute workspace root).

Created backend files:
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\models\customer_policy.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\schemas\customer_policy.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\services\booking_cancellation.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\services\membership_transfer.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\services\policy_schema.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\alembic\versions\b24c5ef78046_customer_policies.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\tests\test_customer_policy.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\tests\test_customer_policy_mysql.py`

Modified backend files:
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\models\__init__.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\schemas\booking.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\schemas\booking_owner.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\schemas\admin_booking.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\schemas\membership.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\schemas\profile.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\routers\bookings.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\routers\cart.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\routers\memberships.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\routers\profile.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\routers\gym_owner.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\routers\admin.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\services\booking_service.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\services\booking_access_service.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\services\access_service.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\services\membership_service.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\services\owner_booking_policy.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\services\owner_member_service.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\services\admin_booking_ops_service.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\services\payment_checkout_service.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\services\notification_workflow.py`

Created frontend files:
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\components\booking\BookingCancellation.tsx`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\components\membership\MembershipTransfer.tsx`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\admin\MembershipTransfers.tsx`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\scripts\customerPolicy.test.mjs`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\scripts\customer-policy-browser.mjs`

Modified frontend files:
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\pages\booking\BookingDetailPage.tsx`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\pages\booking\BookingsPage.tsx`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\pages\membership\MembershipOverview.tsx`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\components\membership\TodayMembershipAccess.tsx`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\components\membership\MyAccessCard.tsx`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\components\common\CancellationNotice.tsx`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\services\bookingService.ts`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\services\accountService.ts`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\services\myAccessService.ts`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\utils\membership.ts`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\screens\Admin\api.ts`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\screens\GymOwner\api.ts`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\admin\Bookings.tsx`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\admin\MembershipPlans.tsx`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\owner\Bookings.tsx`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\owner\Members.tsx`

Verification artifacts: `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\policy-unit-results.txt` and `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\policy-build-results.txt`. Git CLI was unavailable; no commit was made.