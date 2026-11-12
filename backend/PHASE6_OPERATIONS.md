# Phase 6 — operational foundations (implementation, not working deployment)

> Subsequent local activation is recorded in
> `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend/LOCAL_NONFINANCIAL_COMPLETION.md`.
> The deployment boundary below describes this phase before that activation.

## Approved scope

The user's approval followed the explicit Phase 6 proposal: expanded operational
audit, admin filtering, truthful capability text and safe photo management.
It does not authorize subsequent financial phases, working-data reconciliation,
real refunds/messages or deletion of existing working photos.

Existing uncommitted work was preserved. No working migration, environment-file
edit, cleanup-worker execution, production photo deletion, provider request,
git reset/stash/commit/push or deliberate server restart was performed. The
development backend/frontend were already auto-reloading this source tree.
An intermediate syntax error during editing caused test collection to fail and
could affect that dev worker until corrected; final syntax/tests passed.

## Deployment gate (important)

New additive revision **df081ac34602**, parent **cef70fb23591**, creates:
- `operation_audits`: actor, action, resource/type, controlled reason code,
  allowlisted context and timestamp.
- `photo_deletions`: exact image/gym/actor, original generated relative path,
  resolved storage root, SHA-256 file fingerprint, status/error/attempt count and
  completion time. No foreign-key cascade can remove evidence automatically.

**OPERATIONAL_WORKFLOWS_ENABLED defaults to false.** `.env.example` documents it;
the working `.env` was not changed. When disabled, mutation audit writes are not
attempted, the old audit sources remain readable, deletion returns a clear 409,
and the photo UI shows disabled status. This prevents a repeat of the Phase 4
code/schema mismatch on a running local auto-reload instance.

With the flag enabled, missing audit tables cause startup validation to fail.
Runtime mutations do not silently skip audit failures: their transactions fail.
This flag is a deployment switch, not proof of schema integrity or an authorization
switch. Existing role/ownership checks still apply.

Migration tests cover an empty upgrade/downgrade/re-upgrade, source-user data
preservation, idempotent DDL resumption and refusal to downgrade either populated
table. Nonempty evidence/jobs require explicit archival, not a destructive rollback.

## Implemented

### Admin filtering and reasons

User-role filtering now occurs in SQL before limit/offset using a membership
subquery. Multi-role users do not multiply rows. The existing list response remains
compatible. Frontend uses a single filtered 21-row lookahead to display 20 rows;
it no longer makes an unfiltered request or suggests sparse role pages are normal.

Account status accepts ACTIVE/INACTIVE/SUSPENDED/BANNED, not arbitrary strings.
Status updates lock the user and produce one event only when status changes.
Frontend sends a selectable `reason_code`: ADMIN_REQUEST, SECURITY,
POLICY_VIOLATION, DUPLICATE, CORRECTION or OTHER. The legacy optional free-text
`reason` remains accepted for wire compatibility but is **not copied into audit**.
No raw personal text, password or credential is needed to explain an event.

### Transactional audit coverage

After deployment enablement, these writes append an event in the same transaction:
- Admin account-status changes.
- User profile/contact updates (only a contact-changed boolean, not values).
- Password change/reset (no password, hash, token, IP or email).
- Customer/owner/admin booking cancellation, direct rescheduling and owner/staff
  no-show; reschedules include original/destination slot IDs and dates.
- Permitted admin legacy payment-status changes (not provider refunds).
- Staff assignment acceptance and staff removal, with actual actor identity.
- Photo add, cover selection, ordering, removal request and file-cleanup completion.

The shared record writer accepts only known action/reason codes and typed context
keys. Arbitrary dictionaries are rejected. ORM update/delete of audit records is
blocked; no audit mutation API exists. This is application-level append-only
evidence, **not tamper-proof storage**: database administrators/raw SQL can still
change tables. Production credentials/retention/archival must be managed accordingly.

