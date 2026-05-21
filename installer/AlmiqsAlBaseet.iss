; Inno Setup script for AlmiqsAlBaseet.
; Build with build_installer.bat after verify_release.bat succeeds.

#define MyAppName "المقص البسيط"
#define MyAppInternalName "AlmiqsAlBaseet"
#define MyAppVersion "1.0.0"
#define MyAppExeName "AlmiqsAlBaseet.exe"

[Setup]
AppId={{B1DB9A62-2292-40A7-A3F2-64F7A3EA84E6}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher=AlmiqsAlBaseet
DefaultDirName={autopf}\{#MyAppInternalName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=..\release\installer
OutputBaseFilename=AlmiqsAlBaseet-Setup
Compression=lzma
SolidCompression=yes
WizardStyle=modern
SetupIconFile=..\assets\icon.ico
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "arabic"; MessagesFile: "compiler:Languages\Arabic.isl"

[Tasks]
Name: "desktopicon"; Description: "إنشاء اختصار على سطح المكتب"; GroupDescription: "اختصارات إضافية:"; Flags: unchecked

[Files]
Source: "..\dist\AlmiqsAlBaseet\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "تشغيل {#MyAppName}"; Flags: nowait postinstall skipifsilent
