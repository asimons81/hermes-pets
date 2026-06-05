param(
  [string]$Configuration = "Release",
  [switch]$SkipNpmInstall
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = (Resolve-Path (Join-Path $scriptDir "..\..")).Path
$stagingRoot = Join-Path $scriptDir "staging"
$stagingBin = Join-Path $stagingRoot "bin"
$stagingOverlay = Join-Path $stagingRoot "overlay"
$installerOut = Join-Path $repoRoot "dist\windows-installer"
$windowsBuildVenv = Join-Path $env:TEMP "hermes-pets-windows-build-venv"
$windowsBuildRoot = Join-Path $env:TEMP "hermes-pets-windows-build"
$sourceMirror = Join-Path $windowsBuildRoot "repo"
$electronBuildRoot = Join-Path $windowsBuildRoot "electron"
$localInstallerOut = Join-Path $windowsBuildRoot "installer"
$pyInstallerOut = Join-Path $windowsBuildRoot "dist"

Remove-Item -Recurse -Force $stagingRoot, $windowsBuildRoot -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path $stagingBin, $stagingOverlay, $installerOut | Out-Null

$env:UV_PROJECT_ENVIRONMENT = $windowsBuildVenv

New-Item -ItemType Directory -Force -Path $sourceMirror | Out-Null
foreach ($item in @("src", "overlay")) {
  Copy-Item -Recurse -Force (Join-Path $repoRoot $item) (Join-Path $sourceMirror $item)
}
foreach ($item in @("pyproject.toml", "uv.lock", "README.md")) {
  Copy-Item -Force (Join-Path $repoRoot $item) (Join-Path $sourceMirror $item)
}

Push-Location $sourceMirror
try {
  uv run --with pyinstaller pyinstaller `
    --noconfirm `
    --clean `
    --onefile `
    --paths src `
    --collect-data hermes_pet `
    --distpath $pyInstallerOut `
    --workpath (Join-Path $windowsBuildRoot "work\hermes-pet") `
    --specpath (Join-Path $windowsBuildRoot "spec") `
    --name hermes-pet `
    src\hermes_pet\cli.py
  if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller failed for hermes-pet.exe with exit code $LASTEXITCODE"
  }

  uv run --with pyinstaller pyinstaller `
    --noconfirm `
    --clean `
    --onefile `
    --paths src `
    --collect-data hermes_pet `
    --distpath $pyInstallerOut `
    --workpath (Join-Path $windowsBuildRoot "work\hermes-pet-bridge") `
    --specpath (Join-Path $windowsBuildRoot "spec") `
    --name hermes-pet-bridge `
    src\hermes_pet\bridge.py
  if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller failed for hermes-pet-bridge.exe with exit code $LASTEXITCODE"
  }
} finally {
  Pop-Location
}

Copy-Item -Force (Join-Path $pyInstallerOut "hermes-pet.exe") $stagingBin
Copy-Item -Force (Join-Path $pyInstallerOut "hermes-pet-bridge.exe") $stagingBin
Copy-Item -Recurse -Force (Join-Path $sourceMirror "overlay\*") $stagingOverlay

New-Item -ItemType Directory -Force -Path $electronBuildRoot | Out-Null
Copy-Item -Force (Join-Path $scriptDir "main.js") $electronBuildRoot
Copy-Item -Force (Join-Path $scriptDir "package.json") $electronBuildRoot
if (Test-Path (Join-Path $scriptDir "package-lock.json")) {
  Copy-Item -Force (Join-Path $scriptDir "package-lock.json") $electronBuildRoot
}
Copy-Item -Recurse -Force $stagingRoot (Join-Path $electronBuildRoot "staging")

Push-Location $electronBuildRoot
try {
  if (-not $SkipNpmInstall) {
    npm install
    if ($LASTEXITCODE -ne 0) {
      throw "npm install failed with exit code $LASTEXITCODE"
    }
  }
  npm run dist -- --config.directories.output="$localInstallerOut"
  if ($LASTEXITCODE -ne 0) {
    throw "electron-builder failed with exit code $LASTEXITCODE"
  }
} finally {
  Pop-Location
}

Copy-Item -Force (Join-Path $localInstallerOut "Hermes-Pets-Setup-*.exe") $installerOut

$installer = Get-ChildItem -Path $installerOut -Filter "Hermes-Pets-Setup-*.exe" |
  Sort-Object LastWriteTime -Descending |
  Select-Object -First 1
if (-not $installer) {
  throw "No Hermes Pets installer was produced in $installerOut"
}

$hash = Get-FileHash -Algorithm SHA256 -LiteralPath $installer.FullName
$checksumPath = "$($installer.FullName).sha256"
"$($hash.Hash)  $($installer.Name)" | Set-Content -Path $checksumPath -Encoding ASCII

Remove-Item -Recurse -Force $stagingRoot -ErrorAction SilentlyContinue

Write-Output "Installer: $($installer.FullName)"
Write-Output "Checksum: $checksumPath"
