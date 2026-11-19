# Approved local transaction fresh start

Completed November 18, 2026 (observed host date), after the user explicitly selected:

> Back up and clear ALL test/live transaction history in the existing LOCAL database: payments, bookings, memberships, wallets, carts, QR passes, visits and dependent financial records. Preserve users, gyms, plans/pricing and commission settings.

This is a newly authorized destructive **local-only** reset. Earlier handoff statements about preserving historical records describe the previous tasks, not this approved operation. Their INR 300 collection/INR 750 wallet figures are historical pre-reset evidence and are no longer current balances.

## Target and result

- Database: `fitigo`, loopback MySQL port 3306, development environment.
- Verified server UUID: `77a92135-9d29-11f1-abed-00090faa0001`.
- Schema revision remains `d46e70ba9268`; no migration or schema modification.
- No production database or external gateway records were changed.

Cleared all rows from 20 approved transaction/activity tables. Nonempty counts removed:

| Records | Removed |
|---|---:|
| Bookings | 14 |
| Booking payments | 14 |
| Payment checkouts | 18 |
| Payment attempts | 19 |
| Purchased memberships | 3 |
| Platform membership orders | 2 |
| Wallet ledger transactions | 10 |
| Cart items | 14 |
| Access QR tokens | 17 |
| Check-ins | 2 |
| Customer daily accesses | 2 |
| Membership pauses | 1 |
| Cancellation records | 5 |
| Booking funding allocations | 7 |
| Checkout funding records | 9 |

Also cleared transaction tables already empty: access pause days, legacy membership daily accesses, membership transfers, webhook receipts and gym reviews.

All four existing wallet-account rows were retained with **balance 0.00 and payment_mode NULL**; two needed changes. Clearing the now-unfunded environment binding allows a genuinely new test/live wallet funding selection without retaining stale wallet-mode history. No users were deleted.

Removed six booking-cancellation notification events, their six deliveries and six booking-related operational audits. Preserved the security password-change notification/delivery, photo/password operational audits, notification preferences and catalog audit history. Support tables were empty and preserved.

## Preserved unchanged

All 31 designated preserved tables passed exact row/schema fingerprints, including:

- **6 users**, password hashes, profiles, verification state, roles and all 42 refresh tokens.
- **39 gyms**, ownership, staff assignments, images, facilities and operating hours.
- **92 gym slots**, prices/capacity definitions and schedule configuration.
- **12 gym membership plans**, **4 platform membership plans**, **3 offers**.
- **3 commission scopes and 1 configuration version**, including its terms, reason, actor and history.
- Application bootstrap/schema revision and account-security records.
- Uploaded media: archived, integrity checked and unchanged.

Class sessions and slot availability were empty at the baseline and remained empty. No catalog counters were guessed or pricing/status configuration rewritten.

No auto-increment resets: IDs are not reused. No TRUNCATE or foreign-key disabling. Database foreign-key integrity verified with zero orphans before and after.

## Backup and rehearsal

Private ACL-restricted backup directory, accessible only to the current Windows user and SYSTEM:

`C:\Users\ckishor\AppData\Local\FitiGo\backups\transaction-reset-20261118-122950`

Contains:

- `database.sql`: full pre-reset database dump, including preserved accounts/configuration and deleted transactions.
- `media.zip`: verified media archive.
- `manifest.json`: baseline row/schema/media hashes and dump/script identity.
- `rehearsal.json`, `applied.json`, `api-verification.json`: verification evidence.
- `reset_transactions.py`: one-time guarded local reset script; not an application endpoint.
- Private restore/dump logs and retained isolated restore data directory.

Dump SHA-256:

```text
8304b84afa98b7073c47fee5a279e8e5d0f0366d6c1599268445a8e32ed4c4f4
```

The dump was restored to a separate local MySQL instance with a distinct UUID/private datadir. All **55 tables' data and normalized schema fingerprints matched**. The exact reset was rehearsed twice: first rolled back and verified identical to the backup, then committed and verified. The isolated instance was shut down afterward.

Before working deletion, all row/schema fingerprints had to match the verified backup. The script took explicit write locks, used transactional child-first DELETEs, checked preservation/FKs and required its complete result to equal the rehearsal **before commit**. It refused unexpected schema, objects, gate values, target identity or baseline changes.

Backup contains sensitive account and financial data. Do not publish/commit it. Do not import it over new activity without another backup and explicit restore approval. Retaining a backup is not an instruction to restore automatically.

## Service and live API verification

The verified local Uvicorn launcher/reloader/server tree was paused during backup/reset; frontend and MySQL were left running. After verified commit, the existing backend start script restored the normal loopback API. Its usual pre-existing wallet-hold recovery lifespan resumed with no outstanding checkouts; no source/allocation/payout worker was started.

Runtime log directory:

`C:\Users\ckishor\AppData\Local\FitiGo\runtime\backend-20261118-123150-46e0c093`

Checks passed:

- `/api/v1/health`: HTTP 200.
- `/api/v1/health/db`: HTTP 200.
- Authenticated admin summary for both **test** and **live**, full-2026 range: zero bookings, memberships, visits, wallet balance and collections; collections complete for the now-empty eligible dataset.
- Financial-settings gym selector returns **39 gyms**.
- Saved commission history still contains **1 version** for its original gym/environment.
- Independent post-commit snapshot exactly matches rehearsed result, with no foreign-key orphans.

This was an operational reset, not an application-code change. Validation used full backup/restore/reset/rollback rehearsal and read-only API/database checks, not new purchases written into the clean working database.

## Boundaries and next steps

All four financial processing gates remain **false**:

- `source_evidence_enabled`
- `marketplace_allocations_enabled`
- `marketplace_live_allocations_enabled`
- `marketplace_payouts_enabled`

No provider payment/refund/payout call, production migration, production deployment or financial worker start. Gateway-side test orders and payment history remain at the providers; this reset only clears local application records. Old browser tabs/checkout links may refer to deleted IDs: refresh the app and start new bookings/checkouts rather than resuming an old payment page. Existing login credentials remain unchanged.

Old regression evidence files referencing pre-reset transaction IDs or the INR 300/750 dataset remain historical artifacts; hard-coded working-data probes from those earlier tasks must not be mistaken for current empty-database expectations.