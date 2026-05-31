@echo off
chcp 65001 > nul

:: バックアップ先フォルダ
set DEST=C:\Users\ABC\Dropbox\CTM 東海林\医療関係\事務用\販売管理バックアップ

:: バックアップ元DBファイル
set SRC=C:\Users\ABC\med_sales_app\sales_app\sales_app.db

:: 日付をPowerShellで取得（日本語Windowsでも確実に動く）
for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyy-MM-dd"') do set TODAY=%%i

set FILENAME=sales_app_%TODAY%.db
set DEST_FILE=%DEST%\%FILENAME%

echo =============================================
echo  販売管理DB バックアップ
echo =============================================
echo ソース : %SRC%
echo 保存先 : %DEST_FILE%
echo.

:: ソースファイル存在確認
if not exist "%SRC%" (
    echo [エラー] DBファイルが見つかりません:
    echo   %SRC%
    pause
    exit /b 1
)

:: バックアップ先フォルダが存在しなければ作成
if not exist "%DEST%" (
    echo バックアップ先フォルダを作成します...
    mkdir "%DEST%"
)

:: DBをコピー
copy /Y "%SRC%" "%DEST_FILE%"

if %ERRORLEVEL%==0 (
    echo.
    echo [成功] バックアップ完了: %FILENAME%
) else (
    echo.
    echo [エラー] コピーに失敗しました。
    pause
    exit /b 1
)

:: 30日以上前の古いバックアップを削除
echo 古いバックアップを整理中...
forfiles /P "%DEST%" /M "sales_app_*.db" /D -30 /C "cmd /c del @path" 2>nul

echo.
echo 完了しました。何かキーを押すと閉じます。
pause
