# FitiGo (Local-first MVP)

Multi-gym booking and fitness access platform (local development MVP).

## Prerequisites

- Windows 10/11
- Python **3.12+**
- Node.js **18+** (you have Node installed)
- MySQL **8** running locally

## Project structure

```
Fitigo/
  backend/
  .env.example
  README.md
```

## Backend setup (FastAPI)

### 1) Create virtual environment

From the project root:

```powershell
cd "C:\Users\ckishor\PROJECT CODE\GIT Code\poc\Fitigo"
python -m venv backend\.venv
backend\.venv\Scripts\Activate.ps1
```

### 2) Install dependencies

```powershell
pip install -r backend\requirements.txt
```

### 3) Configure environment

Copy `.env.example` to `.env` in the project root and update `DATABASE_URL`.
Configure a private, cryptographically random `JWT_SECRET` before starting the API.
There is no default key, including in development. All API workers must use the
same key and `JWT_ALGORITHM`. See the Phase 1 security handoff at
`C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend/SECURITY_PHASE1.md`.

### 4) Run migrations

```powershell
cd backend
alembic upgrade head
```

### 5) Start API

```powershell
cd backend
uvicorn app.main:app --reload --host 127.0.0.1 --port 8001
```

Open:
- Swagger: http://127.0.0.1:8001/docs
- Health: http://127.0.0.1:8001/api/v1/health

## Frontend (customer UI)

The customer frontend is implemented with React, TypeScript, and Vite. Run `npm run dev` from `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend` after starting the backend. Existing owner/admin pages remain available.

See `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\README.md` for development/deployment instructions and `C:\Users\ckishor\.cline\data\workspaces\chat\fitigo\frontend\IMPLEMENTATION.md` for the verified API mapping, test results, remaining gaps, and production release blockers. Wallet recharge and membership purchase currently use backend MVP payment behavior, not a real gateway.

## One-command start/stop (Windows PowerShell)

From the repo root (backend only):

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start-dev.ps1
```

The startup script starts only the backend on port 8001 and refuses occupied
ports; it never kills another application. Use `-CheckOnly` for a non-starting
port/configuration check. Start the frontend separately. Both Vite proxies
(`/api` and `/uploads`) target `127.0.0.1:8001`.

To stop:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\stop-dev.ps1
```

## Running tests (backend)

Plain pytest now fails closed before application imports. Use the isolated runner;
it creates a new loopback-only MySQL process and data directory, generates test
credentials/run IDs and never reads the application's database URL or `.env`.
Do not manually set `FITIGO_TEST_RUN_ID` or point test variables at `dev_fitigo`.

Phase 6 operational audit/photo deletion requires migration `df081ac34602` and
`OPERATIONAL_WORKFLOWS_ENABLED=true` after an approved database/media backup and
storage review. The flag defaults to false; do not enable it on an unmigrated
working database. Add `--operational` to the isolated runner command to exercise
the enabled implementation safely. The operational handoff is at
`C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend/PHASE6_OPERATIONS.md`.

Notification inbox/preferences require `ef192bd45713` and
`NOTIFICATION_WORKFLOWS_ENABLED=true`. External email has a separate default-off
`NOTIFICATION_EMAIL_ENABLED` switch and an explicit worker; enabling inbox must
not silently start email. Add `--notifications` to the isolated test runner to
exercise this behavior without external delivery. `SUPPORT_EMAIL` is optional.
Local activation and verified database/media backup details are recorded in
`C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend/LOCAL_NONFINANCIAL_COMPLETION.md`.

Private in-app support requires migration `f02a3ce56824`, operational audit and
`SUPPORT_WORKFLOWS_ENABLED=true`. It is implemented but not enabled by default.
Add `--support` to the isolated runner to test the enabled workflow. The admin
readiness report is read-only and is not production certification. See
`C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend/SUPPORT_READINESS_PHASE.md`
for scope, tests and separate deployment requirements.

Support has subsequently been activated in the verified local environment at
revision `f02a3ce56824`; external email remains off. Backup/restore and read-only
verification details:
`C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend/LOCAL_SUPPORT_ACTIVATION.md`.
Other environments still require their own approved migration/activation.

```powershell
Set-Location 'C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend'
& './.venv/Scripts/python.exe' scripts/run_isolated_tests.py --mysql-bin 'C:/Program Files/MySQL/MySQL Server 26.7/bin/mysqld.exe' -q --tb=short --disable-warnings
```

Pass test paths after the MySQL executable option for targeted runs. The runner
stops only its own server; its unique private data/log directory is retained for
diagnostics. Review it before manual removal. No existing database is migrated.

## Dev seed data

After you have configured `DATABASE_URL` and run migrations, you can seed development users:

```powershell
cd backend
& .\.venv\Scripts\python.exe -m app.scripts.seed_dev
```

Seeding is disabled unless the parsed application environment is `development`,
the database host is local, `FITIGO_ALLOW_DEV_SEED=1` is explicitly set, and a
private `DEV_SEED_PASSWORD` of at least 12 characters is configured in the process
environment. There is no default seed password. Do not run the seeder against a
working or production database. Seed users must sign in normally; anonymous demo
identity substitution is not supported.

Dev users created:

- admin@example.com (ADMIN)
- owner@example.com (GYM_OWNER)
- customer@example.com (CUSTOMER)

## Notes

- This MVP is local-first: MySQL + local uploads directory.
- Cloud storage, Redis, real payment gateways, and Docker are intentionally not required for Phase 1.
