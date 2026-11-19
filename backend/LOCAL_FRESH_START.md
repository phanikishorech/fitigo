# Approved local fresh start

User explicitly approved retaining only admin@gmail.com, customer1@gmail.com,
gymowner1@gmail.com and gymstaff1@gmail.com, clearing activity and balances,
and transferring gyms owned by removed accounts to gymowner1@gmail.com.

## Result

- Local development database `fitigo`, loopback MySQL port 3306, 49 tables.
- 76 accounts removed; four active accounts retained with identical passwords,
  profiles and role mappings. Token versions incremented; refresh/reset/OTP
  sessions cleared. Users must sign in again.
- All 39 gyms retained. 34 owner references transferred; all other gym fields
  unchanged. Four retained staff assignments preserved.
- All approved activity cleared: 27 bookings, 27 booking payments, 22 gateway
  checkouts, 15 attempts, nine webhook receipts, 36 cart items, nine purchased
  memberships, 18 membership orders, 45 wallet transactions and related access,
  check-in, review, support, notification and activity/audit records.
- Retained wallet accounts have zero balances. Removed-user wallets deleted.
- Gym photos, facilities, valid slots/hours, membership plan definitions and
  catalog offers retained. Media contents unchanged (13 files).
- Removed pre-existing orphans: 931 slots and 14 operating-hour rows referencing
  nonexistent gyms. The 82 slots and 56 hour rows attached to real gyms remain
  unchanged. All declared foreign-key relationships validated with zero orphans.
- No schema migration, TRUNCATE, foreign-key disabling or auto-increment reset.
  IDs are not reused. No payment/refund/provider call was made for this reset.
  Gateway-side sandbox orders/history remain outside the local database.

## Backup and validation

Private, ACL-restricted directory (contains sensitive data; do not share/commit):

`C:/Users/ckishor/AppData/Local/FitiGo/backups/fresh-start-20261112-185253`

Contains database.sql, media.zip, manifest.json, rehearsal.json, applied.json
and the one-time guarded reset script. Database dump SHA-256:
`cb7b119f81e37010a69eb81fe4ef9491d743a52f3e4580fe9ad66bcaf8d14ac6`.

Restore rehearsed on a separate loopback MySQL instance with a distinct UUID and
private datadir. All table data/counts and normalized DDL matched. Only redundant
explicit character-set clauses were normalized in the schema comparison.
The approved reset was rehearsed and verified there before touching working data.
Media ZIP integrity and per-file hashes verified.

Working reset used explicit table write locks and transactional DELETE/UPDATE.
The complete pre-reset fingerprint had to match the verified backup before any
deletion. Post-reset result matched the rehearsal before commit; repeated checks
verified data, roles, credentials, preserved catalog and media after commit.
Pre-existing activity orphans were removed with their approved activity tables.

FitiGo on 8000 was stopped for maintenance and restarted; port 8000 was not
stopped. Table locks protected against concurrent writers. Isolated restore
servers shut down; private diagnostic files retained.

Post-restart `/api/v1/health` and `/api/v1/health/db`: HTTP 200, healthy.
Runtime: `C:/Users/ckishor/AppData/Local/FitiGo/runtime/backend-20261112-185818-7d0049c9`.

Do not import the dump over new working data without a separate reviewed restore
plan and a new backup. It contains sensitive pre-reset accounts and transactions.