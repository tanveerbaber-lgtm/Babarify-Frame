; Babarify Media Player installer (M10). Built by tools/build_release.py, which defines AppVersion,
; DistDir and OutputDir and writes build\assoc.iss (one entry per media extension).
;
; Per-user install (no administrator rights) to %LOCALAPPDATA%\Programs\Babarify Media Player.
; The same AppId makes a newer installer upgrade in place (and an older one roll back). An upgrade
; from when the app was called Babarify Frame stays in that folder, and keeps its data folders.
; File associations are optional (unticked) and only add "Open with" entries: Babarify never
; takes over a file type; Windows asks the user to choose defaults.
; User data (settings, library, history, bookmarks, generated subtitles, models, logs) is kept
; on uninstall unless the user chooses to remove it.

#ifndef AppVersion
  #error AppVersion must be defined (/DAppVersion=x.y.z)
#endif
#define AppName "Babarify Media Player"
#define AppExe "Babarify Media Player.exe"
#define ProgId "BabarifyFrame.Media"

[Setup]
AppId={{6C6E6628-FE5B-4E93-ADA0-C13ADF7F99A2}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=Tanveer Baber
AppCopyright=Copyright (C) 2026 Tanveer Baber. Licensed under the GNU GPL v3 or later.
VersionInfoVersion={#AppVersion}
DefaultDirName={localappdata}\Programs\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.17763
LicenseFile={#SourcePath}\..\LICENSE
OutputDir={#OutputDir}
OutputBaseFilename=BabarifyMediaPlayer-{#AppVersion}-setup
SetupIconFile={#SourcePath}\..\src\babarify_frame\resources\icons\babarify-frame.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
ChangesAssociations=yes
SetupLogging=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Types]
Name: "full"; Description: "Full installation (with local AI features)"
Name: "compact"; Description: "Compact installation (about 240 MB smaller, no AI features)"
Name: "custom"; Description: "Custom installation"; Flags: iscustom

[Components]
Name: "main"; Description: "Babarify Media Player"; Types: full compact custom; Flags: fixed
Name: "ai"; Description: "Local AI features: subtitles from speech, spoken-word search (runs on this PC; about 240 MB)"; Types: full

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked
Name: "openwith"; Description: "Offer {#AppName} in ""Open with"" for video and audio files (does not change your default apps)"; Flags: unchecked

[InstallDelete]
; An upgrade replaces the program folder completely, so no file of an older version is left.
; The first three are from when the app was called Babarify Frame.
Type: files; Name: "{app}\Babarify Frame.exe"
Type: files; Name: "{autoprograms}\Babarify Frame.lnk"
Type: files; Name: "{autodesktop}\Babarify Frame.lnk"
Type: filesandordirs; Name: "{app}\_internal"
Type: filesandordirs; Name: "{app}\engines"
Type: filesandordirs; Name: "{app}\ai"

[Files]
Source: "{#DistDir}\*"; DestDir: "{app}"; Excludes: "\ai\*"; Components: main; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#DistDir}\ai\*"; DestDir: "{app}\ai"; Components: ai; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Registry]
; Left by versions called Babarify Frame.
Root: HKCU; Subkey: "Software\Classes\Applications\Babarify Frame.exe"; Flags: deletekey dontcreatekey
Root: HKCU; Subkey: "Software\RegisteredApplications"; ValueType: none; ValueName: "Babarify Frame"; Flags: deletevalue dontcreatekey
; "Open with" support and an entry in Settings > Default apps (only with the openwith task).
Root: HKCU; Subkey: "Software\Classes\{#ProgId}"; ValueType: string; ValueName: ""; ValueData: "Media file ({#AppName})"; Flags: uninsdeletekey; Tasks: openwith
Root: HKCU; Subkey: "Software\Classes\{#ProgId}\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\{#AppExe},0"; Tasks: openwith
Root: HKCU; Subkey: "Software\Classes\{#ProgId}\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExe}"" ""%1"""; Tasks: openwith
Root: HKCU; Subkey: "Software\Classes\Applications\{#AppExe}"; ValueType: string; ValueName: "FriendlyAppName"; ValueData: "{#AppName}"; Flags: uninsdeletekey; Tasks: openwith
Root: HKCU; Subkey: "Software\Classes\Applications\{#AppExe}\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExe}"" ""%1"""; Tasks: openwith
Root: HKCU; Subkey: "Software\Babarify\Frame\Capabilities"; ValueType: string; ValueName: "ApplicationName"; ValueData: "{#AppName}"; Flags: uninsdeletekey; Tasks: openwith
Root: HKCU; Subkey: "Software\Babarify\Frame\Capabilities"; ValueType: string; ValueName: "ApplicationDescription"; ValueData: "A free, privacy-focused media player"; Tasks: openwith
Root: HKCU; Subkey: "Software\RegisteredApplications"; ValueType: string; ValueName: "{#AppName}"; ValueData: "Software\Babarify\Frame\Capabilities"; Flags: uninsdeletevalue; Tasks: openwith
#include AddBackslash(SourcePath) + "..\build\assoc.iss"

[Run]
Filename: "{app}\{#AppExe}"; Description: "Start {#AppName}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}\_internal"
Type: filesandordirs; Name: "{app}\engines"
Type: filesandordirs; Name: "{app}\ai"

[Code]
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  Roaming, Local: String;
begin
  if (CurUninstallStep = usPostUninstall) and not UninstallSilent then
  begin
    Roaming := ExpandConstant('{userappdata}\Babarify\Frame');
    Local := ExpandConstant('{localappdata}\Babarify\Frame');
    if (DirExists(Roaming) or DirExists(Local)) and
       (MsgBox('Also delete your Babarify Media Player data on this PC?' + #13#10 + #13#10 +
               'Settings, library, history, bookmarks, generated subtitles, speech models and logs.' + #13#10 +
               'Your media files are never touched. Choose No to keep them for a later install.',
               mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES) then
    begin
      DelTree(Roaming, True, True, True);
      DelTree(Local, True, True, True);
    end;
  end;
end;
