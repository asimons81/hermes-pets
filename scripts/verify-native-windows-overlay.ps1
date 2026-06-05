param(
  [string]$InstalledRoot,
  [switch]$SkipProcessChecks
)

$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) "..")).Path
$packagingRoot = Join-Path $repoRoot "packaging\windows"
$launcher = Join-Path $repoRoot "overlay\scripts\launch-windows-overlay.ps1"
$packagedLauncher = Join-Path $repoRoot "src\hermes_pet\overlay\scripts\launch-windows-overlay.ps1"

function Assert-File {
  param([Parameter(Mandatory = $true)] [string]$Path)
  if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
    throw "Missing required file: $Path"
  }
}

function Assert-Directory {
  param([Parameter(Mandatory = $true)] [string]$Path)
  if (-not (Test-Path -LiteralPath $Path -PathType Container)) {
    throw "Missing required directory: $Path"
  }
}

function Test-PowerShellSyntax {
  param([Parameter(Mandatory = $true)] [string]$Path)

  $source = Get-Content -LiteralPath $Path -Raw
  $tokens = $null
  $errors = $null
  [System.Management.Automation.Language.Parser]::ParseInput(
    $source,
    [ref]$tokens,
    [ref]$errors
  ) | Out-Null
  if ($errors.Count -gt 0) {
    throw ($errors | Out-String)
  }
}

Assert-File (Join-Path $packagingRoot "package.json")
Assert-File (Join-Path $packagingRoot "main.js")
Assert-File (Join-Path $packagingRoot "build-installer.ps1")
Assert-File $launcher
Assert-File $packagedLauncher
Test-PowerShellSyntax $launcher
Test-PowerShellSyntax $packagedLauncher

if ($InstalledRoot) {
  $root = (Resolve-Path $InstalledRoot).Path
  Assert-File (Join-Path $root "Hermes Pets.exe")
  Assert-File (Join-Path $root "bin\hermes-pet.exe")
  Assert-File (Join-Path $root "bin\hermes-pet-bridge.exe")
  Assert-Directory (Join-Path $root "resources\overlay")
  Assert-File (Join-Path $root "resources\overlay\src\main.windows.js")
  Assert-File (Join-Path $root "resources\overlay\scripts\launch-windows-overlay.ps1")

  if (-not $SkipProcessChecks) {
    $env:HERMES_PET_WINDOWS_APP_EXE = Join-Path $root "Hermes Pets.exe"
    & (Join-Path $root "bin\hermes-pet.exe") doctor --strict
    & (Join-Path $root "bin\hermes-pet.exe") overlay-status
    & (Join-Path $root "bin\hermes-pet.exe") close --bridge
  }
}

Write-Output "native Windows overlay verifier ok"
