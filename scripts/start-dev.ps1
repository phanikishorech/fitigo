<#
.SYNOPSIS
  Start FitiGo backend + frontend for local development.

.DESCRIPTION
  - Kills any process currently listening on port 8000 (backend)
  - Starts backend (uvicorn --reload)

  This script opens the backend in a separate PowerShell window.

.USAGE
  From repo root:
    powershell -ExecutionPolicy Bypass -File .\scripts\start-dev.ps1
#>

$ErrorActionPreference = 'Stop'

function Stop-ProcessOnPort {
  param(
    [Parameter(Mandatory = $true)][int]$Port,
    [Parameter(Mandatory = $false)][string]$Label = $null
  )

  $lbl = if ($Label) { $Label } else { "port $Port" }
  try {
    $conns = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    if (-not $conns) {
      Write-Host "No listener found on $lbl"
      return
    }

    $procIds = $conns | Select-Object -ExpandProperty OwningProcess -Unique
    foreach ($procId in $procIds) {
      if (-not $procId) { continue }
      $p = Get-Process -Id $procId -ErrorAction SilentlyContinue
      if ($p) {
        Write-Host "Stopping PID $procId ($($p.ProcessName)) on $lbl"
        Stop-Process -Id $procId -Force
      }
    }
  } catch {
    Write-Warning "Failed to stop process on $lbl. Try running PowerShell as Administrator. Error: $($_.Exception.Message)"
  }
}

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot '..')

$backendDir = Join-Path $repoRoot 'backend'

$python = Join-Path $backendDir '.venv\Scripts\python.exe'
if (-not (Test-Path $python)) {
  throw "Backend venv python not found at: $python. Did you create the venv in backend/.venv?"
}

Write-Host "Repo root: $repoRoot"

Stop-ProcessOnPort -Port 8000 -Label 'backend (8000)'

Write-Host "Starting backend (uvicorn --reload)..."
$backendCmd = "cd `"$backendDir`"; & `"$python`" -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000"
Start-Process powershell.exe -ArgumentList @('-NoExit', '-Command', $backendCmd) | Out-Null

Write-Host "Done. Backend: http://localhost:8000/docs"
