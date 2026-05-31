# CTM販売管理システム — Windowsアプリ配布ガイド

## 全体の流れ

```
開発PC でビルド → installer.exe を GitHub Releases にアップ → 同僚がダウンロード・インストール
                                                              ↑ 更新時も同じ
```

---

## Step 1: 事前準備（初回のみ）

### 1-1. 必要ツールのインストール

| ツール | 用途 | URL |
|---|---|---|
| Inno Setup 6 | インストーラー生成 | https://jrsoftware.org/isdl.php |
| Git | バージョン管理 | https://git-scm.com/ |
| GitHubアカウント | リリース配布 | https://github.com/ |

### 1-2. GitHubリポジトリを作成

1. GitHub で新しいリポジトリを作成（プライベートでOK）
2. `update_checker.py` の以下を自分のリポジトリ情報に変更:
   ```python
   GITHUB_OWNER = "your-github-username"   # ← GitHubユーザー名
   GITHUB_REPO  = "ctm-sales-app"          # ← リポジトリ名
   ```

### 1-3. プロジェクトに追加するファイル

以下のファイルを `C:\Users\ABC\med_sales_app\sales_app\` にコピー:

```
sales_app/
├── launcher.py          ← コピー
├── app.spec             ← コピー（★ パスを確認）
├── setup.iss            ← コピー（★ GUIDを生成して置換）
├── build.bat            ← コピー
├── update_checker.py    ← コピー
└── main.py              （既存）
```

### 1-4. main.py に更新チェッカーを追加

`main.py` に以下を追記:
```python
from update_checker import router as update_router
app.include_router(update_router)
```

### 1-5. launcher.py のパス確認

`launcher.py` の以下を確認・修正:
```python
APP_MODULE = "main:app"   # FastAPIのモジュール名:appオブジェクト名
PORT = 8000               # 使用ポート
```

### 1-6. app.spec のパス確認

`app.spec` の `datas` セクションで、実際に存在するフォルダを確認:
```python
datas = [
    ("static", "static"),       # ← static フォルダがある場合
    ("templates", "templates"), # ← templates フォルダがある場合
]
```

---

## Step 2: Inno Setup の GUID を生成

`setup.iss` の `AppId` に一意のGUIDを設定（重要！）:

PowerShell で生成:
```powershell
[System.Guid]::NewGuid().ToString()
```

出力例: `a1b2c3d4-e5f6-7890-abcd-ef1234567890`

`setup.iss` の以下を置換（`{` `}` を忘れずに）:
```
AppId={{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}}
```
※ `[Code]` セクション内の同じGUIDも同じ値に変更すること

---

## Step 3: ビルド実行

```
sales_app\ フォルダで build.bat をダブルクリック
```

成功すると:
- `dist\CTM販売管理\` にアプリファイル一式が生成される
- `installer_output\CTM販売管理_v1.0.0_installer.exe` が生成される

---

## Step 4: GitHub Releases にアップロード

1. GitHub リポジトリ → **Releases** → **Create a new release**
2. タグ: `v1.0.0`（`setup.iss` の `AppVersion` と一致させる）
3. `installer_output\CTM販売管理_v1.0.0_installer.exe` をアタッチ
4. **Publish release**

---

## Step 5: 同僚への配布

GitHub Releases の URL を共有するだけ:
```
https://github.com/[ユーザー名]/[リポジトリ名]/releases/latest
```

同僚はインストーラーをダウンロードしてダブルクリックするだけでOK。

---

## Step 6: アップデートの手順（バグ修正・機能追加時）

1. `update_checker.py` の `CURRENT_VERSION` を更新（例: `"1.0.1"`）
2. `setup.iss` の `AppVersion` を同じ値に更新
3. `build.bat` を実行
4. GitHub に新しい Release を作成（タグ: `v1.0.1`）
5. 新しいインストーラーをアタッチ

→ 同僚がアプリを起動すると「アップデートがあります」と通知が表示される

---

## トラブルシューティング

### ビルドエラー「ModuleNotFoundError」
`app.spec` の `hiddenimports` に不足しているモジュールを追加してください。

### ビルドしたexeが起動しない
```
dist\CTM販売管理\CTM販売管理.exe を コマンドプロンプトから実行してエラーを確認
```
`launcher.py` の `APP_MODULE` や `PORT` を見直す。

### 静的ファイルが表示されない
`app.spec` の `datas` でフォルダパスが正しいか確認。

### アップデート通知が出ない
- GitHubリポジトリが公開（Public）になっているか確認
- `update_checker.py` の `GITHUB_OWNER` / `GITHUB_REPO` が正しいか確認
- プライベートリポジトリの場合は GitHub Token が必要（要カスタマイズ）
