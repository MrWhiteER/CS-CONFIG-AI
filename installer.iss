; Inno Setup script for the installed edition of cs2-autoconfig.
;
; Two editions are published side by side and the updater knows which one it is
; running as (see cs2cfg/paths.py, install_kind):
;
;   portable    a zip, unpacked anywhere, data beside the exe, updates itself
;               by copying new files over the old ones
;   installed   this installer, per-user, data under the install folder,
;               updates itself by running the next Setup.exe silently
;
; AppId is fixed forever. Windows and Inno use it to recognise a later
; Setup.exe as an update to this same installation rather than a second copy
; of the program. Changing it strands everyone already installed on the old
; identity, with two entries in Add/Remove Programs and no upgrade path -- so
; it must never change, not even if the program is renamed.

#define AppName        "CS2 Launcher"
#define AppPublisher   "cs2-autoconfig"
#define AppExe         "CS2 Launcher.exe"
#define AppUrl         "https://github.com/REPLACE_ME/cs2-autoconfig"

; Passed in by tools/release.py so the version is never written twice.
#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{52CB95CD-82DB-40CA-8E48-7DDE2C72820D}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
AppSupportURL={#AppUrl}
AppUpdatesURL={#AppUrl}/releases

; Per-user, so there is no administrator prompt and no elevation to fail
; behind a silent update. It also means the program can write its own data
; inside its own install folder, the way the portable edition does.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
DefaultDirName={localappdata}\cs2-autoconfig
DisableDirPage=auto
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes

OutputDir=dist
OutputBaseFilename=cs2-autoconfig-{#AppVersion}-Setup
SetupIconFile=build\cs2cfg.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
ArchitecturesAllowed=x64compatible

; Asks the running program to close before replacing it. It only asks -- a
; process that ignores it still holds the file lock -- so the updater waits for
; every process running out of the install folder before starting this at all.
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Shortcuts:"

[Files]
Source: "dist\CS2 Launcher.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "dist\cs2cfg.exe";       DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#AppName}";              Filename: "{app}\{#AppExe}"
Name: "{group}\Uninstall {#AppName}";    Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}";        Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
; Only offered in an interactive install. A silent update run by the updater
; relaunches the program itself once the copy is finished.
Filename: "{app}\{#AppExe}"; Description: "Open {#AppName}"; \
  Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Written by the updater while staging a download. Nothing here is the user's
; own work -- their preferences and backups live in cs2cfg-data, which is
; deliberately left alone so reinstalling does not lose them.
Type: filesandordirs; Name: "{app}\cs2cfg-data\updates"
