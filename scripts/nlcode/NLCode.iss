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
  #define AppVersion "0.7.3"
#endif
#ifndef ModelsConfig
  #define ModelsConfig PayloadDir + "\engine\config\models.yaml"
#endif
#ifndef VsixFile
  #error VsixFile define is required
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
; Per-user release: shared all-users profiles are not shipped until standard-user
; ACL and multi-user acceptance have passed.
PrivilegesRequired=lowest
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
Source: "{#PayloadDir}\*"; DestDir: "{app}"; Excludes: "data,data\*,engine\data,engine\data\*,engine\config,engine\config\*,engine\.workspace,engine\.workspace\*,setup-version.txt,*.log,*.lnk,__pycache__,*\__pycache__\*,*.pyc,node-compile-cache,*\node-compile-cache\*"; Flags: ignoreversion recursesubdirs createallsubdirs
; The NL Coder extension is installed into the user-selected data root, matching
; the --extensions-dir used by the generated launcher.
Source: "{#PayloadDir}\data\extensions\nlcodingagent.nl-coding-agent-{#AppVersion}\*"; DestDir: "{code:GetExtensionsDir}\nlcodingagent.nl-coding-agent-{#AppVersion}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#ModelsConfig}"; DestName: "nlcode-default-models.yaml"; Flags: dontcopy
Source: "{#VsixFile}"; DestName: "NL-Coder.vsix"; Flags: dontcopy
Source: "{#SourcePath}\default_settings.json"; DestName: "nlcode-default-settings.json"; Flags: dontcopy

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

function FileAttributes(Path: String): LongWord;
  external 'GetFileAttributesW@kernel32.dll stdcall';
function SetEnvironment(Name, Value: String): Boolean;
  external 'SetEnvironmentVariableW@kernel32.dll stdcall';

function Canonical(Path: String): String;
begin
  Result := RemoveBackslashUnlessRoot(ExpandFileName(Trim(Path)));
end;

function ReparseAncestor(Path: String): Boolean;
var
  parent: String;
  attrs: LongWord;
begin
  Result := False;
  Path := Canonical(Path);
  while Path <> '' do
  begin
    attrs := FileAttributes(Path);
    if (attrs <> $FFFFFFFF) and ((attrs and $400) <> 0) then
    begin
      Result := True;
      Exit;
    end;
    parent := ExtractFileDir(Path);
    if CompareText(parent, Path) = 0 then Exit;
    Path := parent;
  end;
end;

function InvalidRoots(AppDir, DataDir: String): Boolean;
var
  appPrefix, dataPrefix: String;
begin
  if (Trim(AppDir) = '') or (Trim(DataDir) = '') then
  begin
    Result := True;
    Exit;
  end;
  AppDir := Canonical(AppDir);
  DataDir := Canonical(DataDir);
  appPrefix := AddBackslash(AppDir);
  dataPrefix := AddBackslash(DataDir);
  Result := (DataDir = '') or (AppDir = '') or
    (CompareText(DataDir, AddBackslash(ExtractFileDrive(DataDir))) = 0) or
    (CompareText(AppDir, AddBackslash(ExtractFileDrive(AppDir))) = 0) or
    (CompareText(Copy(dataPrefix, 1, Length(appPrefix)), appPrefix) = 0) or
    (CompareText(Copy(appPrefix, 1, Length(dataPrefix)), dataPrefix) = 0) or
    ReparseAncestor(AppDir) or ReparseAncestor(DataDir);
end;

function EmptyDirectory(Path: String): Boolean;
var
  item: TFindRec;
begin
  Result := not DirExists(Path);
  if FindFirst(AddBackslash(Path) + '*', item) then
  begin
    Result := True;
    try
      repeat
        if (item.Name <> '.') and (item.Name <> '..') then
        begin
          Result := False;
          Exit;
        end;
      until not FindNext(item);
    finally
      FindClose(item);
    end;
  end;
end;

function ReparseBelow(Path: String): Boolean;
var
  item: TFindRec;
begin
  Result := True;
  if FindFirst(AddBackslash(Path) + '*', item) then
  begin
    Result := False;
    try
      repeat
        if (item.Name <> '.') and (item.Name <> '..') then
        begin
          if ((item.Attributes and $400) <> 0) then Result := True
          else if ((item.Attributes and $10) <> 0) then
            Result := ReparseBelow(AddBackslash(Path) + item.Name);
          if Result then Exit;
        end;
      until not FindNext(item);
    finally
      FindClose(item);
    end;
  end;
