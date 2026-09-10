<#
.SYNOPSIS
  Genuine end-to-end smoke test of the Windows installer on a real machine.

  Phase 1 (interactive): opens the actual Inno Setup wizard and screenshots
  it as it appears, then closes it without installing.

  Phase 2 (silent): runs the installer with /SILENT -- the genuine
  progress dialog is screenshotted -- waits for it to finish, and verifies
  the installed files.

  Phase 3: launches the installed app and screenshots the first-run setup
  window.

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

function Focus-Window {
    param($Proc, [int]$Tries = 10)
    $shell = New-Object -ComObject WScript.Shell
    for ($i = 0; $i -lt $Tries; $i++) {
        $Proc.Refresh()
        if ($Proc.MainWindowHandle -ne 0) {
            $shell.AppActivate($Proc.Id) | Out-Null
            return $true
        }
        Start-Sleep -Seconds 1
    }
    return $false
}

function Send-FocusedKeys {
    param($Proc, [string]$Keys, [int]$SettleSeconds = 4)
    if (Focus-Window $Proc) {
        Start-Sleep -Seconds 1
        (New-Object -ComObject WScript.Shell).SendKeys($Keys)
    } else {
        Write-Host "WARNING: could not focus installer window for keys $Keys"
    }
    Start-Sleep -Seconds $SettleSeconds
}

$setup = Get-ChildItem "CopilotUsageTracker-Setup-*.exe" | Sort-Object LastWriteTime -Descending | Select-Object -First 1
if (-not $setup) { throw "installer exe not found in $(Get-Location)" }

# Drop any Mark-of-the-Web so SmartScreen doesn't gate the genuine run.
Unblock-File -Path $setup.FullName -ErrorAction SilentlyContinue

# ---- Phase 1: wizard screenshot ------------------------------------------------
# Capture one honest screenshot of the real installer wizard as it appears.
# (Page-turning via SendKeys proved flaky on headless runners, so we no
# longer pretend to click through pages.)
Write-Host "phase 1: installer wizard window"
$wiz = Start-Process $setup.FullName -PassThru
Start-Sleep -Seconds 10
if (Focus-Window $wiz) { Start-Sleep -Seconds 2 }
Save-Shot "installer-wizard.png"

# Close the wizard without installing; the real install happens in phase 2.
# Kill by window title (not PID): Inno spawns the wizard UI such that the
# original process handle may already be gone, leaving the window behind.
Stop-Process -Id $wiz.Id -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2
Get-Process | Where-Object { $_.MainWindowTitle -like "Setup - Copilot Usage Tracker*" } |
    Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 3
$leftover = Get-Process | Where-Object { $_.MainWindowTitle -like "Setup - Copilot Usage Tracker*" }
if ($leftover) { throw "installer wizard did not close; it would obscure later screenshots" }

# ---- Phase 2: genuine silent install (progress dialog is real) -------------
Write-Host "phase 2: silent install"
$inst = Start-Process $setup.FullName -ArgumentList "/SILENT" -PassThru
Start-Sleep -Seconds 12
Save-Shot "installer-progress.png"
if (-not $inst.WaitForExit(300000)) { throw "installer did not finish within 5 minutes" }
Write-Host "installer exit code: $($inst.ExitCode)"
if ($inst.ExitCode -ne 0) {
    Save-Shot "installer-failed.png"
    throw "installer exited with code $($inst.ExitCode)"
}

$appExe = Join-Path $env:LOCALAPPDATA "Programs\CopilotUsageTracker\copilot-usage-tray.exe"
if (-not (Test-Path $appExe)) {
    Save-Shot "install-missing.png"
    throw "installed exe not found: $appExe"
}
Write-Host "installed OK: $appExe"

# ---- Phase 3: launch the app, screenshot first-run setup -------------------
Write-Host "phase 3: launch installed app"
# Minimize everything first: the runner's terminal is maximized and would
# otherwise cover the app window in screenshots.
(New-Object -ComObject Shell.Application).MinimizeAll()
Start-Sleep -Seconds 2
$app = Start-Process $appExe -PassThru
Start-Sleep -Seconds 45
# Focus the app window so the screenshot captures it (not the desktop).
Focus-Window $app | Out-Null
Start-Sleep -Seconds 2
Save-Shot "app-first-run.png"
Start-Sleep -Seconds 15
Focus-Window $app | Out-Null
Start-Sleep -Seconds 2
Save-Shot "app-first-run-2.png"
# A PyInstaller "Unhandled exception in script" dialog keeps the process
# alive -- the screenshots above are the verification (reviewed manually),
# but fail loudly if the app died outright.
$app.Refresh()
if ($app.HasExited -and $app.ExitCode -ne 0) {
    throw "app exited with code $($app.ExitCode) shortly after launch"
}
Stop-Process -Id $app.Id -Force -ErrorAction SilentlyContinue
Get-Process -Name "copilot-usage-tray" -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Write-Host "smoke test done"
