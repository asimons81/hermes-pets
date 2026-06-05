# Native Windows Installer

Native Windows support is an unsigned beta installer path for Windows 10/11. It
does not require WSL, a system Python install, or npm after installation.

## Build

Run from native Windows PowerShell:

```powershell
packaging\windows\build-installer.ps1
```

The build script:

- creates PyInstaller `hermes-pet.exe` and `hermes-pet-bridge.exe` binaries;
- stages the Electron overlay and launcher scripts;
- runs `electron-builder` to produce an NSIS installer in
  `dist\windows-installer`;
- writes a `.sha256` checksum beside the unsigned installer.

## Installed Layout

The installer creates a Start Menu shortcut for `Hermes Pets.exe`. The bundled
CLI is available at:

```text
<install-dir>\bin\hermes-pet.exe
```

The CLI keeps honoring `HERMES_PET_HOME`. Without that override, Windows expands
the existing `~\.hermes_pet` state location for pet state, preferences, jobs,
and custom pets. Overlay app data and position files stay under
`%LOCALAPPDATA%\HermesAgent\pet-overlay-electron`.

## Verification

Before describing a native Windows installer artifact as release-ready, run:

```powershell
scripts\verify-native-windows-overlay.ps1 -InstalledRoot "<install-dir>"
```

Then complete the manual live checklist on a real Windows desktop:

- install the unsigned beta and acknowledge SmartScreen if it appears;
- open Hermes Pets from the Start Menu and confirm the overlay is visible;
- run `<install-dir>\bin\hermes-pet.exe doctor --strict`;
- run `<install-dir>\bin\hermes-pet.exe overlay-status`;
- run `<install-dir>\bin\hermes-pet.exe launch --replace`;
- run `<install-dir>\bin\hermes-pet.exe emit bubble "test"`;
- run `<install-dir>\bin\hermes-pet.exe close`;
- run `<install-dir>\bin\hermes-pet.exe close --bridge`;
- reinstall over the existing install and confirm pet state survives;
- uninstall and confirm installed app files are removed.

Unsigned beta releases must publish the generated SHA-256 checksum with the
installer artifact. Auto-update and Authenticode signing are intentionally out
of scope for this milestone.