end;

function OwnershipText(Path: String): String;
begin
  Result := 'NL-Code-data-v1|' + Lowercase(Canonical(Path));
end;

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
    if InvalidRoots(ExpandConstant('{app}'), selected) then
    begin
      MsgBox('Scegli cartelle applicazione e dati separate, senza sovrapposizioni, junction o radici di disco.', mbError, MB_OK);
      Result := False;
      Exit;
    end;
    DataPage.Values[0] := selected;
  end;
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  Result := '';
  if InvalidRoots(ExpandConstant('{app}'), DataPage.Values[0]) then
    Result := 'Cartelle applicazione/dati non valide o sovrapposte.'
  else if DirExists(ExpandConstant('{app}')) and ReparseBelow(ExpandConstant('{app}')) then
    Result := 'La cartella applicazione contiene junction o collegamenti non supportati.'
  else if DirExists(DataPage.Values[0]) and ReparseBelow(DataPage.Values[0]) then
    Result := 'La cartella dati contiene junction o collegamenti non supportati.'
  else if DirExists(ExpandConstant('{app}\data')) and
    not EmptyDirectory(ExpandConstant('{app}\data')) then
    Result := 'Questa cartella contiene un profilo portable. Scegli una cartella di installazione separata.';
end;

procedure WriteText(Path, Content: String);
begin
  if not SaveStringToFile(Path, Content, False) then
    MsgBox('Impossibile scrivere ' + Path, mbError, MB_OK);
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  dataDir, cacheDir, workspaceDir, modelsConfig, batch, cfg, oldModels, oldElectron, cliArgs: String;
  cliExit: Integer;
begin
  if CurStep = ssInstall then
  begin
    dataDir := Canonical(DataPage.Values[0]);
    if not DirExists(dataDir) or EmptyDirectory(dataDir) then
    begin
      ForceDirectories(dataDir);
      WriteText(dataDir + '\.nl-code-data-owner', OwnershipText(dataDir));
    end;
    modelsConfig := dataDir + '\config\models.yaml';
    if not FileExists(modelsConfig) then
    begin
      ForceDirectories(dataDir + '\config');
      oldModels := ExpandConstant('{app}\engine\config\models.yaml');
      if not FileExists(oldModels) then
      begin
        ExtractTemporaryFile('nlcode-default-models.yaml');
        oldModels := ExpandConstant('{tmp}\nlcode-default-models.yaml');
      end;
      if not FileCopy(oldModels, modelsConfig, True) then
        RaiseException('Impossibile inizializzare la configurazione modelli nella cartella dati.');
    end;
    Exit;
  end;
  if CurStep <> ssPostInstall then
    Exit;
  dataDir := Canonical(DataPage.Values[0]);
  cacheDir := dataDir + '\cache';
  workspaceDir := dataDir + '\workspace';
  modelsConfig := dataDir + '\config\models.yaml';
  ForceDirectories(dataDir);
  ForceDirectories(cacheDir);
  ForceDirectories(workspaceDir);
  if not FileExists(dataDir + '\user-data\User\settings.json') then
  begin
    ForceDirectories(dataDir + '\user-data\User');
    ExtractTemporaryFile('nlcode-default-settings.json');
    if not FileCopy(ExpandConstant('{tmp}\nlcode-default-settings.json'),
      dataDir + '\user-data\User\settings.json', True) then
      RaiseException('Impossibile inizializzare le impostazioni NL Code.');
  end;
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
  RemoveDir(ExpandConstant('{app}\data'));
  batch := '@echo off' + #13#10 +
    'setlocal' + #13#10 +
    'set "NLCODE_ROOT=%~dp0"' + #13#10 +
    'set "NLCODE_ENGINE_ROOT=%~dp0engine"' + #13#10 +
    'set "NL_ENGINE_ROOT=%NLCODE_ENGINE_ROOT%"' + #13#10 +
    'set "ELECTRON_RUN_AS_NODE="' + #13#10 +
    'set "PYTHONDONTWRITEBYTECODE=1"' + #13#10 +
    'set "NL_DATA_DIR=' + dataDir + '"' + #13#10 +
    'set "NL_WORKSPACE_DIR=' + workspaceDir + '"' + #13#10 +
    'set "NL_CACHE_DIR=' + cacheDir + '"' + #13#10 +
    'set "NL_MODELS_CONFIG=' + modelsConfig + '"' + #13#10 +
    'if not exist "%NL_DATA_DIR%" mkdir "%NL_DATA_DIR%"' + #13#10 +
    'if not exist "%NL_WORKSPACE_DIR%" mkdir "%NL_WORKSPACE_DIR%"' + #13#10 +
    'start "" "%~dp0NL Code.exe" --user-data-dir="' + dataDir + '\user-data" --extensions-dir="' + dataDir + '\extensions" %*' + #13#10;
  WriteText(ExpandConstant('{app}\NL Code Installed.cmd'), batch);
  ExtractTemporaryFile('NL-Coder.vsix');
  cliArgs := '"' + ExpandConstant('{app}\resources\app\out\cli.js') +
    '" --install-extension "' + ExpandConstant('{tmp}\NL-Coder.vsix') +
    '" --extensions-dir "' + GetExtensionsDir('') + '" --user-data-dir "' +
    dataDir + '\user-data" --force';
  oldElectron := GetEnv('ELECTRON_RUN_AS_NODE');
  SetEnvironment('ELECTRON_RUN_AS_NODE', '1');
  try
    if not Exec(ExpandConstant('{app}\NL Code.exe'), cliArgs,
      ExpandConstant('{app}'), SW_HIDE, ewWaitUntilTerminated, cliExit) then
      RaiseException('Impossibile registrare NL Coder.')
    else if cliExit <> 0 then
      RaiseException('Registrazione NL Coder fallita: ' + IntToStr(cliExit));
  finally
    SetEnvironment('ELECTRON_RUN_AS_NODE', oldElectron);
  end;
