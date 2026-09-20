; Inno Setup script — compile after PyInstaller.
; Download Inno Setup: https://jrsoftware.org/isinfo.php

#define MyAppName "TrendForge Studio"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "TrendForge"
#define MyAppExeName "TrendForgeStudio.exe"

[Setup]
AppId={{8F3C2A91-7B14-4E55-9C0A-1D2E3F4A5B6C}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\TrendForge Studio
DefaultGroupName={#MyAppName}
OutputDir=..\release
OutputBaseFilename=TrendForgeStudio-Setup
Compression=lzma
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64
PrivilegesRequired=lowest

[Files]
Source: "..\dist\TrendForgeStudio\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop icon"; GroupDescription: "Additional icons:"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch TrendForge Studio"; Flags: nowait postinstall skipifsilent
