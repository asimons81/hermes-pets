param(
  [Parameter(Mandatory = $true)]
  [string]$RepoPath,

  [int]$Port = 17473,

  [string]$PositionFile,

  [switch]$Replace,

  [switch]$Status,

  [switch]$Stop
)

$ErrorActionPreference = "Stop"

$cacheRoot = Join-Path $env:LOCALAPPDATA "HermesAgent\pet-overlay-electron"
$packageJson = Join-Path $cacheRoot "package.json"
$electronCmd = Join-Path $cacheRoot "node_modules\.bin\electron.cmd"
$mainJs = Join-Path $RepoPath "src\main.windows.js"

if (-not (Test-Path $mainJs)) {
  throw "Windows overlay entrypoint not found: $mainJs"
}

function Get-HermesOverlayProcesses {
  $targetMain = [System.IO.Path]::GetFullPath($mainJs)
  Get-CimInstance Win32_Process |
    Where-Object {
      $_.Name -ieq "electron.exe" -and
      $_.CommandLine -and
      $_.CommandLine.IndexOf($targetMain, [System.StringComparison]::OrdinalIgnoreCase) -ge 0
    } |
    Sort-Object ProcessId
}

function Stop-HermesOverlayTree {
  param([Parameter(Mandatory = $true)] [object[]]$Roots)

  $allProcesses = @(Get-CimInstance Win32_Process)
  $pending = New-Object System.Collections.Generic.Queue[int]
  $ids = New-Object System.Collections.Generic.HashSet[int]
  foreach ($root in $Roots) {
    [void]$pending.Enqueue([int]$root.ProcessId)
  }

  while ($pending.Count -gt 0) {
    $id = $pending.Dequeue()
    if (-not $ids.Add($id)) {
      continue
    }
    foreach ($child in $allProcesses | Where-Object { $_.ParentProcessId -eq $id }) {
      [void]$pending.Enqueue([int]$child.ProcessId)
    }
  }

  $orderedIds = @($ids) | Sort-Object -Descending
  foreach ($id in $orderedIds) {
    try {
      Stop-Process -Id $id -Force -ErrorAction Stop
    } catch {
      Write-Warning "Could not stop Hermes overlay process $id`: $($_.Exception.Message)"
    }
  }
}

$existing = @(Get-HermesOverlayProcesses)

if ($Status) {
  if ($existing.Count -eq 0) {
    Write-Output "Overlay processes: none"
  } else {
    Write-Output "Overlay processes: $($existing.Count)"
    foreach ($proc in $existing) {
      Write-Output "  pid $($proc.ProcessId): $($proc.CommandLine)"
    }
  }
  Write-Output "Electron cache: $cacheRoot"
  exit 0
}

if ($Stop) {
  if ($existing.Count -eq 0) {
    Write-Output "Overlay processes: none"
    Write-Output "Electron cache: $cacheRoot"
    exit 0
  }

  Write-Output "Stopping Hermes Windows pet overlay process tree(s): $($existing.ProcessId -join ', ')"
  Stop-HermesOverlayTree -Roots $existing
  Start-Sleep -Milliseconds 500
  $existing = @(Get-HermesOverlayProcesses)
  if ($existing.Count -gt 0) {
    throw "Could not stop existing Hermes overlay process(es): $($existing.ProcessId -join ', ')"
  }
  Write-Output "Overlay processes: none"
  Write-Output "Electron cache: $cacheRoot"
  exit 0
}

if ($existing.Count -gt 0 -and $Replace) {
  Write-Output "Stopping existing Hermes Windows pet overlay process tree(s): $($existing.ProcessId -join ', ')"
  Stop-HermesOverlayTree -Roots $existing
  Start-Sleep -Milliseconds 500
  $existing = @(Get-HermesOverlayProcesses)
  if ($existing.Count -gt 0) {
    throw "Could not stop existing Hermes overlay process(es): $($existing.ProcessId -join ', ')"
  }
}

if ($existing.Count -gt 0) {
  Write-Output "Hermes Windows pet overlay already running (pid $($existing.ProcessId -join ', ')); reusing existing instance."
  Write-Output "Use 'hermes-pet launch --replace' to restart the overlay."
  Write-Output "Electron cache: $cacheRoot"
  Write-Output "Bridge URL: ws://127.0.0.1:$Port"
  exit 0
}

if (-not (Test-Path $cacheRoot)) {
  New-Item -ItemType Directory -Path $cacheRoot | Out-Null
}

if (-not (Test-Path $packageJson)) {
  @'
{
  "name": "hermes-pet-overlay-windows-cache",
  "private": true,
  "version": "0.0.0",
  "dependencies": {
    "electron": "33.0.0",
    "ws": "8.18.0"
  }
}
'@ | Set-Content -Path $packageJson -Encoding UTF8
}

if (-not (Test-Path $electronCmd)) {
  $npm = (Get-Command npm.cmd -ErrorAction Stop).Source
  & $npm install --prefix $cacheRoot --no-audit --no-fund
  if ($LASTEXITCODE -ne 0) {
    throw "npm install failed with exit code $LASTEXITCODE"
  }
}

$env:HERMES_PET_PORT = [string]$Port
$env:HERMES_PET_WS_URL = "ws://127.0.0.1:$Port"
$env:HERMES_PET_WINDOWS_NODE_MODULES = (Join-Path $cacheRoot "node_modules")
if ($PositionFile) {
  $env:HERMES_PET_POSITION_FILE = $PositionFile
}

# Forward known overlay env vars from the parent (WSL) process so the
# Electron renderer can also read them as a bootstrap hint.
$forwardVars = @(
  "HERMES_PET_SPECIES",
  "HERMES_PET_DEBUG_ANIMATION",
  "HERMES_PET_DEBUG_DRAG",
  "HERMES_PET_DEBUG_EVENTS",
  "HERMES_PET_OVERLAY_VERIFY_FILE",
  "HERMES_PET_ALWAYS_ON_TOP_LEVEL",
  "HERMES_PET_FOCUSABLE",
  "HERMES_PET_SHOW_UPLOAD"
)
foreach ($name in $forwardVars) {
  $val = [System.Environment]::GetEnvironmentVariable($name, "Process")
  if ($val) {
    Set-Item "env:$name" -Value $val
  }
}

$argsList = @("`"$mainJs`"")
$proc = Start-Process -FilePath $electronCmd `
  -ArgumentList $argsList `
  -WorkingDirectory $RepoPath `
  -WindowStyle Hidden `
  -PassThru

Write-Output "Hermes Windows pet overlay started (pid $($proc.Id))"
Write-Output "Electron cache: $cacheRoot"
Write-Output "Bridge URL: $env:HERMES_PET_WS_URL"
