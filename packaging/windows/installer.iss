; Inno Setup 6 script for Copilot Usage Tracker (Windows).
; Built by packaging/windows/build.ps1 or the Packaging GitHub workflow.
; Paths are relative to this file's directory (packaging/windows).

#define MyAppName "Copilot Usage Tracker"
#define MyAppExe "copilot-usage-tray.exe"
; NOTE: AppId is hardcoded below with {{ }} (Inno's literal-brace escape).
; Do NOT route it through {#...}: ISPP collapses {{ before Inno parses
; constants, which breaks the GUID into an "unknown constant" error.

#ifndef AppVersion
  #define AppVersion "0.1.0"
#endif

[Setup]
AppId={{104C27E1-409E-46A5-981B-A79EB2A23913}
AppName={#MyAppName}
AppVersion={#AppVersion}
AppVerName={#MyAppName} {#AppVersion}
AppPublisher=Sanjay Santhanam
AppPublisherURL=https://github.com/Sanjays2402/copilot-usage-tracker
AppSupportURL=https://github.com/Sanjays2402/copilot-usage-tracker/issues
DefaultDirName={autopf}\CopilotUsageTracker
PrivilegesRequired=lowest
OutputDir=dist
OutputBaseFilename=CopilotUsageTracker-Setup-{#AppVersion}
SetupIconFile=..\assets\icon.ico
UninstallDisplayIcon={app}\{#MyAppExe}
LicenseFile=..\..\LICENSE
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
DisableProgramGroupPage=yes
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "startup"; Description: "Launch at Windows startup"; GroupDescription: "Startup:"; Flags: unchecked
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"; Flags: unchecked

[Files]
; PyInstaller onedir output, produced by `pyinstaller tray/pyinstaller.spec`
Source: "dist\copilot-usage-tray\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\Copilot Usage Tracker"; Filename: "{app}\{#MyAppExe}"
Name: "{autodesktop}\Copilot Usage Tracker"; Filename: "{app}\{#MyAppExe}"; Tasks: desktopicon

[Registry]
; Optional run-at-login (HKCU: no admin rights needed)
Root: HKCU; Subkey: "SOFTWARE\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; \
  ValueName: "CopilotUsageTracker"; ValueData: """{app}\{#MyAppExe}"""; \
  Flags: uninsdeletevalue; Tasks: startup

[Run]
Filename: "{app}\{#MyAppExe}"; Description: "Launch Copilot Usage Tracker"; \
  Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}"
