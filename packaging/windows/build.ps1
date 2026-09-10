<#
.SYNOPSIS
  Build the Windows installer for Copilot Usage Tracker.

.DESCRIPTION
  Creates an isolated venv, installs the app, bundles it with PyInstaller,
  and compiles packaging/windows/installer.iss with Inno Setup 6 into
  dist/CopilotUsageTracker-Setup-<version>.exe.

  Requires: Python 3.11+, Inno Setup 6 (winget install --id JRSoftware.InnoSetup).

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File packaging/windows/build.ps1
#>
$ErrorActionPreference = "Stop"

$Root = Resolve-Path (Join-Path $PSScriptRoot ".." "..")
$PkgDir = $PSScriptRoot
Set-Location $Root

# Version: release tag (refs/tags/vX.Y.Z) wins, else pyproject.toml.
if ($env:GITHUB_REF -match 'refs/tags/v(.+)$') {
    $Version = $Matches[1]
} else {
    $Version = (python -c "import tomllib; print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])").Trim()
}
Write-Host "Building Copilot Usage Tracker $Version for Windows"

# 1. Isolated build venv
python -m venv .venv-pkg
& .\.venv-pkg\Scripts\python -m pip install -q --upgrade pip
& .\.venv-pkg\Scripts\pip install -q -e ".[desktop,dashboard]" pyinstaller

# 2. PyInstaller bundle (onedir, windowed -- no console window)
& .\.venv-pkg\Scripts\pyinstaller tray\pyinstaller.spec `
    --distpath "$PkgDir\dist" --workpath "$PkgDir\build" --noconfirm
if (-not (Test-Path "$PkgDir\dist\copilot-usage-tray\copilot-usage-tray.exe")) {
    throw "PyInstaller output missing: $PkgDir\dist\copilot-usage-tray\copilot-usage-tray.exe"
}

# 3. Compile the installer with Inno Setup
$Iscc = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe"
if (-not (Test-Path $Iscc)) { $Iscc = "$env:ProgramFiles\Inno Setup 6\ISCC.exe" }
if (-not (Test-Path $Iscc)) {
    throw "Inno Setup 6 not found. Install it: winget install --id JRSoftware.InnoSetup"
}
& $Iscc /DAppVersion=$Version "$PkgDir\installer.iss"

$Setup = Get-ChildItem "$PkgDir\dist\CopilotUsageTracker-Setup-*.exe" | Sort-Object LastWriteTime -Descending | Select-Object -First 1

# 4. Optional code signing: removes the SmartScreen "Unknown publisher"
# prompt. Set CODESIGN_THUMBPRINT to the thumbprint of a code-signing
# certificate in the CurrentUser\My or LocalMachine\My store. Skipped
# silently when unset (CI builds stay reproducible without secrets).
if ($env:CODESIGN_THUMBPRINT) {
    $signtool = Get-ChildItem "${env:ProgramFiles(x86)}\Windows Kits\10\bin" -Recurse -Filter signtool.exe -ErrorAction SilentlyContinue |
        Sort-Object FullName -Descending | Select-Object -First 1
    if ($signtool) {
        Write-Host "Signing $($Setup.Name) with certificate $($env:CODESIGN_THUMBPRINT)"
        & $signtool.FullName sign /sha1 $env:CODESIGN_THUMBPRINT /fd SHA256 `
            /tr http://timestamp.digicert.com /td SHA256 $Setup.FullName
    } else {
        Write-Warning "CODESIGN_THUMBPRINT set but signtool.exe not found; skipping signing."
    }
}

Write-Host ""
Write-Host "Installer ready: $($Setup.FullName)"