`GET /admin/audit-logs` merges these records with existing gym-review and plan-audit
sources, paginates on the backend and exposes safe contextual keys. Raw historical
reason/JSON fields remain excluded. The UI displays coverage and whether expanded
audit is enabled; it does not claim a complete security/platform history or
retroactively reconstruct old actions. Existing endpoints remain admin-only and
no-store. System/legacy events can have no actor; the UI says so rather than
inventing a user.

Not covered by this phase: complete login/security telemetry, every check-in,
every invitation delivery/revoke, all gateway transitions, all gym field changes,
or external immutable audit storage. Existing domain history remains in place.

### Recoverable photo deletion

New authenticated owner routes:
- DELETE `/gym-owner/gyms/{gym_id}/images/{image_id}`
- GET `/gym-owner/gyms/{gym_id}/image-deletions`
- POST `/gym-owner/gyms/{gym_id}/image-deletions/{job_id}/retry`

All are under `/api/v1`; cleanup list is no-store and capped at 100 pending/blocked
jobs. The explicit worker can process subsequent bounded batches.

Algorithm:
1. Verify deployment gate, role and current gym ownership; lock gym/image/job.
2. Accept only uploader-generated `gyms/gym_<id>/<32 hex>.<supported extension>`
   paths. External/legacy path formats require manual review (409, unchanged).
3. Reject traversal, absolute paths, links/junctions below the trusted resolved
   upload root, hardlinked files and shared references, including canonical
   backslash/path aliases. Record file fingerprint and resolved storage root.
4. Commit a durable deletion job, gallery removal, deterministic replacement cover,
   compact remaining display ordering and audit event together. No file is deleted
   before this commit. A failed commit leaves both metadata and file intact.
5. Recheck job ownership/lock, configured root, references, path and fingerprint.
   Delete only that exact file. Missing files are safe to complete. Permission/I/O
   errors remain PENDING; changed files/root/unsafe references become BLOCKED.
6. Commit completion and audit. If interrupted after unlink, retry sees the missing
   file and completes once. Duplicate requests/concurrent workers reuse the job.

Response explicitly separates `removed_from_gallery` and `file_deleted` with
status/error code. The UI requires confirmation, hides removal controls when the
gate is disabled, and offers a retry for pending/blocked cleanup. It does not
claim a successful physical deletion when only gallery removal succeeded.
Removal is irreversible through the UI; this is recoverable job execution, not a
photo undo/quarantine feature. Keep media backups before enabling it.

The local-storage assumption is a trusted application-owned upload directory:
untrusted users must not have OS-level write/rename access to it. Path checks are
defense in depth, not a filesystem sandbox against an adversarial local process
swapping paths between validation and unlink. Object storage is not supported by
this deletion implementation. Original storage root changes block cleanup until
an operator reviews/migrates jobs; the worker never switches targets implicitly.

An explicit worker is available at:
`C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend/app/scripts/process_photo_deletions.py`
It previews queued count by default; `--execute` processes bounded jobs using the
same service. It was not run against working data. There is no automatically
installed scheduler: operator scheduling and monitoring are deployment tasks.

### Upload hardening

Ownership is checked before content processing/disk writes. Payloads are read
with a 5 MB bound. PNG chunk lengths/CRC/IHDR/terminator, JPEG frame/scan structure,
and static WebP RIFF/chunk/frame headers are checked; dimensions are capped at
16 megapixels. File extension is chosen from the validated MIME format, not the
supplied filename. Files are created exclusively with random names. Gym-directory
symlinks/junctions are refused, and the generic delete primitive now uses actual
path ancestry rather than a vulnerable string-prefix comparison.

These stdlib checks are **not a full image decoder/re-encoder, antivirus or content
moderation system**. Animated WebP is unsupported. No new unapproved image library
was installed. A decoder-backed sanitization pipeline and recovery for orphan
uploads after an ambiguous database commit/crash remain separate hardening work;
this phase does not delete such existing orphan files automatically.

### Capability messaging and notifications boundary

