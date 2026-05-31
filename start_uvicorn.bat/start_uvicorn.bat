@echo off
cd /d %~dp0
if not exist venv\Scripts\uvicorn.exe (
    echo [ERROR] venv が見つかりません。先に以下を実行してください:
    echo   python -m venv venv
    echo   venv\Scripts\pip install -r requirements.txt
    pause
    exit /b 1
)
echo サーバーを起動中... http://localhost:8001
venv\Scripts\uvicorn.exe main:app --host 0.0.0.0 --port 8001
