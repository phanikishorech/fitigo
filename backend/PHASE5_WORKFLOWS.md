# Phase 5 — connected workflows and explicit capability limits

> Historical phase record. Phase 6 adds gated expanded audit and photo deletion;
> see `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend/PHASE6_OPERATIONS.md`
> for current implementation and separate deployment requirements.

## Result

Implemented the supported owner/admin workflows below without schema changes.
This is not a claim that every audited feature is implemented: manual attendance,
saved-photo deletion, delivery preferences, editable global settings, a complete
platform audit log, gateway rescheduling and refund initiation remain unavailable.
The UI/API communicate these limitations without simulated successful outcomes.

Final backend validation: **639 passed, zero failures/errors/skips**, through
the separate-server isolated runner. Frontend: **393 tests passed**, application
TypeScript and Vite production build passed. Mocked browser suite passed at
360/768/1440px. No working-data tests, messages, real payments or refunds ran.
Existing uncommitted Phase 1–4 changes were preserved.

## Owner booking actions

Existing frontend contract is an array, not an object. Owner list/detail/action
responses now add compatible fields:
- `allowed_actions`: `CANCEL`, `MARK_NO_SHOW`, or an empty array.
- `action_unavailable_reasons`: explanations keyed by action.
- `cancellation_policy`: explicit cancellation/refund distinction.

Existing authenticated owner routers verify role and gym ownership. The shared
server policy is recalculated under the booking lock before mutation. The UI
renders only permitted buttons and shows reasons plus a QR scanner link.

Cancellation preserves the existing no-time-cutoff rule for unused bookings;
the initial proposed cutoff was removed after regression exposed that it changed
existing business policy. Closed/attendance-recorded/scanned bookings cannot be
rewritten. Already-cancelled retries are idempotent and do not release capacity
or append history again. Cancellation retains payment status and never returns
money or credits. Payment-pending gateway bookings and class bookings identified
by session metadata are withheld because their checkout/session capacity must be
coordinated rather than partially updated.

No-show requires CONFIRMED, PAID, no prior attendance/successful check-in, and
the actual admission window to have ended. Unknown admission windows fail closed.
It records time/actor and optional note, revokes unconsumed passes and prevents
later overwrites. Staff's existing gym-assignment check remains, is rechecked
under lock, and the actual staff actor is recorded rather than the gym owner.

**Manual MARK_ATTENDED is explicitly rejected with 409** on owner/staff paths.
The old method did not verify entry or create a real Checkin; presenting it as
equivalent to scanning would be misleading. Actual attendance remains the tested
owner/assigned-staff QR flow, which checks access eligibility, payment, visitor,
gym, time and duplicate use. This is an intentional restriction of the insecure
legacy manual mutation, not a new admission mechanism. A future override needs
product authorization, reason/audit requirements, multi-visitor semantics and
revenue treatment before it can be enabled.

Checks cover wrong owner/staff, unavailable states, payment preservation,
successful scan conflicts, no-show timing and actual MySQL duplicate cancellation
(one capacity release and one history entry). Booking/attendance history is
preserved; actor/timestamp annotations append to existing notes. These notes are
not advertised as an immutable, comprehensive audit system.

## Payment/help accuracy

Customer Multi-Gym instructions and admin plan instructions use existing catalog
`checkout_available` and `payment_mode` values: Cashfree, Razorpay, development
wallet test credit, or unavailable. No hardcoded assertion about the user's
current gateway is needed. Gateway mode is confirmed at checkout. Plan/offer
save dialogs do not claim payments are disabled or imply a gateway-funded offer.

Owner Help describes owners scanning their own gyms, assigned staff scope,
personal membership access versus named booking visitors, gym-scoped history,
and unsupported operations. Cancellation and refund completion remain distinct.
The older checkout screen is labeled a legacy development wallet flow, not the
only payment option. Historical handoff documents remain historical records,
not user-facing runtime promises.

## Member directory/history

New authenticated owner endpoints (under `/api/v1`):
- `GET /gym-owner/gyms/{gym_id}/members?q=&limit=&offset=`
- `GET /gym-owner/gyms/{gym_id}/members/{user_id}?limit=&offset=`

The directory is built only from this gym's memberships, bookings and successful
check-ins; users with no such relationship cannot be enumerated. Name search is
literal substring search. Results have bounded pagination, total count and
deterministic ordering. History paginates bookings/verified visits and returns
gym-sold membership periods/status (including derived expiry/upcoming/pause).

No customer emails, phones, password hashes, tokens, payment references, notes,
other gyms' history or global Multi-Gym purchase details are returned. A Multi-Gym
visitor can appear through an actual visit but is not represented as holding a
membership sold by this gym. Names identify account holders/purchasers, not each
booking visitor. Only modern successful Checkin records are counted as verified
visits; legacy access tables/manual attendance are not fabricated as new visits.
The UI includes selected-gym scope, search, pagination and loading/empty/error
states; history navigation is local to the selected gym and resets on gym switch.

## Profile and notification preferences

Owner/staff Settings and Admin Profile now use existing `PATCH /users/me`.
Backend validation, contact-change password verification, verification reset,
token-version increment/session revocation and throttling are unchanged.
No roles/status/verification fields are client-editable. UI success appears only
after server acceptance; contact changes clear local tokens and request sign-in.
Name changes refresh server identity. Admin password controls reuse the existing
password-change flow, including global session invalidation.

**Notification preferences remain unavailable.** Existing NotificationService
stores events; it does not consume user delivery preferences or run a general
delivery worker. No fake toggle or unused preference database field was added.
Required future work: a per-user preference model, authenticated get/update API,
event-category/channel definitions (mandatory security notices distinct from
optional messages), and a delivery worker that enforces them with retry/status
tracking. Existing notification screens continue displaying recorded events,
not read/unread acknowledgements.

