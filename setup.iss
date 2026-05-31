; Inno Setup スクリプト
; Inno Setup 6.x 以上が必要: https://jrsoftware.org/isdl.php
;
; ★ マーク箇所をプロジェクトに合わせて修正してください

#define AppName "CTM販売管理システム"
#define AppVersion "1.0.0"          ; ★ バージョン（リリース時に更新）
#define AppPublisher "CTM"           ; ★ 会社名・チーム名
#define AppExeName "CTM販売管理.exe"
#define SourceDir "dist\CTM販売管理" ; PyInstallerのCOLLECT出力先

[Setup]
AppId={{B2477E22-24BC-4BBE-9BB9-73C25A98340F}}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
OutputDir=installer_output
OutputBaseFilename=CTM販売管理_v{#AppVersion}_installer
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
; アンインストール時にデータフォルダを保持する
UninstallDisplayName={#AppName}
; 管理者権限不要でインストール可能（同僚PCへの配布を想定）
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog

[Languages]
Name: "japanese"; MessagesFile: "compiler:Languages\Japanese.isl"

[Tasks]
Name: "desktopicon"; Description: "デスクトップにショートカットを作成"; GroupDescription: "追加タスク:"
Name: "startupicon"; Description: "Windows起動時に自動起動"; GroupDescription: "追加タスク:"

[Files]
; PyInstallerの出力フォルダ全体を同梱
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{group}\{#AppName} をアンインストール"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon
Name: "{userstartup}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: startupicon

[Run]
; インストール後に即起動するオプション
Filename: "{app}\{#AppExeName}"; Description: "インストール後に起動"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; アンインストール時にdataフォルダは削除しない（DBデータ保護）
; 削除したい場合は以下のコメントを外す
; Type: filesandordirs; Name: "{app}\data"

[Code]
// バージョンチェック：古いバージョンが入っている場合は先にアンインストール
function InitializeSetup(): Boolean;
var
  UninstallString: String;
  ResultCode: Integer;
begin
  Result := True;
  if RegQueryStringValue(HKCU, 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{B2477E22-24BC-4BBE-9BB9-73C25A98340F}_is1',
    'UninstallString', UninstallString) then
  begin
    if MsgBox('前のバージョンがインストールされています。アップデートしますか？',
      mbConfirmation, MB_YESNO) = IDYES then
    begin
      Exec(RemoveQuotes(UninstallString), '/SILENT', '', SW_SHOW, ewWaitUntilTerminated, ResultCode);
    end;
  end;
end;
