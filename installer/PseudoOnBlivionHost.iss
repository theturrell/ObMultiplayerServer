#ifndef SourceRoot
  #error SourceRoot must be defined on the ISCC command line.
#endif

#ifndef OutputRoot
  #define OutputRoot SourceRoot + "\installers"
#endif

[Setup]
AppId={{A3F26C64-2134-4B31-BF1D-6B90CBA3D001}
AppName=Pseudo-OnBlivion Host
AppVersion=0.1.0
AppPublisher=OpenAI Codex Prototype
DefaultDirName={autopf}\Pseudo-OnBlivion Host
DefaultGroupName=Pseudo-OnBlivion Host
DisableProgramGroupPage=yes
OutputDir={#OutputRoot}
OutputBaseFilename=PseudoOnBlivionHostSetup
Compression=lzma
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
CloseApplications=yes
CloseApplicationsFilter=PseudoOnBlivionHost.exe,PseudoOnBlivionJoiner.exe,PseudoOnBlivionRelay.exe

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut for the host relay"; GroupDescription: "Additional shortcuts:"

[InstallDelete]
Type: files; Name: "{app}\PseudoOnBlivionHost.exe"
Type: files; Name: "{app}\README_HOST.txt"
Type: files; Name: "{app}\QUICKSTART.md"
Type: filesandordirs; Name: "{app}\server"
Type: filesandordirs; Name: "{app}\scripts"

[Files]
Source: "{#SourceRoot}\PseudoOnBlivion-Host\server\*"; DestDir: "{app}\server"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#SourceRoot}\PseudoOnBlivion-Host\scripts\*"; DestDir: "{app}\scripts"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#SourceRoot}\PseudoOnBlivion-Host\QUICKSTART.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#SourceRoot}\PseudoOnBlivion-Host\README_HOST.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#SourceRoot}\PseudoOnBlivion-Host\PseudoOnBlivionHost.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#SourceRoot}\PseudoOnBlivion-Host\Data\OBSE\Plugins\*"; DestDir: "{app}\Data\OBSE\Plugins"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#SourceRoot}\PseudoOnBlivion-Host\Data\OBSE\Plugins\*"; DestDir: "{code:GetGamePluginDir}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\Pseudo-OnBlivion Host\Host Control Panel"; Filename: "{app}\PseudoOnBlivionHost.exe"
Name: "{autoprograms}\Pseudo-OnBlivion Host\Start Relay"; Filename: "{sys}\WindowsPowerShell\v1.0\powershell.exe"; Parameters: "-ExecutionPolicy Bypass -File ""{app}\scripts\start_host_relay.ps1"""; WorkingDir: "{app}\server"
Name: "{autoprograms}\Pseudo-OnBlivion Host\Open Host Folder"; Filename: "{app}"
Name: "{autodesktop}\Pseudo-OnBlivion Host"; Filename: "{app}\PseudoOnBlivionHost.exe"; Tasks: desktopicon

[Run]
Filename: "{sys}\WindowsPowerShell\v1.0\powershell.exe"; Parameters: "-ExecutionPolicy Bypass -File ""{app}\scripts\open_firewall_port.ps1"""; Flags: postinstall skipifsilent unchecked; Description: "Open Windows Firewall port 7777"
Filename: "{app}\PseudoOnBlivionHost.exe"; Description: "Open the host control panel"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}\server"
Type: filesandordirs; Name: "{app}\scripts"

[Code]
var
  GamePathPage: TInputDirWizardPage;

function DetectDefaultGamePath(): string;
begin
  Result := ExpandConstant('{commonpf32}\Steam\steamapps\common\Oblivion');
  if FileExists(AddBackslash(Result) + 'Oblivion.exe') then
    exit;

  Result := ExpandConstant('{pf}\Steam\steamapps\common\Oblivion');
  if FileExists(AddBackslash(Result) + 'Oblivion.exe') then
    exit;

  Result := ExpandConstant('{commonpf32}\GOG Galaxy\Games\The Elder Scrolls IV - Oblivion Game of the Year Edition');
  if FileExists(AddBackslash(Result) + 'Oblivion.exe') then
    exit;

  Result := 'C:\Games\Oblivion';
end;

function GetGamePluginDir(Param: string): string;
begin
  Result := AddBackslash(GamePathPage.Values[0]) + 'Data\OBSE\Plugins';
end;

procedure InitializeWizard();
begin
  GamePathPage := CreateInputDirPage(
    wpSelectDir,
    'Oblivion Folder',
    'Choose the Oblivion installation that should receive the host plugin.',
    'The installer will copy the Pseudo-OnBlivion plugin into Oblivion\Data\OBSE\Plugins.',
    False,
    ''
  );
  GamePathPage.Add('');
  GamePathPage.Values[0] := DetectDefaultGamePath();
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if CurPageID = GamePathPage.ID then
  begin
    if not FileExists(AddBackslash(GamePathPage.Values[0]) + 'Oblivion.exe') then
    begin
      MsgBox('Please choose a valid Oblivion folder that contains Oblivion.exe.', mbError, MB_OK);
      Result := False;
    end;
  end;
end;
