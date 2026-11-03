; NL Code Windows installer (Inno Setup).
; Compiled by scripts/nlcode/build_release.ps1 with:
;   /DPayloadDir=... /DAppVersion=... /DOutputDir=... /DSetupIcon=...
; The installer ships the verified standalone payload, lets the user choose any
; installation and data directory, registers an uninstaller in Windows "Apps",
; and keeps the portable ZIP completely independent.

#ifndef PayloadDir
  #error PayloadDir define is required
#endif
#ifndef AppVersion
  #define AppVersion "0.7.2"
#endif
#ifndef OutputDir
  #define OutputDir "."
#endif

#define MyAppName "NL Code"
#define MyAppPublisher "Nicotina4ever"
#define MyAppURL "https://github.com/Nicotina4ever/NL-Coding-Agent"
#define MyAppExeName "NL Code.exe"

[Setup]
AppId={{A6C9E3D1-7B2C-4F0A-9D6E-52D8C5B4E7A1}
AppName={#MyAppName}
AppVersion={#AppVersion}
AppVerName={#MyAppName} {#AppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\NL Code
DefaultGroupName=NL Code
DisableProgramGroupPage=yes
OutputDir={#OutputDir}
OutputBaseFilename=NL-Code-Setup
Compression=lzma2/fast
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
UsePreviousAppDir=yes
UsePreviousTasks=yes
CloseApplications=yes
RestartApplications=no
AppMutex=nlcode
UninstallDisplayName={#MyAppName}
UninstallDisplayIcon={app}\{#MyAppExeName}
VersionInfoVersion={#AppVersion}
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription={#MyAppName} installer
VersionInfoProductName={#MyAppName}
VersionInfoProductVersion={#AppVersion}
SetupIconFile={#SetupIcon}

[Files]
; Never install the payload's live data/ or setup marker; user data is external.
Source: "{#PayloadDir}\*"; DestDir: "{app}"; Excludes: "data\*,setup-version.txt"; Flags: ignoreversion recursesubdirs createallsubdirs
; The NL Coder extension is installed into the user-selected data root, matching
; the --extensions-dir used by the generated launcher.
Source: "{#PayloadDir}\data\extensions\*"; DestDir: "{code:GetExtensionsDir}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Tasks]
Name: "desktopicon"; Description: "Crea un collegamento sul desktop"; GroupDescription: "Collegamenti:"; Flags: unchecked
Name: "startmenu"; Description: "Crea i collegamenti nel menu Start"; GroupDescription: "Collegamenti:"; Flags: checkedonce

[Icons]
Name: "{autoprograms}\NL Code\NL Code"; Filename: "{cmd}"; Parameters: "/c """"{app}\NL Code Installed.cmd"""""; WorkingDir: "{app}"; IconFilename: "{app}\{#MyAppExeName}"; Tasks: startmenu
Name: "{autoprograms}\NL Code\Disinstalla NL Code"; Filename: "{uninstallexe}"; Tasks: startmenu
Name: "{autodesktop}\NL Code"; Filename: "{cmd}"; Parameters: "/c """"{app}\NL Code Installed.cmd"""""; WorkingDir: "{app}"; IconFilename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Registry]
Root: HKA; Subkey: "Software\NL Code"; ValueType: string; ValueName: "InstallDir"; ValueData: "{app}"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\NL Code"; ValueType: string; ValueName: "DataDir"; ValueData: "{code:GetDataDir}"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\NL Code"; ValueType: string; ValueName: "Version"; ValueData: "{#AppVersion}"; Flags: uninsdeletekey

[Run]
Filename: "{app}\NL Code Installed.cmd"; Description: "Avvia NL Code"; Flags: nowait postinstall skipifsilent

[Code]
var
  DataPage: TInputDirWizardPage;
  RemoveData: Boolean;
  SavedDataDir: String;

function ReplaceAll(const S, OldPattern, NewPattern: String): String;
var
  P: Integer;
  Rest: String;
begin
  Rest := S;
  Result := '';
  while True do
  begin
    P := Pos(OldPattern, Rest);
    if P = 0 then
    begin
      Result := Result + Rest;
      Break;
    end;
    Result := Result + Copy(Rest, 1, P - 1) + NewPattern;
    Rest := Copy(Rest, P + Length(OldPattern), Length(Rest));
  end;
end;

function JsonEsc(Value: String): String;
begin
  Result := ReplaceAll(Value, '\', '/');
  Result := ReplaceAll(Result, '"', '\"');
end;

function GetDataDir(Param: String): String;
begin
  if DataPage <> nil then
    Result := DataPage.Values[0]
  else
    Result := SavedDataDir;
end;

function GetExtensionsDir(Param: String): String;
begin
  Result := GetDataDir('') + '\extensions';
end;

procedure InitializeWizard;
var
  previous: String;
  defaultDir: String;
begin
  if IsAdminInstallMode then
    defaultDir := ExpandConstant('{commonappdata}\NL Code\data')
  else
    defaultDir := ExpandConstant('{localappdata}\NL Code\data');
  defaultDir := ExpandConstant('{param:DATADIR|' + defaultDir + '}');
  DataPage := CreateInputDirPage(wpSelectDir,
    'Cartella dati NL Code',
    'Scegli dove conservare dati, database e workspace di NL Code.',
    'I file dell''applicazione e il runtime vanno nella cartella di installazione; ' +
    'dati, database, workspace e cache possono stare anche su un altro disco. ' +
    'I progetti e i modelli Ollama non vengono mai spostati o eliminati.',
    False, '');
  DataPage.Add('Cartella dati:');
  if ExpandConstant('{param:DATADIR|}') <> '' then
    DataPage.Values[0] := defaultDir
  else if RegQueryStringValue(HKA, 'Software\NL Code', 'DataDir', previous) and (previous <> '') then
    DataPage.Values[0] := previous
  else
    DataPage.Values[0] := defaultDir;
end;

function NextButtonClick(CurPageID: Integer): Boolean;
var
  selected: String;
begin
  Result := True;
  if (DataPage <> nil) and (CurPageID = DataPage.ID) then
  begin
    selected := Trim(DataPage.Values[0]);
    if selected = '' then
    begin
      MsgBox('Scegli una cartella dati.', mbError, MB_OK);
      Result := False;
      Exit;
    end;
    if CompareText(selected, ExpandConstant('{app}')) = 0 then
    begin
      MsgBox('La cartella dati deve essere diversa dalla cartella di installazione.', mbError, MB_OK);
      Result := False;
      Exit;
    end;
    DataPage.Values[0] := selected;
  end;
end;

procedure WriteText(Path, Content: String);
begin
  if not SaveStringToFile(Path, Content, False) then
    MsgBox('Impossibile scrivere ' + Path, mbError, MB_OK);
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  dataDir, cacheDir, workspaceDir, modelsConfig, batch, cfg: String;
begin
  if CurStep <> ssPostInstall then
    Exit;
  dataDir := DataPage.Values[0];
  cacheDir := dataDir + '\cache';
  workspaceDir := dataDir + '\workspace';
  modelsConfig := ExpandConstant('{app}\engine\config\models.yaml');
  ForceDirectories(dataDir);
  ForceDirectories(cacheDir);
  ForceDirectories(workspaceDir);
  cfg := '{"version":"' + JsonEsc('{#AppVersion}') + '",' +
         '"installDir":"' + JsonEsc(ExpandConstant('{app}')) + '",' +
         '"dataDir":"' + JsonEsc(dataDir) + '",' +
         '"workspaceDir":"' + JsonEsc(workspaceDir) + '",' +
         '"cacheDir":"' + JsonEsc(cacheDir) + '",' +
         '"modelsConfig":"' + JsonEsc(modelsConfig) + '"}';
  WriteText(ExpandConstant('{app}\install-config.json'), cfg + #13#10);
  // Code - OSS enters portable mode whenever <app>\data exists; the payload
  // contains an empty directory entry. Remove it so --user-data-dir and
  // --extensions-dir below are authoritative and no profile is written in the
  // application folder.
  DelTree(ExpandConstant('{app}\data'), True, True, True);
  batch := '@echo off' + #13#10 +
    'setlocal' + #13#10 +
    'set "NLCODE_ROOT=%~dp0"' + #13#10 +
    'set "NLCODE_ENGINE_ROOT=%~dp0engine"' + #13#10 +
    'set "NL_ENGINE_ROOT=%NLCODE_ENGINE_ROOT%"' + #13#10 +
    'set "ELECTRON_RUN_AS_NODE="' + #13#10 +
    'set "NL_DATA_DIR=' + dataDir + '"' + #13#10 +
    'set "NL_WORKSPACE_DIR=' + workspaceDir + '"' + #13#10 +
    'set "NL_CACHE_DIR=' + cacheDir + '"' + #13#10 +
    'set "NL_MODELS_CONFIG=' + modelsConfig + '"' + #13#10 +
    'if not exist "%NL_DATA_DIR%" mkdir "%NL_DATA_DIR%"' + #13#10 +
    'if not exist "%NL_WORKSPACE_DIR%" mkdir "%NL_WORKSPACE_DIR%"' + #13#10 +
    'start "" "%~dp0NL Code.exe" --user-data-dir="' + dataDir + '\user-data" --extensions-dir="' + dataDir + '\extensions" %*' + #13#10;
  WriteText(ExpandConstant('{app}\NL Code Installed.cmd'), batch);
end;

function InitializeUninstall(): Boolean;
var
  dataDir: String;
begin
  Result := True;
  RemoveData := False;
  SavedDataDir := '';
  if RegQueryStringValue(HKA, 'Software\NL Code', 'DataDir', dataDir) then
    SavedDataDir := dataDir;
  if SavedDataDir = '' then
    Exit;
  if UninstallSilent then
    RemoveData := ExpandConstant('{param:REMOVEDATA|0}') = '1'
  else
    RemoveData := MsgBox('Vuoi eliminare anche dati, database, workspace e cache di NL Code?' + #13#10 +
      'I progetti e i modelli Ollama non verranno toccati.',
      mbConfirmation, MB_YESNO) = IDYES;
  Result := True;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  appDir: String;
begin
  if CurUninstallStep <> usPostUninstall then
    Exit;
  appDir := ExpandConstant('{app}');
  // Generated configuration/launcher and runtime caches are not tracked as
  // installer files; remove them explicitly so uninstall leaves no app residue.
  DeleteFile(appDir + '\install-config.json');
  DeleteFile(appDir + '\NL Code Installed.cmd');
  DelTree(appDir + '\data', True, True, True);
  DelTree(appDir + '\resources\app\node-compile-cache', True, True, True);
  DelTree(appDir + '\resources', True, True, True);
  RemoveDir(appDir);
  if (not RemoveData) or (SavedDataDir = '') then
    Exit;
  if CompareText(SavedDataDir, appDir) = 0 then
    Exit;
  DelTree(SavedDataDir, True, True, True);
end;
