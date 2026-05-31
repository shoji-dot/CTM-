@echo off
chcp 65001 > nul
echo ========================================
echo  CTM販売管理システム ビルドスクリプト
echo ========================================

REM ★ venv のパスを確認して変更してください
set VENV_PYTHON=venv\Scripts\python.exe
set VENV_PIP=venv\Scripts\pip.exe

REM venv が存在するか確認
if not exist %VENV_PYTHON% (
    echo [ERROR] venv が見つかりません。
    echo 以下を実行して venv を作成してください:
    echo   python -m venv venv
    echo   venv\Scripts\pip install -r requirements.txt
    pause
    exit /b 1
)

echo [1/4] 依存パッケージを確認中...
%VENV_PIP% install pyinstaller pystray pillow --quiet
if errorlevel 1 goto error

echo [2/4] PyInstaller でビルド中...
venv\Scripts\pyinstaller app.spec --clean --noconfirm
if errorlevel 1 goto error

echo [3/4] ビルド成功！
echo 出力先: dist\CTM販売管理\

REM Inno Setup がインストールされていれば自動でインストーラー生成
set INNO="C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
if exist %INNO% (
    echo [4/4] Inno Setup でインストーラーを生成中...
    %INNO% setup.iss
    if errorlevel 1 goto error
    echo インストーラー出力先: installer_output\
) else (
    echo [4/4] Inno Setup が見つかりません。スキップします。
    echo インストーラーを作成するには:
    echo   https://jrsoftware.org/isdl.php からInno Setup 6をインストール後
    echo   ISCC.exe setup.iss を実行してください。
)

echo.
echo ========================================
echo  ビルド完了！
echo ========================================
pause
exit /b 0

:error
echo.
echo [ERROR] ビルドに失敗しました。上のエラーメッセージを確認してください。
pause
exit /b 1
