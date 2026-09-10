<#
.SYNOPSIS
  Genuine end-to-end smoke test of the Windows installer on a real machine.

  Clicks through the actual Inno Setup wizard (welcome -> license ->
  tasks -> ready -> installing -> finish), screenshotting each page,
  then verifies the installed files, launches the app, and screenshots
  the first-run setup window. Used by the Packaging workflow to produce
  real Windows screenshots for docs/screenshots/.

  Not for end users: end users just double-click the Setup exe.
#>
$ErrorActionPreference = "Continue"

$ShotDir = Join-Path (Get-Location) "screenshots"
New-Item -ItemType Directory -Force -Path $ShotDir | Out-Null
Add-Type -AssemblyName System.Drawing
Add-Type -AssemblyName System.Windows.Forms

function Save-Shot {
    param([string]$Name)
    try {
        $b = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
        $bmp = New-Object System.Drawing.Bitmap($b.Width, $b.Height)
        $g = [System.Drawing.Graphics]::FromImage($bmp)
        $g.CopyFromScreen($b.Location, [System.Drawing.Point]::Empty, $b.Size)
        $p = Join-Path $ShotDir $Name
        $bmp.Save($p, [System.Drawing.Imaging.ImageFormat]::Png)
        $g.Dispose(); $bmp.Dispose()
        Write-Host "screenshot: $p"
    } catch {
        Write-Host "screenshot failed: $_"
    }
}

$shell = New-Object -ComObject WScript.Shell
$setup = Get-ChildItem "CopilotUsageTracker-Setup-*.exe" | Sort-Object LastWriteTime -Descending | Select-Object -First 1
if (-not $setup) { throw "installer exe not found in $(Get-Location)" }

# Drop any Mark-of-the-Web so SmartScreen doesn't gate the genuine run.
Unblock-File -Path $setup.FullName -ErrorAction SilentlyContinue

Write-Host "starting $($setup.Name)"
$proc = Start-Process $setup.FullName -PassThru
Start-Sleep -Seconds 8
$shell.AppActivate($proc.Id) | Out-Null
Start-Sleep -Seconds 1
Save-Shot "installer-welcome.png"

$shell.SendKeys("%n")                    # Next -> license agreement
Start-Sleep -Seconds 3
Save-Shot "installer-license.png"
$shell.SendKeys("%a")                    # Alt+A: "I accept the agreement"
Start-Sleep -Seconds 1
$shell.SendKeys("%n")                    # Next -> select tasks
Start-Sleep -Seconds 3
Save-Shot "installer-options.png"

$shell.SendKeys("%n")                    # Next -> ready to install
Start-Sleep -Seconds 3
Save-Shot "installer-ready.png"

$shell.SendKeys("%i")                    # Alt+I: Install
Start-Sleep -Seconds 12
Save-Shot "installer-progress.png"

if (-not $proc.WaitForExit(240000)) { Write-Host "WARNING: installer still running after 4 min" }
Start-Sleep -Seconds 3
Save-Shot "installer-finish.png"
$shell.SendKeys(" ")                     # uncheck "Launch Copilot Usage Tracker"
Start-Sleep -Seconds 1
$shell.SendKeys("%f")                    # Finish
Start-Sleep -Seconds 3

# --- verify the installed files ---
$appExe = Join-Path $env:LOCALAPPDATA "Programs\CopilotUsageTracker\copilot-usage-tray.exe"
if (Test-Path $appExe) {
    Write-Host "installed OK: $appExe"
} else {
    Write-Host "INSTALLED EXE MISSING: $appExe"
    Save-Shot "install-missing.png"
    throw "installed exe not found"
}

# --- launch the app and screenshot the first-run setup window ---
$app = Start-Process $appExe -PassThru
Start-Sleep -Seconds 40
Save-Shot "app-first-run.png"
Start-Sleep -Seconds 15
Save-Shot "app-first-run-2.png"
Stop-Process -Id $app.Id -Force -ErrorAction SilentlyContinue
Get-Process -Name "copilot-usage-tray" -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Write-Host "smoke test done"
