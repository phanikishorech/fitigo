<#
.SYNOPSIS
  Stop FitiGo backend + frontend dev servers.

.USAGE
  powershell -ExecutionPolicy Bypass -File .\scripts\stop-dev.ps1
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

Stop-ProcessOnPort -Port 8000 -Label 'backend (8000)'

Write-Host "Stopped backend (if it was running)."