## Photos

- New `PUT /gym-owner/gyms/{gym_id}/images/order` accepts `{image_ids: [...]}`.
- Requires owner scope and the complete current ID permutation; duplicates,
  missing/foreign IDs and stale photo inventories return 409.
- Gym/image row locks serialize reorder with cover changes/upload. Reordering
  modifies only display_order; it does not touch files or change the cover.
- Cover remains first under existing read ordering; UI moves other photos earlier/
  later and refreshes only after server success.
- Upload now authorizes ownership before any filesystem write (previously the
  file was saved before the service rejected unauthorized gym ownership).

**Saved-photo deletion remains unavailable.** LocalStorageService has a raw
delete primitive, but no durable delete job/quarantine record coordinates a
filesystem deletion with a database commit and crash recovery. Deleting first
risks a live reference to a missing file; deleting metadata first risks unmanaged
objects. A production implementation needs a persisted tombstone/storage job,
strict resolved-path/gym ownership validation, reference checks, an idempotent
worker/recovery policy and confirmed UI deletion with cover reassignment. No
DELETE route or fake delete button was added. All new photo tests use temporary
storage or metadata-only fixtures; no existing photo was removed. Existing upload
failure/orphan-file recovery and file-content validation remain separate hardening.

## Admin settings and audit

New endpoints:
- `GET /admin/settings`: ADMIN/SUPER_ADMIN-only, read-only capability summary.
- `GET /admin/audit-logs?limit=&offset=`: ADMIN/SUPER_ADMIN-only paginated union of
  existing gym review transitions and membership-plan audit records.
- `GET /meta/workflows`: authenticated safe capability flags and limitations.

Settings show configured provider availability/mode and supported operations;
no secrets, URLs, credentials or database configuration are returned. No editable
global settings API/model exists, so the UI has no pretend save control.

Audit includes actor ID, known action, affected resource/type, timestamp and safe
enum transition context. Raw legacy reasons/JSON details are deliberately omitted;
they might contain private values or secrets. Unknown action strings become a
generic PLAN_CHANGE. Coverage is explicitly limited, not a complete activity,
authentication or security log. Backend authorization and no-store headers protect
these responses. Broader audit coverage requires a new append-only event model,
transactional writes in each mutation service, retention/privacy policy and
read-only authorized query API; it cannot be manufactured from current state.

## Rescheduling/refunds policy boundary

Existing direct non-gateway customer rescheduling remains: same-gym active slot,
future destination, locked capacity revalidation, paid confirmed price equality,
pending quote recalculation, no used pass, QR reference rotation when present.
It now serializes on the gym before booking/slot locks to match owner edits,
rejects class source/destination and attendance-recorded bookings, and appends
original/destination slot/date plus actor/time to history. Existing successful
reschedule tests now assert original/destination history.

Gateway-paid/payment-pending bookings remain blocked, including no-op attempts;
no new checkout/charge is created. New mocked gateway regression verifies this.
Policy needed before enabling: cutoff/limits, class versus direct reservation
handling, price increases/new payment approval, decreases/refund eligibility,
atomic capacity swaps, idempotency/retries and notification requirements.

Refund initiation remains unavailable. Phase 3 provider abstraction supports
order/payment retrieval and reconciliation, not initiating refunds. Existing
provider-confirmed refunds still reconcile independently. Required future work:
approved initiating roles/reasons, cancellation/no-show eligibility, full/partial
amount rules and fees; durable refund request/idempotency state; provider adapter
methods; timeout/retry/webhook reconciliation and safe history. No real provider
refund was attempted. Cancellation does not imply initiated or completed refund.

## Validation and deployment

Backend artifacts:
`C:/Users/ckishor/AppData/Local/Temp/fitigo-isolated-6c54307650087999-2u15ddrp`
Final full run: **639 passed**, 21,373 existing/deprecation warnings, no failures,
errors or skips. All existing MySQL opt-ins enabled. Includes QR/wallet/payment
regressions, new MySQL cancellation race and strict-mode member/audit queries.
No assertion was deleted/skipped to achieve the result. One old frontend test
that assumed every capability was unsupported now asserts the implemented versus
unsupported split explicitly. Initial missing-currency fixture and cancellation
cutoff failures were repaired and rerun; they are not counted as final success.

Frontend/browser artifacts:
`C:/Users/ckishor/AppData/Local/Temp/fitigo-phase5`
New tests:
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend/tests/test_phase5_workflows.py`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend/tests/test_phase5_mysql.py`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/frontend/scripts/phase5Workflows.test.mjs`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/frontend/scripts/phase5-browser.mjs`

Browser API requests are intercepted in an isolated browser context. Successful
checks do not claim physical-device camera testing, live authenticated mutations,
payment/refund execution, or every production concurrency scenario was exercised.

No migrations or model columns were added. Target environments must already have
Phase 4 revision `cef70fb23591`. Release backend and frontend together so capability
fields/new routes and screens match; restart backend/rebuild frontend normally
after review. This run did not issue a deployment/restart or any working business
mutation. The existing local uvicorn/Vite processes were running in auto-reload
mode, so source changes can already be reflected locally: this is not an isolated
source checkout. No claim is made that the running dev process remained on old
code. No production deployment is implied.

Accidental fixtures, orphan ledger/account/staff records and legacy class links
remain untouched. All accumulated source changes remain uncommitted. Preserve
private test artifacts; any further deployment/data cleanup requires its own
approved scope.