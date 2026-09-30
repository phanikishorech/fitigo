# FitiGo customer and owner web application

React 18 + TypeScript + Vite. Customer pages use the existing FastAPI services; no mock backend or additional runtime libraries are installed. Owner/admin routes remain available and are loaded separately.

## Run locally

From `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend`:

```powershell
npm install
npm run dev
```

The existing Vite proxy forwards `/api` and `/uploads` to the backend on port 8000. No backend credentials belong in frontend environment variables.

## Sign in

Open the Sign in modal and choose **OTP** or **Password**. Password sign-in uses the existing `/api/v1/auth/login` endpoint with your account email and password. Both methods use the existing session handling and preserve your intended customer route.

Local OTP delivery is not configured in the backend; use Password for local authenticated testing. The documented seed credentials are not guaranteed to match an existing database—the default customer password was rejected during verification. No existing passwords were reset.

## Automated checks

```powershell
npm run typecheck
npm test
npm run build
```

## Deployment

Serve `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\dist` through an HTTPS web server. Route `/api` and `/uploads` to the backend before the SPA fallback; other application routes must fall back to `index.html`. The development Vite proxy is not a production reverse proxy. Do not expose the repository root or `.env` files.

Use HTTPS for location, clipboard, and camera access. Staff scanning additionally requires native browser `BarcodeDetector` support; unsupported browsers display a clear message rather than accepting unvalidated access.

## Architecture

- Customer route mapping: `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\customerRoutes.ts`
- Page composition and route-level code splitting: `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\pages\CustomerApp.tsx`
- Typed services: `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\services`
- Shared components: `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\components`
- Design tokens and responsive styles: `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\customer.css`
- Central in-memory booking draft: `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\store\bookingStore.ts`

## Important release limitations

This is not yet cleared for public financial transactions. The existing backend directly credits wallet topups and records membership payments as `DUMMY`. New customer UI gates both operations to development builds and identifies them as MVP operations. Production builds explain that payments/recharge are unavailable instead of pretending to use a payment gateway. Spending an existing wallet balance uses the real wallet checkout endpoint.

The backend has legacy development-account fallback behavior on some customer APIs. The new client validates identity first, but server-side authorization must be hardened before deployment. The existing localStorage token strategy is retained; it has not been replaced with invented cookie endpoints.

Favorites persistence, profile editing, coupons, price filtering, dedicated per-visit review state, and cart editing lack the required API contracts. They are not simulated. Reviews follow the existing one-review-per-user-per-gym update behavior.

Full endpoint mapping, limitations, and verification notes: `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\IMPLEMENTATION.md`.

## Gym owner portal

Open `/owner/login` or `/owner/register`. The owner workspace starts at `/owner/dashboard`; the `/owner` alias remains supported. Customer and admin routes are unchanged.

- Responsive desktop sidebar and mobile Home/Gyms/Bookings/Check-in/More navigation.
- Shared authentication and HTTP client; selected gym is persisted per authenticated user.
- Real API integration for gym setup, photos, facilities, operating hours, plans, owner class/slot records, bookings, staff assignments, notifications and portfolio metrics.
- Assigned staff can use `/owner/check-in`; owner-only accounts receive an explicit permission explanation.
- Missing backend capabilities are explained, never replaced with mock business records.

Source: `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\owner`.

Verified endpoint mapping, acceptance limitations and test results: `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\OWNER_IMPLEMENTATION.md`.

Owner contract tests are included in `npm test`. The live browser suite is `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\scripts\owner-browser-smoke.mjs`; it uses an isolated Chrome debugging session on port 9231. Set `FITIGO_TEST_EMAIL` and `FITIGO_TEST_PASSWORD` to use an existing test account. The documented seed owner credentials were rejected by the local database during verification; no passwords were changed.

`FITIGO_TEST_CREATE_GYM=1` explicitly enables real draft/plan/slot mutation checks. `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\scripts\owner-local-qa.mjs` is a localhost-only opt-in bootstrap (`FITIGO_CREATE_LOCAL_QA=1`) that creates separate QA records and does not log credentials. QA records remain drafts because the API has no owner draft-delete endpoint.
