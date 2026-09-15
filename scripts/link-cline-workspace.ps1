param(
  [string]$RepoPath = (Resolve-Path (Join-Path $PSScriptRoot "..") ).Path,
  [string]$ClineWorkspace = (Join-Path $env:USERPROFILE ".cline\data\workspaces\chat\fitigo")
)

$ErrorActionPreference = "Stop"

Write-Host "RepoPath:        $RepoPath"
Write-Host "ClineWorkspace:  $ClineWorkspace"

if (!(Test-Path -LiteralPath $RepoPath)) {
  throw "Repo path not found: $RepoPath"
}

if (Test-Path -LiteralPath $ClineWorkspace) {
  $item = Get-Item -LiteralPath $ClineWorkspace -Force
  if ($item.LinkType) {
    # Already a junction/symlink
    if ($item.Target -contains $RepoPath) {
      Write-Host "Cline workspace is already linked to this repo. ($($item.LinkType) -> $RepoPath)"
      exit 0
    }

    Write-Warning "Cline workspace is linked elsewhere ($($item.LinkType) -> $($item.Target))."
    Write-Warning "Remove it manually if you want to repoint. Path: $ClineWorkspace"
    exit 1
  }

  # Real directory exists (not a link). Back it up.
  $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
  $backup = "${ClineWorkspace}_backup_${stamp}"
  Write-Host "Backing up existing directory: $ClineWorkspace -> $backup"
  Rename-Item -LiteralPath $ClineWorkspace -NewName (Split-Path $backup -Leaf)
}

Write-Host "Creating junction: $ClineWorkspace -> $RepoPath"
New-Item -ItemType Junction -Path $ClineWorkspace -Target $RepoPath | Out-Null

$linked = Get-Item -LiteralPath $ClineWorkspace -Force
Write-Host "Done. LinkType=$($linked.LinkType) Target=$($linked.Target)"
