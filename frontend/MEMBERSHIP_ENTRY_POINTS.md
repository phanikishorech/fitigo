# Membership and home access entry points

Membership now renders the same TodayMembershipAccess / MyAccessCard as
`/access/qr` and `/my-access`. The button navigates to the existing
`/access/qr?generate=1` flow. QR issuance, validation, expiry, pause rules, daily
limits, offline hiding and scan polling remain unchanged. Viewing membership or
home never calls the QR issuance endpoint.

Home shows a compact membership card only for authenticated customers with a
backend-reported active/paused membership. Multi-Gym uses “You're a FitiGo member”;
Single-Gym uses the assigned gym name. Available access offers “Book a visit today”
and links to `/my-access`, not paid booking or cart. Used/paused/unavailable states
offer accurate status and a view-access link. Nonmembers/guests get no member
claim. Errors remain retryable rather than being interpreted as no membership.

Existing APIs only: membership summary/records, read-only access calendar,
customer identity, assigned gym details, pause eligibility and existing QR route.
Initial membership data is reused by its access card. Explicit/focus refresh
reloads fresh data. Home scopes/unmounts its resource by authenticated user ID.
No backend/API/schema/dependency changes were required.

Verified: 363 frontend tests, TypeScript check, production build; 43 backend
direct-access/pause/booking-QR regressions. Two mocked browser suites cover both
membership types, single explicit generation/double-click guard, home-to-access
navigation, paused/used/nonmember/guest/error states and responsive widths
360/390/768/1440. Existing My Access browser checks also cover offline/expiry and
issuance races. Browser fixtures do not represent real gym check-ins.

Files:
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/frontend/src/components/membership/TodayMembershipAccess.tsx`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/frontend/src/components/membership/HomeMembershipCard.tsx`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/frontend/src/components/membership/homeMembership.css`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/frontend/src/utils/memberHome.ts`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/frontend/src/services/myAccessService.ts`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/frontend/src/pages/membership/MembershipOverview.tsx`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/frontend/src/pages/access/AccessPage.tsx`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/frontend/src/pages/discovery/DiscoveryPage.tsx`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/frontend/scripts/myAccess.test.mjs`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/frontend/scripts/memberHome.test.mjs`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/frontend/scripts/my-access-browser.mjs`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/frontend/scripts/member-entry-browser.mjs`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/frontend/MEMBERSHIP_ENTRY_POINTS.md`