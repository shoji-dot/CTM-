$src  = "C:\Users\ABC\med_sales_app\sales_app\sales_app.db"
$dest = "C:\Users\ABC\Dropbox\CTM " + [char]0x6771 + [char]0x6D77 + [char]0x6797 + "\" + [char]0x533B + [char]0x7642 + [char]0x95A2 + [char]0x4FC2 + "\" + [char]0x4E8B + [char]0x52D9 + [char]0x7528 + "\" + [char]0x8CA9 + [char]0x58F2 + [char]0x7BA1 + [char]0x7406 + [char]0x30D0 + [char]0x30C3 + [char]0x30AF + [char]0x30A2 + [char]0x30C3 + [char]0x30D7

$today    = Get-Date -Format "yyyy-MM-dd"
$filename = "sales_app_$today.db"
$destFile = Join-Path $dest $filename

Write-Host "===== DB Backup =====" -ForegroundColor Cyan
Write-Host "Source : $src"
Write-Host "Dest   : $destFile"
Write-Host ""

if (-not (Test-Path $src)) {
    Write-Host "ERROR: DB file not found: $src" -ForegroundColor Red
    Read-Host "Press Enter to close"
    exit 1
}

if (-not (Test-Path $dest)) {
    New-Item -ItemType Directory -Path $dest | Out-Null
}

try {
    Copy-Item -Path $src -Destination $destFile -Force
    Write-Host "SUCCESS: $filename" -ForegroundColor Green
} catch {
    Write-Host "ERROR: $_" -ForegroundColor Red
    Read-Host "Press Enter to close"
    exit 1
}

Get-ChildItem -Path $dest -Filter "sales_app_*.db" | Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-30) } | Remove-Item -Force

Write-Host ""
Write-Host "Backup completed." -ForegroundColor Green
Read-Host "Press Enter to close"
