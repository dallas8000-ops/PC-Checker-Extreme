; =============================================================================
; PC Checker Extreme - Inno Setup Installer Script
; Build with:  iscc installer\PCCheckerExtreme.iss
;              (or run installer\build_installer.ps1 for the full pipeline)
; =============================================================================

#define AppName      "PC Checker Extreme"
#define AppVersion   "1.0.0"
#define AppPublisher "Gilliom Frontline Digital"
#define AppURL       "https://gilliomfrontlinedigital.com"

[Setup]
; Unique GUID for the app - regenerate if you fork/brand this
AppId={{4B7E2C9A-83F1-4D6E-B512-A9C3E8F07D24}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}
AppUpdatesURL={#AppURL}

; Install into %LOCALAPPDATA% - no UAC elevation required
DefaultDirName={localappdata}\{#AppName}
DefaultGroupName={#AppName}
AllowNoIcons=no
DisableDirPage=yes

; Output
OutputDir=dist
OutputBaseFilename=PCCheckerExtreme-Setup
SetupIconFile=icon.ico

; Compression
Compression=lzma2/ultra
SolidCompression=yes

; No admin rights needed
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=

; Require 64-bit Windows
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0

; Visual
WizardStyle=modern
WizardSizePercent=110

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"
Name: "startupentry"; Description: "Start {#AppName} automatically when Windows starts"; GroupDescription: "Startup:"

; =============================================================================
; FILES
; =============================================================================
[Files]
; --- Django source ---
Source: "..\manage.py";           DestDir: "{app}"; Flags: ignoreversion

Source: "..\pc_checker_extreme\*"; DestDir: "{app}\pc_checker_extreme"; \
  Flags: ignoreversion recursesubdirs createallsubdirs; \
  Excludes: "*.pyc,__pycache__"

Source: "..\diagnostics\*";       DestDir: "{app}\diagnostics"; \
  Flags: ignoreversion recursesubdirs createallsubdirs; \
  Excludes: "*.pyc,__pycache__"

Source: "..\stripe\*";            DestDir: "{app}\stripe"; \
  Flags: ignoreversion recursesubdirs createallsubdirs; \
  Excludes: "*.pyc,__pycache__"

; --- Pre-collected static files (built by build_installer.ps1) ---
Source: "..\staticfiles\*";      DestDir: "{app}\staticfiles"; \
  Flags: ignoreversion recursesubdirs createallsubdirs

; --- Pre-migrated, pre-seeded database (built by build_installer.ps1) ---
Source: "build\db.sqlite3";      DestDir: "{app}"; Flags: ignoreversion

; --- Bundled Python + packages (built by build_installer.ps1) ---
Source: "build\python\*";        DestDir: "{app}\python"; \
  Flags: ignoreversion recursesubdirs createallsubdirs

; --- Installer helpers ---
Source: "setup_env.py";          DestDir: "{app}"; Flags: ignoreversion
Source: "launcher.vbs";          DestDir: "{app}"; Flags: ignoreversion
Source: "stopper.vbs";           DestDir: "{app}"; Flags: ignoreversion
Source: "icon.ico";              DestDir: "{app}"; Flags: ignoreversion

; =============================================================================
; SHORTCUTS
; =============================================================================
[Icons]
; Start Menu
Name: "{group}\{#AppName}"; \
  Filename: "{sys}\wscript.exe"; Parameters: """{app}\launcher.vbs"""; \
  WorkingDir: "{app}"; IconFilename: "{app}\icon.ico"

Name: "{group}\Stop {#AppName}"; \
  Filename: "{sys}\wscript.exe"; Parameters: """{app}\stopper.vbs"""; \
  WorkingDir: "{app}"

Name: "{group}\{cm:UninstallProgram,{#AppName}}"; \
  Filename: "{uninstallexe}"

; Desktop (optional task)
Name: "{userdesktop}\{#AppName}"; \
  Filename: "{sys}\wscript.exe"; Parameters: """{app}\launcher.vbs"""; \
  WorkingDir: "{app}"; IconFilename: "{app}\icon.ico"; \
  Tasks: desktopicon

; Startup folder (optional task)
Name: "{userstartup}\{#AppName}"; \
  Filename: "{sys}\wscript.exe"; Parameters: """{app}\launcher.vbs"""; \
  WorkingDir: "{app}"; IconFilename: "{app}\icon.ico"; \
  Tasks: startupentry

; =============================================================================
; POST-INSTALL STEPS  (run in order)
; =============================================================================
[Run]
; 1. Generate .env with a fresh SECRET_KEY (skips if .env already exists)
Filename: "{app}\python\python.exe"; \
  Parameters: "setup_env.py"; \
  WorkingDir: "{app}"; \
  Flags: runhidden; \
  StatusMsg: "Generating security keys..."

; 2. Offer to launch the app immediately
Filename: "{sys}\wscript.exe"; \
  Parameters: """{app}\launcher.vbs"""; \
  WorkingDir: "{app}"; \
  Flags: nowait postinstall skipifsilent; \
  Description: "Launch {#AppName} now"

; =============================================================================
; UNINSTALL CLEANUP
; =============================================================================
[UninstallDelete]
; Remove runtime-generated files that the uninstaller won't know about
Type: files;      Name: "{app}\.env"
Type: files;      Name: "{app}\db.sqlite3"
Type: filesandordirs; Name: "{app}\__pycache__"
Type: filesandordirs; Name: "{app}\pc_checker_extreme\__pycache__"
Type: filesandordirs; Name: "{app}\diagnostics\__pycache__"
Type: filesandordirs; Name: "{app}\stripe\__pycache__"
; Remove the install dir if it is now empty
Type: dirifempty; Name: "{app}"
