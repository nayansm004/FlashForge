; Inno Setup script for FlashForge
; Produces a click-through Windows installer: FlashForge-Setup.exe
; Install Inno Setup (or use the chocolatey/CI package) then compile with:
;   iscc installer\windows.iss
; The CI workflow does this automatically on every tagged release.

#define MyAppName "FlashForge"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "FlashForge"
#define MyAppExeName "FlashForge.exe"

[Setup]
AppId={{8F3B2C9A-6C2E-4B7A-9B1D-1E2F3A4B5C6D}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
UninstallDisplayIcon={app}\{#MyAppExeName}
OutputDir=..\dist_installer
OutputBaseFilename=FlashForge-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
SetupIconFile=..\assets\icon.ico
DisableProgramGroupPage=yes
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional shortcuts:"

[Files]
; Pulls in the entire PyInstaller onedir output built by `pyinstaller flashforge.spec`
Source: "..\dist\FlashForge\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent
