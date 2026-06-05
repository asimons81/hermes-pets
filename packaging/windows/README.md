# Native Windows Installer

This folder contains the unsigned beta desktop installer scaffold for Hermes
Pets on Windows 10/11.

Build from native Windows PowerShell:

```powershell
packaging\windows\build-installer.ps1
```

The script builds PyInstaller copies of `hermes-pet.exe` and
`hermes-pet-bridge.exe`, stages the Electron overlay, then runs
`electron-builder` to create an NSIS installer under `dist\windows-installer`.
The installer is intentionally unsigned for the beta milestone and writes a
`.sha256` checksum beside the installer.
