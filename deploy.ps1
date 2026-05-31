# CTM deploy.ps1
$ROOT = "C:\Users\ABC\med_sales_app\sales_app"
$ErrorActionPreference = "Continue"

$GITHUB_OWNER = "shoji-dot"
$GITHUB_REPO  = "CTM-"
$APP_VERSION  = "1.0.0"
$VENV_PYTHON  = "$ROOT\venv\Scripts\python.exe"
$VENV_PIP     = "$ROOT\venv\Scripts\pip.exe"

$TOKEN_FILE = "$env:USERPROFILE\.ctm_github_token"
if (Test-Path $TOKEN_FILE) {
    $GITHUB_TOKEN = (Get-Content $TOKEN_FILE -Raw).Trim()
    Write-Host "Token: saved token OK"
} else {
    Write-Host "GitHub Token ga hitsuyou desu."
    $GITHUB_TOKEN = Read-Host "Token"
    Set-Content $TOKEN_FILE $GITHUB_TOKEN
    Write-Host "Token saved."
}

$headers = @{
    Authorization = "token $GITHUB_TOKEN"
    Accept        = "application/vnd.github.v3+json"
}

Write-Host "--- Step 1: GitHub push ---"
Set-Location $ROOT

if (-not (Test-Path ".git")) {
    git init
    git remote add origin "https://$GITHUB_TOKEN@github.com/$GITHUB_OWNER/$GITHUB_REPO.git"
} else {
    git remote set-url origin "https://$GITHUB_TOKEN@github.com/$GITHUB_OWNER/$GITHUB_REPO.git"
}

if (-not (Test-Path ".gitignore")) {
    $lines = @("__pycache__/","*.pyc","venv/","dist/","build/","installer_output/","*.db-shm","*.db-wal","*.db.bak*",".ctm_github_token")
    $lines | Set-Content ".gitignore"
}

git config user.email "esw218@gmail.com"
git config user.name "shoji-dot"
git add .
$commitResult = git commit -m "v$APP_VERSION" 2>&1
Write-Host $commitResult
git branch -M main
git push -u origin main --force
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: git push failed."
    Read-Host "Press Enter to exit"
    exit 1
}
Write-Host "--- Step 1 done ---"

Write-Host "--- Step 2: PyInstaller build ---"
Set-Location $ROOT

if (-not (Test-Path $VENV_PIP)) {
    Write-Host "ERROR: venv not found."
    Read-Host "Press Enter to exit"
    exit 1
}

& $VENV_PIP install pyinstaller pystray pillow --quiet
& $VENV_PYTHON -m PyInstaller "$ROOT\app.spec" --clean --noconfirm
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: build failed."
    Read-Host "Press Enter to exit"
    exit 1
}
Write-Host "--- Step 2 done ---"

Write-Host "--- Step 3: Inno Setup ---"
$ISCC = "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
if (-not (Test-Path $ISCC)) { $ISCC = "C:\Program Files (x86)\Inno Setup 7\ISCC.exe" }
if (-not (Test-Path $ISCC)) { $ISCC = "C:\Program Files\Inno Setup 6\ISCC.exe" }
if (-not (Test-Path $ISCC)) { $ISCC = "C:\Program Files\Inno Setup 7\ISCC.exe" }
if (-not (Test-Path $ISCC)) {
    Write-Host "SKIP: Inno Setup not installed -> https://jrsoftware.org/isdl.php"
    Read-Host "Press Enter to exit"
    exit 0
}

& $ISCC "$ROOT\setup.iss"
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Inno Setup failed."
    Read-Host "Press Enter to exit"
    exit 1
}

$INSTALLER = "$ROOT\installer_output\CTM販売管理_v${APP_VERSION}_installer.exe"
if (-not (Test-Path $INSTALLER)) {
    Write-Host "ERROR: installer not found: $INSTALLER"
    Read-Host "Press Enter to exit"
    exit 1
}
Write-Host "--- Step 3 done ---"

Write-Host "--- Step 4: GitHub Releases ---"
$TAG = "v$APP_VERSION"
$RELEASE_API = "https://api.github.com/repos/$GITHUB_OWNER/$GITHUB_REPO/releases"

try {
    $existing = Invoke-RestMethod -Uri "$RELEASE_API/tags/$TAG" -Headers $headers -Method Get -ErrorAction SilentlyContinue
    if ($existing.id) {
        Invoke-RestMethod -Uri "$RELEASE_API/$($existing.id)" -Headers $headers -Method Delete | Out-Null
        Write-Host "Deleted existing release $TAG"
    }
} catch {}

$tagVal = $TAG
$verVal = $APP_VERSION
$body = "{`"tag_name`":`"$tagVal`",`"name`":`"CTM $tagVal`",`"body`":`"v$verVal`",`"draft`":false,`"prerelease`":false}"
$release = Invoke-RestMethod -Uri $RELEASE_API -Headers $headers -Method Post -Body $body -ContentType "application/json"
Write-Host "Release created: $TAG"

$upload_url = $release.upload_url.Split("{")[0]
$file_bytes = [System.IO.File]::ReadAllBytes((Resolve-Path $INSTALLER))
$upload_headers = @{ Authorization = "token $GITHUB_TOKEN"; "Content-Type" = "application/octet-stream" }
$file_name = [System.IO.Path]::GetFileName($INSTALLER)
Invoke-RestMethod -Uri "${upload_url}?name=$file_name" -Headers $upload_headers -Method Post -Body $file_bytes | Out-Null
Write-Host "Upload done: $file_name"

Write-Host "======================================"
Write-Host "Done! URL:"
Write-Host "https://github.com/$GITHUB_OWNER/$GITHUB_REPO/releases/latest"
Write-Host "======================================"
Read-Host "Press Enter to close"
