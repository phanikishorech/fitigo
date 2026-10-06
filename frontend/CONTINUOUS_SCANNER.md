# Continuous owner/staff check-in

The existing `/owner/check-in` screen uses a persistent video preview and jsQR. No new dependencies, backend authorization rules or attendance transactions were introduced.

## Behavior

- Auto-start once when the assigned-staff scanner mounts. A browser permission prompt is requested if needed. Denial shows **Allow Camera** and does not loop.
- The pure `scannerMachine.ts` reducer owns the seven primary states. `useContinuousScanner.ts` owns camera resources, decoding, API requests, permission events and timers. Event timestamps are supplied by the controller, not read inside the reducer.
- The existing `POST /checkins/validate` contract confirms entry with `success: true` and `status: CHECKED_IN`, plus member, gym, access type and check-in time. HTTP 200 alone is not approval.
- Approval/rejection overlays last 2 seconds, then automatically resume scanning without navigation or camera recreation.
- Duplicate protection combines a synchronous reducer guard, processing lock, a 2.5-second same-token cooldown and removal detection. A stationary QR is not repeatedly submitted. A different QR can be scanned immediately after the overlay; an identical QR can be deliberately re-presented after removal and cooldown.
- Technical errors return to scanning with a temporary **Unable to verify access** message. Requests time out after 12 seconds. Remove/re-present the QR to retry; a stationary code cannot trigger a request storm. Aborting a request does not undo a check-in already committed by the backend.
- The manual token form remains available, including when the camera cannot start. Manual results return to the previous camera/permission state rather than pretending a camera is running.
- Stop, hidden document, permission revocation, camera failure and unmount release media tracks, detection/result/request timers, listeners and pending requests. Generation/cycle guards discard stale responses and late camera starts.

## Existing backend constraints

- Scanning still requires `GYM_STAFF` assignment to the selected gym. A gym-owner role alone cannot bypass that backend requirement.
- The current endpoint groups some rejection causes into `INVALID_QR` or a generic inactive-membership message. The UI maps its known public messages without guessing an expiry or rendering raw exception text. More precise reason codes require a future backend response refinement; no membership rules were changed here.
- This update targets the owner workspace scanner. The separate legacy customer `/staff/check-in` screen is unchanged.

## Verification

- `npm test`: pure transition/guard, normalization and existing frontend regression tests.
- `npm run typecheck`, `npm run build`.
- `node scripts/owner-scanner-browser.mjs`: isolated Chrome CDP on port 9231, real jsQR decoder, simulated canvas camera and API responses. Covers continuous valid/rejected scans, stationary suppression, intentional reuse, technical errors/timeouts, permission changes, hardware errors/retry, manual tokens and cleanup.
- Physical device camera permissions and live authenticated staff check-in still require deployment/device QA. Fixture tests do not create real attendance records.