# Notifications and remaining non-financial work

> Final validation and local activation:
> `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend/LOCAL_NONFINANCIAL_COMPLETION.md`.
> 680 full backend tests, 39 post-fix checks, 399 frontend tests passed. Local
> inbox/operational features enabled; external email remains explicitly disabled.

## Approved scope

The user explicitly chose: complete notifications and other non-financial gaps;
keep refunds, gateway rescheduling, wallet spending and offers disabled. No new
financial policy, real charge/refund, external message, orphan repair or existing
photo deletion is authorized by this implementation. Legacy development test-credit
paths remain separate; configured-gateway wallet spending remains blocked.

## Implemented

- Shared customer, owner/staff and admin notification center with backend-persisted
  optional operational email preference, unread filter, pagination, count and
  idempotent per-notification mark-read. Identity is always authenticated, never
  accepted as an editable request field.
- Transactional in-app events/outbox rows for booking cancellation, existing direct
  rescheduling, gym review changes, staff removal, profile update and password
  change/reset. Mutation rollback removes both event and delivery intent.
- Safe fixed templates: no passwords, reset links, OTPs, user-supplied reasons,
  payment credentials or provider diagnostics in the new payloads. Resource IDs
  and fixed messages point users back into the application.
- Read/unread is independent from email processing state. Existing unrestricted
  legacy events remain available separately as recorded history, not proven delivery.
  Legacy API response payloads/errors are allowlisted; arbitrary event names are
  labeled LEGACY_EVENT. The old manual mark-sent endpoint now returns 409 rather
  than fabricating successful delivery.
- Admin-only paginated email-processing view, without addresses/hashes/claim IDs
  or send/retry controls. UNKNOWN messages require operator investigation.
- Configurable support email through `/meta/support`, with email validation and
  honest absent/error states. No invented address, response-time guarantee or
  fake ticket-submission screen.

Supported new routes under `/api/v1`:
- GET/PATCH `/notifications/preferences`
- GET `/notifications/inbox?limit=&offset=&unread=`
- POST `/notifications/inbox/{id}/read`
- GET `/notifications/delivery-status` (ADMIN/SUPER_ADMIN only)
- GET `/meta/support`

Existing `/notifications/me` and `/pending` now have bounded pagination and
no-store responses. Raw legacy payload/error content is deliberately no longer
exposed. Historical entries are not backfilled into email jobs.

## Email semantics / privacy

Email is independently gated by NOTIFICATION_EMAIL_ENABLED, false by default.
Operational email defaults to off and requires explicit user opt-in, verified
email and a configured channel. Opt-out is always permitted even if the channel
later becomes unavailable. No SMS/push preference is displayed as functional.

Security notices are not disabled by the optional operational preference. OTP,
reset-link and staff-invitation delivery retain their existing separate protected
flows. The new worker sends only generic post-action notices. A contact change
that clears verification does not send to the unverified destination; an old-address
security notice is not implemented or claimed. Inbox evidence still exists.

Queue creation never performs network I/O. User changes made while the email
switch is off produce NOT_REQUESTED, not a backlog to send on later activation.
Worker rechecks account activity, verified email, the originally selected email
hash and current preferences under locks before claiming a send. Changed recipient
or opted-out jobs become SUPPRESSED. A preference change after a durable dispatch
claim cannot recall an in-flight email; this is disclosed in settings.

States:
- NOT_REQUESTED: no email selected when the event occurred.
- QUEUED / WAITING: not sent; waiting for a worker/configuration.
- DISPATCHING: durable claim before SMTP I/O.
- ACCEPTED: the transport confirmed server acceptance, **not inbox delivery**.
- UNKNOWN: interrupted or uncertain send; no automatic retry.
- SUPPRESSED: account/contact/preference no longer eligible.
- FAILED: bounded pre-send attempts exhausted or unsupported template.

Pre-send channel-unavailable checks back off (bounded to five attempts). The
existing SMTP transport collapses exceptions to sanitized failures, so a failure
after dispatch is conservatively UNKNOWN rather than retried. A stale claim older
than five minutes becomes UNKNOWN. A successful send followed by failed DB commit
also remains uncertain and is not replayed. Duplicate concurrent workers cannot
take a second claim. This favors avoiding duplicate messages; it is not an
exactly-once-delivery guarantee and may leave unsent messages needing review.

Worker:
`C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend/app/scripts/deliver_notifications.py`

It previews a bounded job count by default; `--execute` may send email only if the
separate switch is enabled. No scheduler is automatically installed and no worker
was executed against working recipients. Provider bounces/delivery receipts are
not integrated: ACCEPTED never becomes DELIVERED without evidence.

## Schema / gates

Additive migration `ef192bd45713`, parent `df081ac34602`, adds
`notification_preferences` and `notification_deliveries`. Existing events are
untouched. A unique event link prevents duplicate intents per event. Business
mutation idempotency prevents duplicate cancellation events on retries.
Downgrade refuses nonempty preference/delivery tables until explicitly archived.

- OPERATIONAL_WORKFLOWS_ENABLED: Phase 6 audit/photo capability gate.
- NOTIFICATION_WORKFLOWS_ENABLED: inbox/preference/new-event generation gate.
- NOTIFICATION_EMAIL_ENABLED: independent external email gate, default false.
- SUPPORT_EMAIL: optional validated support contact, not credentials.

Startup checks required tables before enabling workflow flags. Missing tables do
not lead to silent audit/notification omission. Disabled mode avoids querying new
tables. No dependency/library was added.

## Test evidence and remaining acceptance

Tests cover scoped preferences and read state, malicious fields, rollback, safe
payloads, default-off behavior, suppression, bounded pre-send retry, uncertainty,
post-send commit failure, duplicate cancellation, admin visibility, migration
roundtrip/archival and actual MySQL concurrent workers/preference writes.
All database tests use the managed isolated runner; message delivery is mocked.
The new `--notifications` runner flag enables inbox behavior without enabling a
real sender. `--test-timeout` adds a bounded 60..3600-second allowance for slow
machines; it never removes the database safeguard.

Initial selected run: 26 passed, two failures (fixture tuple shape and MySQL
fractional timestamp rounding). Fixed fixture and second-precision queue times.
First full enabled run: 675 passed, one failure from a minimal gym-review fixture
missing the new tables. Fixture schema extended, not the feature disabled.
Final results are recorded in the local completion handoff after verification.

Frontend mock browser checks cover failed/successful preference updates, read
tracking, UNKNOWN email, admin processing, and prior owner/photo workflows at
360/768/1440px. Test requests are intercepted. No real SMTP/SMS/provider/dashboard
acceptance or physical-device camera test is implied.

Still needed before external sending: approved sender/domain/credentials, verified
test recipients, explicit authorization to send, worker scheduling/monitoring,
bounce handling and retention policy. SUPPORT_EMAIL must be supplied by the
operator; it is left unset rather than guessed.

## Explicitly not “all gaps complete”

The approved financial exclusions remain. Other product extensions (custom staff
roles, manual attendance overrides, overnight schedules, comprehensive immutable
audit, editable global policy settings, gym/draft deletion, true contact re-verification,
push/SMS operational notifications, support ticketing) are not silently enabled.
They require their own policy/storage/service work. Orphan/account/ledger repairs,
accidental fixture cleanup and legacy class links remain untouched. Upload decoder/
malware scanning and crash-orphan upload recovery are still hardening items.