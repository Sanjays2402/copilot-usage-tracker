<#
.SYNOPSIS
  Genuine end-to-end smoke test of the Windows installer on a real machine.

  Phase 1 (interactive): opens the actual Inno Setup wizard and screenshots
  it as it appears, then closes it without installing.

  Phase 2 (silent): runs the installer with /SILENT -- the genuine
  progress dialog is screenshotted -- waits for it to finish, and verifies
  the installed files.

  Phase 3: installs the WebView2 runtime (inbox on real Win10/11, missing on
  the Server runner SKU), launches the installed app, screenshots the
  first-run setup window, and asserts the dashboard server comes up and
  serves the app over HTTP (ground truth from tray.log).

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
# The native dashboard window needs the WebView2 runtime. Real Windows 10/11
# machines have it inbox; this Server runner SKU does not, so install it to
# match a user machine (silent, ~1 min).
$wvInstaller = Join-Path $env:TEMP "MicrosoftEdgeWebView2RuntimeInstallerX64.exe"
Invoke-WebRequest -Uri "https://go.microsoft.com/fwlink/p/?LinkId=2124703" -OutFile $wvInstaller
Start-Process $wvInstaller -ArgumentList "/silent", "/install" -Wait
Write-Host "webview2 runtime installed"
# Minimize everything first: the runner's terminal is maximized and would
# otherwise cover the app window in screenshots.
(New-Object -ComObject Shell.Application).MinimizeAll()
Start-Sleep -Seconds 2
$app = Start-Process $appExe -PassThru

# Ground truth: the tray app logs milestones to tray.log. Poll for the
# server-up milestone -- a cold Streamlit start on a busy runner can take
# a couple of minutes.
$logFile = Join-Path $env:LOCALAPPDATA "Sanjays2402\copilot-usage-tracker\tray.log"
$serverLogFile = Join-Path $env:LOCALAPPDATA "Sanjays2402\copilot-usage-tracker\dashboard-server.log"
$serverUp = $false
$port = 8501
$shotsTaken = 0
$deadline = (Get-Date).AddSeconds(300)
while ((Get-Date) -lt $deadline) {
    Start-Sleep -Seconds 15
    # Focus the app window so the screenshots capture it (not the desktop).
    Focus-Window $app | Out-Null
    $shotsTaken += 1
    Save-Shot "app-first-run-$shotsTaken.png"
    if (Test-Path $logFile) {
        $logText = Get-Content $logFile -Raw
        $m = [regex]::Match($logText, "dashboard server up on 127\.0\.0\.1:(\d+)")
        if ($m.Success) {
            $serverUp = $true
            $port = $m.Groups[1].Value
            break
        }
    }
    $app.Refresh()
    if ($app.HasExited) { break }
}
Write-Host "--- tray.log (last 20 lines) ---"
if (Test-Path $logFile) {
    Get-Content $logFile | Select-Object -Last 20 | ForEach-Object { Write-Host $_ }
} else {
    Write-Host "tray.log not found at $logFile"
}
Write-Host "--- dashboard-server.log (last 30 lines) ---"
if (Test-Path $serverLogFile) {
    Get-Content $serverLogFile | Select-Object -Last 30 | ForEach-Object { Write-Host $_ }
} else {
    Write-Host "dashboard-server.log not found at $serverLogFile"
}
if (-not $serverUp) {
    throw "dashboard server never came up (see tray.log above)"
}

# The server must actually serve the Streamlit app over HTTP.
$dashOk = $false
for ($i = 0; $i -lt 12 -and -not $dashOk; $i++) {
    try {
        $resp = Invoke-WebRequest -Uri "http://127.0.0.1:$port/" -UseBasicParsing -TimeoutSec 10
        if ($resp.StatusCode -eq 200 -and $resp.Content -match "streamlit") {
            $dashOk = $true
        } else {
            Start-Sleep -Seconds 10
        }
    } catch {
        Start-Sleep -Seconds 10
    }
}
if (-not $dashOk) {
    throw "dashboard server is up but did not serve the app over HTTP"
}
Write-Host "dashboard serves HTTP 200 on port $port"

# Native window is informational: with WebView2 installed it should show;
# without it the app falls back to the browser by design.
$windowShown = (Test-Path $logFile) -and ((Get-Content $logFile -Raw) -match "dashboard window shown")
Write-Host "native dashboard window shown: $windowShown"

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
