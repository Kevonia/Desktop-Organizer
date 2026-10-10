; Inno Setup script for the Windows installer. Run through packaging/build.py,
; which passes AppVersion, SourceDir and OutputDir on the command line.

#ifndef AppVersion
  #error AppVersion must be passed in, e.g. ISCC /DAppVersion=1.0.0
#endif

#define AppName "Desktop Organizer"
#define AppExe "DesktopOrganizer.exe"

[Setup]
; Never change AppId: Windows uses it to recognise upgrades of the same app.
AppId={{E4DF5B59-D9DD-4AED-9932-7198B4F2F9F1}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
VersionInfoVersion={#AppVersion}
AppPublisher={#AppName}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
; Installs for the current user without needing admin rights.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir={#OutputDir}
OutputBaseFilename=DesktopOrganizer-{#AppVersion}-Setup
SetupIconFile={#IconFile}
UninstallDisplayIcon={app}\{#AppExe}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent

[Registry]
; The app adds these File Explorer menu entries when the user turns them on in Settings.
; Listed here only so uninstalling removes them; installing doesn't create them.
Root: HKCU; Subkey: "Software\Classes\Directory\shell\DesktopOrganizer.Organize"; Flags: uninsdeletekey dontcreatekey
Root: HKCU; Subkey: "Software\Classes\Directory\Background\shell\DesktopOrganizer.Organize"; Flags: uninsdeletekey dontcreatekey
Root: HKCU; Subkey: "Software\Classes\Drive\shell\DesktopOrganizer.Organize"; Flags: uninsdeletekey dontcreatekey
Root: HKCU; Subkey: "Software\Classes\*\shell\DesktopOrganizer.WhereFrom"; Flags: uninsdeletekey dontcreatekey

; Settings and the undo history in %APPDATA%\DesktopOrganizer are kept on uninstall,
; so reinstalling keeps the user's folders and lets them undo earlier runs.