end;

function InitializeUninstall(): Boolean;
var
  dataDir, registeredApp: String;
begin
  Result := True;
  RemoveData := False;
  SavedDataDir := '';
  if RegQueryStringValue(HKA, 'Software\NL Code', 'DataDir', dataDir) then
    SavedDataDir := dataDir;
  if (SavedDataDir = '') or
    not RegQueryStringValue(HKA, 'Software\NL Code', 'InstallDir', registeredApp) or
    (CompareText(Canonical(registeredApp), Canonical(ExpandConstant('{app}'))) <> 0) or
    InvalidRoots(ExpandConstant('{app}'), SavedDataDir) or
    ReparseBelow(ExpandConstant('{app}')) or
    (DirExists(SavedDataDir) and ReparseBelow(SavedDataDir)) then
  begin
    Result := False;
    Log('Uninstall refused before file removal: installation identity or path checks failed.');
    if not UninstallSilent then
      MsgBox('Disinstallazione interrotta: percorsi modificati o collegamenti esterni. Controlla cartella applicazione e dati prima di riprovare.', mbError, MB_OK);
    Exit;
  end;
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
  owner: AnsiString;
begin
  if CurUninstallStep <> usPostUninstall then
    Exit;
  appDir := ExpandConstant('{app}');
  // Generated configuration/launcher and runtime caches are not tracked as
  // installer files; remove them explicitly so uninstall leaves no app residue.
  DeleteFile(appDir + '\install-config.json');
  DeleteFile(appDir + '\NL Code Installed.cmd');
  RemoveDir(appDir + '\data');
  RemoveDir(appDir + '\resources\app');
  RemoveDir(appDir + '\resources');
  RemoveDir(appDir);
  if (not RemoveData) or (SavedDataDir = '') then
    Exit;
  if InvalidRoots(appDir, SavedDataDir) then
    Exit;
  if not LoadStringFromFile(SavedDataDir + '\.nl-code-data-owner', owner) or
    (String(owner) <> OwnershipText(SavedDataDir)) or ReparseBelow(SavedDataDir) then
  begin
    Log('Data removal skipped: directory ownership or reparse checks failed.');
    if not UninstallSilent then
      MsgBox('La cartella dati e stata conservata: contiene dati preesistenti o collegamenti esterni. Percorso: ' + SavedDataDir,
        mbInformation, MB_OK);
    Exit;
  end;
  DelTree(SavedDataDir, True, True, True);
end;
