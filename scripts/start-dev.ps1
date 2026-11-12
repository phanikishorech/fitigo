<#
.SYNOPSIS
  Start the local FitiGo backend on loopback port 8000.
.DESCRIPTION
  Never stops existing processes. Refuses startup if the selected port is busy.
  The frontend is started separately; both Vite proxies target port 8000.
#>
[CmdletBinding()]
param(
  [ValidateRange(1024, 65535)][int]$Port = 8000,
  [switch]$CheckOnly
)

$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$backendDir = Join-Path $repoRoot 'backend'
$python = Join-Path $backendDir '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) {
  throw "Backend virtual-environment Python not found: $python"
}

# Probe by binding instead of killing an arbitrary listener. A startup race is
# still safe: uvicorn fails its own bind without taking over another process.
$probe = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, $Port)
try {
  $probe.Server.ExclusiveAddressUse = $true
  $probe.Start()
} catch {
  throw "Port $Port is occupied or unavailable. No process was stopped. Verify ownership before stopping any application."
} finally {
  $probe.Stop()
}

if ($CheckOnly) {
  Write-Host "FitiGo backend configuration valid; port $Port is available. No process started."
  return
}
if ($Port -ne 8000) {
  Write-Warning 'A nondefault port requires updating BOTH Vite proxies before using the frontend.'
}

# Per-run private local logs, not source-controlled artifacts. No .env values
# or credentials are echoed. The child inherits the usual application config.
$logDir = Join-Path $env:LOCALAPPDATA ('FitiGo\runtime\backend-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '-' + [guid]::NewGuid().ToString('N').Substring(0, 8))
New-Item -ItemType Directory -Path $logDir -Force | Out-Null
$sid = [System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value
& icacls.exe $logDir /inheritance:r /grant:r "*$($sid):(OI)(CI)F" '*S-1-5-18:(OI)(CI)F' | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Could not secure the runtime log directory; backend not started.' }
$backend = Start-Process -FilePath $python -WorkingDirectory $backendDir -ArgumentList @(
  '-m', 'uvicorn', 'app.main:app', '--reload', '--host', '127.0.0.1', '--port', "$Port"
) -RedirectStandardOutput (Join-Path $logDir 'stdout.log') -RedirectStandardError (Join-Path $logDir 'stderr.log') -PassThru

@{ pid = $backend.Id; port = $Port; backend_directory = $backendDir } |
  ConvertTo-Json | Set-Content -LiteralPath (Join-Path $logDir 'process.json')
Write-Host "Started FitiGo launcher PID $($backend.Id); backend port $Port."
Write-Host "Logs: $logDir"
Write-Host 'Verify /api/v1/health and /api/v1/health/db; launching does not guarantee readiness.'
