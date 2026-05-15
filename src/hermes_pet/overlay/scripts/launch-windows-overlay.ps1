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
$appRoot = Join-Path $cacheRoot "app-$Port"
$sourceMainJs = Join-Path $RepoPath "src\main.windows.js"
$mainJs = Join-Path $appRoot "src\main.windows.js"

if (-not (Test-Path $sourceMainJs)) {
  throw "Windows overlay entrypoint not found: $sourceMainJs"
}

function Get-HermesOverlayProcesses {
  $targetMains = @(
    [System.IO.Path]::GetFullPath($mainJs),
    [System.IO.Path]::GetFullPath($sourceMainJs)
  )
  $cacheAppPrefix = [System.IO.Path]::GetFullPath((Join-Path $cacheRoot "app-"))
  $cacheRootFull = [System.IO.Path]::GetFullPath($cacheRoot)
  Get-CimInstance Win32_Process |
    Where-Object {
      $cmdLine = $_.CommandLine
      if ($_.Name -ine "electron.exe" -or -not $cmdLine) {
        $false
      } else {
        $matched = $false
        foreach ($targetMain in $targetMains) {
          if ($cmdLine.IndexOf($targetMain, [System.StringComparison]::OrdinalIgnoreCase) -ge 0) {
            $matched = $true
          }
        }
        if ($cmdLine.IndexOf($cacheRootFull, [System.StringComparison]::OrdinalIgnoreCase) -ge 0) {
          $matched = $true
        }
        if (
          $cmdLine.IndexOf($cacheAppPrefix, [System.StringComparison]::OrdinalIgnoreCase) -ge 0 -and
          $cmdLine.IndexOf("src\main.windows.js", [System.StringComparison]::OrdinalIgnoreCase) -ge 0
        ) {
          $matched = $true
        }
        $matched
      }
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

function Wait-HermesOverlayExit {
  param([int]$TimeoutSeconds = 6)

  $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
  do {
    $remaining = @(Get-HermesOverlayProcesses)
    if ($remaining.Count -eq 0) {
      return $true
    }
    Start-Sleep -Milliseconds 250
  } while ((Get-Date) -lt $deadline)

  return (@(Get-HermesOverlayProcesses).Count -eq 0)
}

function Stop-HermesOverlayProcesses {
  param([Parameter(Mandatory = $true)] [object[]]$Roots)

  $current = @($Roots)
  if ($current.Count -eq 0) {
    return $true
  }

  for ($attempt = 1; $attempt -le 3; $attempt++) {
    Stop-HermesOverlayTree -Roots $current
    if (Wait-HermesOverlayExit -TimeoutSeconds 6) {
      return $true
    }
    $current = @(Get-HermesOverlayProcesses)
    if ($current.Count -eq 0) {
      return $true
    }
    Write-Warning "Hermes overlay process(es) still exiting after stop attempt $attempt`: $($current.ProcessId -join ', ')"
  }

  return $false
}

function Sync-HermesOverlayApp {
  if (Test-Path $appRoot) {
    $removed = $false
    for ($attempt = 1; $attempt -le 10; $attempt++) {
      try {
        Remove-Item -Recurse -Force $appRoot -ErrorAction Stop
        $removed = $true
        break
      } catch {
        if ($attempt -eq 10) {
          throw
        }
        Start-Sleep -Milliseconds 500
      }
    }
    if (-not $removed -and (Test-Path $appRoot)) {
      throw "Could not refresh cached overlay app: $appRoot"
    }
  }
  New-Item -ItemType Directory -Path $appRoot | Out-Null

  foreach ($name in @("package.json", "src", "assets", "scripts")) {
    $source = Join-Path $RepoPath $name
    if (Test-Path $source) {
      Copy-Item -Path $source -Destination $appRoot -Recurse -Force
    }
  }

  if (-not (Test-Path $mainJs)) {
    throw "Cached Windows overlay entrypoint was not created: $mainJs"
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
  $stopped = Stop-HermesOverlayProcesses -Roots $existing
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
  $stopped = Stop-HermesOverlayProcesses -Roots $existing
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

Sync-HermesOverlayApp

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
  "HERMES_PET_ELECTRON_USER_DATA",
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
  -WorkingDirectory $appRoot `
  -PassThru

Write-Output "Hermes Windows pet overlay started (pid $($proc.Id))"
Write-Output "Electron cache: $cacheRoot"
Write-Output "Bridge URL: $env:HERMES_PET_WS_URL"
