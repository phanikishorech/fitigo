param(
  [int]$BackendPort = 8000,
  [int]$FrontendPort = 5173
)

$ErrorActionPreference = "Stop"

$repo = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$backend = Join-Path $repo "backend"
$frontend = Join-Path $repo "frontend"

if (!(Test-Path -LiteralPath $backend)) { throw "Backend folder not found: $backend" }
if (!(Test-Path -LiteralPath $frontend)) { throw "Frontend folder not found: $frontend" }

Write-Host "Starting backend (uvicorn) on port $BackendPort..."
Start-Process powershell -WorkingDirectory $backend -ArgumentList @(
  "-NoExit",
  "-Command",
  ".\\.venv\\Scripts\\python.exe -m uvicorn app.main:app --reload --port $BackendPort"
)

Write-Host "Starting frontend (Vite) on port $FrontendPort..."
Start-Process powershell -WorkingDirectory $frontend -ArgumentList @(
  "-NoExit",
  "-Command",
  "npm run dev -- --port $FrontendPort --strictPort"
)

Write-Host ""
Write-Host "Frontend: http://localhost:$FrontendPort"
Write-Host "Backend:  http://localhost:$BackendPort/docs"
