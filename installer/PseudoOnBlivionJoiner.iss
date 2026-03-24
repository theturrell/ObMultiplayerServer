#ifndef SourceRoot
  #error SourceRoot must be defined on the ISCC command line.
#endif

#ifndef OutputRoot
  #define OutputRoot SourceRoot + "\installers"
#endif

[Setup]
AppId={{3B3E4044-6801-4B75-BB48-CB3CF47D9C22}
AppName=Pseudo-OnBlivion Joiner
AppVersion=0.1.0
AppPublisher=OpenAI Codex Prototype
DefaultDirName={autopf}\Pseudo-OnBlivion Joiner Support
DefaultGroupName=Pseudo-OnBlivion Joiner
DisableProgramGroupPage=yes
OutputDir={#OutputRoot}
OutputBaseFilename=PseudoOnBlivionJoinerSetup
Compression=lzma
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
CloseApplications=yes
CloseApplicationsFilter=PseudoOnBlivionHost.exe,PseudoOnBlivionJoiner.exe,PseudoOnBlivionRelay.exe

[InstallDelete]
Type: files; Name: "{app}\PseudoOnBlivionJoiner.exe"
Type: files; Name: "{app}\README_JOINER.txt"
Type: files; Name: "{app}\QUICKSTART.md"
Type: files; Name: "{app}\version.json"
Type: filesandordirs; Name: "{app}\scripts"
Type: filesandordirs; Name: "{app}\Data"

[Files]
Source: "{#SourceRoot}\PseudoOnBlivion-Joiner\scripts\*"; DestDir: "{app}\scripts"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#SourceRoot}\PseudoOnBlivion-Joiner\QUICKSTART.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#SourceRoot}\PseudoOnBlivion-Joiner\README_JOINER.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#SourceRoot}\PseudoOnBlivion-Joiner\version.json"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#SourceRoot}\PseudoOnBlivion-Joiner\PseudoOnBlivionJoiner.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#SourceRoot}\PseudoOnBlivion-Joiner\Data\OBSE\Plugins\*"; DestDir: "{app}\Data\OBSE\Plugins"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#SourceRoot}\PseudoOnBlivion-Joiner\Data\OBSE\Plugins\*"; DestDir: "{code:GetGamePluginDir}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\Pseudo-OnBlivion Joiner\Join Oblivion"; Filename: "{app}\PseudoOnBlivionJoiner.exe"
Name: "{autoprograms}\Pseudo-OnBlivion Joiner\Open Support Folder"; Filename: "{app}"

[Run]
Filename: "{app}\PseudoOnBlivionJoiner.exe"; Description: "Open the joiner app"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}\scripts"
Type: filesandordirs; Name: "{app}\Data"

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
    'Choose the Oblivion installation that should receive the joiner plugin.',
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