Authenticated `/meta/workflows` and admin `/admin/settings` expose actual deployment
flags, safe audit coverage and account-email/SMS readiness. The Photos page gets
its deletion capability from its authorized job endpoint. Customer Settings now
queries `/auth/otp/options`, distinguishing configured, unavailable and unknown
delivery rather than permanently claiming OTP is unconfigured. Configured does
not promise delivery. General notification preferences remain disabled.

Notification design for Phase 7:
- Mandatory security/account messages (reset, OTP, invite/security changes) remain
  distinct from optional operational/promotional updates.
- Define recipient/category/channel policy first; preferences need a persisted
  per-user model and authenticated GET/PATCH API.
- A durable outbox worker must enforce preferences, retry with backoff, track
  provider acceptance versus delivery failure, and avoid duplicate sends.
- In-app read/unread state is a separate per-user acknowledgement, not SENT status.
- No preference toggles or external-message tests were invented in this phase.

## Test evidence

All backend runs used the fail-closed runner and a NEW private MySQL instance;
SQLite fixtures remain in-memory. Filesystem tests use pytest temporary roots.
No test deleted existing photos or used working database credentials.

- Initial focused corrected run: 36 passed.
- First full enabled run: 649 passed, 5 failures caused by password fixtures missing
  the new audit table. Fixture schema was extended, not audit disabled.
- Full enabled run after repair: **658 passed**, no failures/errors/skips;
  artifacts `C:/Users/ckishor/AppData/Local/Temp/fitigo-isolated-958e7a544f125fa1-2dodrsbo`.
- Subsequent enabled targeted safety/migration/password run: **35 passed**;
  artifacts `C:/Users/ckishor/AppData/Local/Temp/fitigo-isolated-a685d061482dc09a-0val9_jn`.
- Final default-disabled full run: **661 passed**, zero failures/errors/skips,
  22,116 existing/deprecation warnings. Includes three additional safety tests;
  artifacts `C:/Users/ckishor/AppData/Local/Temp/fitigo-isolated-1e82e56fd682f9c3-1z48k0kk`.
- Frontend **396 tests passed**, TypeScript and production build passed.
- Browser suite passed 360/768/1440px: existing owner/member/profile/help/admin
  regression flow plus confirmation-before-delete, honest pending cleanup and
  successful retry. Initial browser timing failure was corrected to wait for the
  actual Photos tab rather than a gym name already present in the sidebar.
- Real MySQL concurrent deletion proves one job, one completion and no unrelated
  file deletion. Tests also cover rollback before/after unlink, root/fingerprint
  changes, shared/canonical references, traversal/hardlinks, ownership, default gate,
  unknown audit metadata, role filtering and migration guards.

Frontend/browser artifacts: `C:/Users/ckishor/AppData/Local/Temp/fitigo-phase6`.
Browser requests were intercepted; no real authenticated working mutations occurred.
Existing warnings/deprecations remain. Physical-device/provider acceptance is not
claimed by this phase.

## Deployment requirements / next decision

1. Review accumulated changes and approve a specific deployment window/target.
2. Back up the database **and uploaded media**; verify restore independently.
3. Stop/drain writers and apply `df081ac34602` with the feature flag still false.
4. Verify schema/indexes and actual upload-root identity/permissions. Do not enable
   cleanup if unrelated applications/users can write beneath that root.
5. Enable OPERATIONAL_WORKFLOWS_ENABLED=true privately and restart compatible
   backend instances. Deploy matching frontend; verify capability flags and safe
   read-only endpoints before authorized test-account mutations.
6. Establish cleanup-job monitoring/retry scheduling and evidence retention policy.
7. Retain data on rollback: disabling the flag stops new operational records and
   deletions; do not downgrade populated audit/job tables or restore media blindly.

Working migration/flag changes were deliberately NOT performed here. Features
that do not need new tables (filtering, messaging, validation) can be reflected in
the existing dev auto-reload process. Photo deletion/expanded audit stay disabled.

Remaining financial decisions (refunds, gateway rescheduling, wallet spending,
gateway offers), notification delivery, orphan reconciliation and legacy class
link review remain separately approved phases. Accidental fixtures and historical
orphan records are untouched.