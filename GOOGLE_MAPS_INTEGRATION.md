# FitiGo Maps integration — November 12, 2026

## Subsequent UI simplification

Gym Details now has only a **Get Directions** link inside the existing sidebar, below opening hours and above the booking divider. The separate map/directions section and its component were removed at the user's request. The link opens Google Maps directly with the gym's validated coordinates, without asking for geolocation or loading Google Maps JavaScript. Invalid coordinates show a small location-unavailable label in the same sidebar. Booking and membership actions are unchanged. Home discovery maps and owner pin selection are unchanged. Embedded-route descriptions and their original test results below describe the previous implementation, not the current Gym Details UI. The browser regression script now checks the simplified external-link flow instead.

## Status and release gates

Implemented against React 18.3 / Vite 6 and FastAPI / SQLAlchemy 2 / MySQL. No package dependencies were added. Existing global CSS, fonts, shared tokens, navigation styling and booking/membership flows were not redesigned.

**Not yet live-Maps verified.** Google Cloud credentials, billing, API restrictions, quotas, a production map ID, and real-device verification must be supplied/completed by the project operator. Mocked tests do not establish that a Google project is configured correctly.

Local database migration `a13b4df67935` was applied successfully. Deploy it before deploying backend code to other environments. Back up each environment first and schedule large-table index creation appropriately.

## APIs and configuration

Google services used: Maps JavaScript API (`maps`, `marker`, and on-demand `routes` libraries), Routes API for route calculations, and Google Maps directions URLs for external navigation. No Places gym search, Geocoding API, Google Geolocation API, server key, or address auto-geocoding is used.

Set these build-time variables in `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\.env.local` or the deployment build environment:

```dotenv
VITE_GOOGLE_MAPS_API_KEY=your_restricted_browser_key
VITE_GOOGLE_MAPS_MAP_ID=your_javascript_map_id
```

The empty template is `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\.env.example`. Existing ignore rules exclude actual environment files. Browser keys necessarily appear in browser requests/bundles; restrictions, not secrecy, protect them. Never put server credentials in VITE variables.

Google Cloud setup:
1. Select the intended project and attach billing.
2. Enable Maps JavaScript API and Routes API only for this integration.
3. Create a JavaScript map ID in Maps Management; use it in the variable above. Do not use a demo ID.
4. Create separate development and production browser keys. Apply Websites / HTTP-referrer application restrictions to the exact allowed HTTPS hostnames (and explicit localhost development origins on the development key). Avoid broad wildcard domains.
5. Apply API restrictions allowing only the required APIs. Verify browser Routes-library requests using the restricted key; do not call the REST Routes service directly from frontend code or remove restrictions to bypass an error.
6. Set quotas appropriate to expected map loads and route requests; configure usage monitoring, budget alerts, and operational alerts. Budget alerts alone are not a spending cap.
7. Serve over HTTPS. Ensure the deployment CSP permits the Google Maps script, connection, image and worker resources required by Google's CSP guidance. The loader copies an existing script nonce when available. Do not disable CSP globally.
8. Rebuild/redeploy the frontend after configuring variables. Test valid and invalid referrers, denied quota, offline loading, and all supported travel modes in your region.

Official references (documentation paths): Google Maps JavaScript / load-maps-js-api; / routes/start; / reference/route; Maps / api-security-best-practices; Maps / documentation/urls/get-started. The loader uses the quarterly channel and direct asynchronous loading followed by importLibrary. Only requested route fields are retrieved.

## Existing backend contracts reused

`GET /api/v1/gyms/discover?latitude=...&longitude=...&radius_km=10&page=1&page_size=12`

- Same search, city, facilities, rating, open-now, membership, sorting and pagination contract.
- Coordinates must be paired, finite and within geographic ranges. Radius validation remains 0.1–200 km for compatibility; UI offers 5/10/20/50 km.
- APPROVED + is_active are the existing public-discovery eligibility rules; the model has no separate private/deleted flag. Other statuses are excluded.
- Database bounding-box filtering uses `ix_gyms_discovery_geo(status,is_active,geo_latitude,geo_longitude)`, including dateline and polar cases. Exact spherical distance, filters, total count, sorting and pagination run in SQL before card enrichment. The old 700-record cutoff is removed.
- Adds real `starting_price` (existing per-visit price) and `is_active`; preserves images, ratings, facilities, coordinates and backend-calculated distance.
- Straight-line discovery distance is not a road-route distance. Route distance/duration come only from Google route responses.

Also reused: `GET /api/v1/meta/locations`, `GET /api/v1/gyms/{id}/details`, and existing authenticated owner gym create/update endpoints. Public browsing remains public; existing optional-user membership enrichment and owner authorization are preserved.

## Coordinates and audit

Migration adds nullable numeric `geo_latitude` / `geo_longitude` projections alongside original strings. Batched backfill copies valid pairs only. Original coordinates are not rewritten. ORM insert/update listeners keep projections synchronized. Future bulk SQL importers must explicitly maintain both projections or use the ORM; this is not a database trigger.

