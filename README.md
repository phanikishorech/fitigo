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

### 4) Run migrations

```powershell
cd backend
alembic upgrade head
```

### 5) Start API

```powershell
cd backend
uvicorn app.main:app --reload --port 8000
```

Open:
- Swagger: http://localhost:8000/docs
- Health: http://localhost:8000/api/v1/health

## Frontend (customer UI)

Frontend has been intentionally removed for now. We'll rebuild the customer/user UI screen-by-screen.

## One-command start/stop (Windows PowerShell)

From the repo root (backend only):

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start-dev.ps1
```

To stop:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\stop-dev.ps1
```

## Running tests (backend)

```powershell
cd backend
pytest
```

## Dev seed data

After you have configured `DATABASE_URL` and run migrations, you can seed development users:

```powershell
cd backend
& .\.venv\Scripts\python.exe -m app.scripts.seed_dev
```

Default dev password: `password1234`

Dev users created:

- admin@example.com (ADMIN)
- owner@example.com (GYM_OWNER)
- customer@example.com (CUSTOMER)

## Notes

- This MVP is local-first: MySQL + local uploads directory.
- Cloud storage, Redis, real payment gateways, and Docker are intentionally not required for Phase 1.