Owner Location step now supports ranged numeric input, existing at-gym geolocation capture, and a lazy map for checking/correcting the pin. Coordinates remain editable even when Google is unavailable. Completing Location requires a pair; drafts can still be saved before that step. Existing approval workflows are not retroactively blocked. Administrators must enforce the audit release gate for active gyms.

Read-only audit command:

```powershell
Set-Location 'C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend'
& '.\.venv\Scripts\python.exe' -m app.scripts.audit_gym_coordinates
```

Local audit: 39 gyms, 32 missing coordinate pairs. Affected IDs: 1637–1668 inclusive. Of these, 1647 is inactive; 1664 and 1668 are drafts. The remaining 29 are approved active gyms requiring owner-confirmed locations. Seven records have valid coordinate pairs. No locations were guessed, no geocoding was performed, and gym statuses were not changed. Missing coordinates exclude gyms from radius discovery and produce a location-unavailable section on Details, rather than an incorrect pin.

## Customer location and behavior

- Existing manual selection remains persistent and takes precedence. Home requests browser location once per page lifetime when no area is already selected. Current location, accuracy and timestamp stay in memory; old persisted `Current location` records are removed.
- A later manual selection wins over an outstanding geolocation callback. Use current location explicitly returns discovery to the device location. Permission revocation clears the current position and falls back to the saved manual area.
- Denied/unavailable/timeout/unsupported/insecure contexts retain list discovery and manual area selection. A browser without permission-query support still uses geolocation error callbacks.
- Search is debounced; discovery reads are deduplicated with a two-second memory cache and auth-change invalidation. No precise-location persistence is introduced. Production access logs must redact discovery latitude/longitude query parameters if they currently log full URLs.
- Map/list share the same results page, area and radius. Markers are clustered using a zoom-dependent grid; at high zoom all markers are individually selectable. Pagination deliberately bounds marker volume. Panning does not silently change the search center. Preview selection does not refit the map.
- Directions use current device coordinates, never a manually selected discovery area. Switching mode clears the previous route. Google failures retain Open in Google Maps. Without origin permission, Get Directions navigates to the destination-only URL in the same tab, avoiding asynchronous popup blocking. Actual app handoff depends on device settings.

## Verification performed

- Frontend `npm test`: **430 passed**, including 10 new maps tests.
- `npm run typecheck`: passed.
- `npm run build`: passed; map components are split into lazy chunks.
- `node scripts/maps-browser.mjs`: passed with intercepted APIs, geolocation and Google Maps objects in an isolated Chrome context. Covers granted/denied/unavailable, four radii, marker preview/navigation, map/list preservation, two manual areas, four route modes, revoked permission, destination-only fallback, empty results, API error/retry, missing coordinates and Maps-unconfigured fallback. Layout overflow checked at 360/768/1440 pixels.
- Isolated backend runner: **53 passed** across geo discovery, geo migration, strict MySQL, owner review, admin submissions and platform membership regression tests. Existing deprecation warnings remain. Strict-MySQL test verifies index availability/query compatibility and owner projection updates; migration test verifies original values survive upgrade/downgrade.
- Local read-only audit completed; additive migration applied. No automated tests ran against working gym records.

Backend test command:
```powershell
Set-Location 'C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend'
& '.\.venv\Scripts\python.exe' 'scripts\run_isolated_tests.py' --mysql-bin 'C:\Program Files\MySQL\MySQL Server 26.7\bin\mysqld.exe' tests/test_gym_geo_discovery.py tests/test_gym_geo_mysql.py tests/test_gym_geo_migration.py tests/test_owner_gym_review.py tests/test_admin_gym_submission.py tests/test_platform_memberships.py -q
```

Still manual: real Google sandbox route rendering/quota/referrer checks; Android/iOS app handoff; visual approval with real Google tiles; owner pin accuracy for all active gyms. These are release blockers, not claimed passing tests.

## File inventory

Created:
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\GOOGLE_MAPS_INTEGRATION.md`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\.env.example`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\maps\geo.ts`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\maps\googleMaps.ts`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\maps\location.ts`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\maps\useLocation.ts`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\maps\maps.css`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\maps\MapCanvas.tsx`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\maps\DiscoveryMap.tsx`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\maps\GymDirections.tsx`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\maps\CoordinatePicker.tsx`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\scripts\maps.test.mjs`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\scripts\maps-browser.mjs`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\services\gym_geo.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\services\gym_discovery.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\scripts\audit_gym_coordinates.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\alembic\versions\a13b4df67935_gym_geo_index.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\tests\test_gym_geo_discovery.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\tests\test_gym_geo_mysql.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\tests\test_gym_geo_migration.py`

Modified:
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\pages\discovery\DiscoveryPage.tsx`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\pages\discovery\GymPage.tsx`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\pages\discovery\LocationPage.tsx`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\components\navigation\CustomerShell.tsx`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\screens\NearbyGyms\LocationStore.ts`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\screens\NearbyGyms\types.ts`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\services\gymService.ts`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\src\owner\Gyms.tsx`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\models\gym.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\schemas\gym.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\services\gym_service.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\routers\gyms_public.py`
- `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\backend\app\routers\meta.py`

Build/test outputs: `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\maps-unit-results.txt`, `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\maps-build-results.txt`, and ignored frontend dist assets. Git CLI was unavailable on PATH; no commit was made.