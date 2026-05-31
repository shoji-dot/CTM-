"""
CTM販売管理システム ランチャー
PyInstallerでビルドする際のエントリーポイント。
uvicornをバックグラウンドスレッドで起動し、ブラウザを自動オープン。
システムトレイアイコンで常駐・終了を制御。
"""

import sys
import os
import time
import threading
import webbrowser
import subprocess

# PyInstallerバンドル時のベースパスを解決
if getattr(sys, 'frozen', False):
    BASE_DIR = sys._MEIPASS
    # データ保存先はexeと同階層（上書きインストールで消えないよう別パス）
    DATA_DIR = os.path.join(os.path.dirname(sys.executable), "data")
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    DATA_DIR = os.path.join(BASE_DIR, "data")

os.makedirs(DATA_DIR, exist_ok=True)

HOST = "127.0.0.1"
PORT = 8001
APP_MODULE = "main:app"


def start_server():
    """uvicornをサブプロセスで起動"""
    import uvicorn
    # カレントディレクトリをアプリのベースに設定
    os.chdir(BASE_DIR)
    uvicorn.run(
        APP_MODULE,
        host=HOST,
        port=PORT,
        log_level="warning",
    )


def wait_for_server(timeout=15):
    """サーバーが起動するまで待機"""
    import urllib.request
    url = f"http://{HOST}:{PORT}/"
    for _ in range(timeout * 2):
        try:
            urllib.request.urlopen(url, timeout=1)
            return True
        except Exception:
            time.sleep(0.5)
    return False


def run_with_tray():
    """システムトレイアイコン付きで実行"""
    try:
        import pystray
        from PIL import Image, ImageDraw

        # トレイアイコン画像を動的生成（アイコン画像がない場合のフォールバック）
        icon_path = os.path.join(BASE_DIR, "static", "favicon.ico")
        if os.path.exists(icon_path):
            image = Image.open(icon_path)
        else:
            image = Image.new("RGB", (64, 64), color=(0, 120, 212))
            draw = ImageDraw.Draw(image)
            draw.rectangle([16, 16, 48, 48], fill=(255, 255, 255))

        def on_open(_):
            webbrowser.open(f"http://{HOST}:{PORT}/")

        def on_quit(icon, _):
            icon.stop()
            os._exit(0)

        menu = pystray.Menu(
            pystray.MenuItem("ブラウザで開く", on_open),
            pystray.MenuItem("終了", on_quit),
        )
        icon = pystray.Icon("CTM販売管理", image, "CTM販売管理システム", menu)
        icon.run()

    except ImportError:
        # pystray未インストール時はシンプルなコンソール待機
        print("CTM販売管理システム 起動中... ブラウザで http://127.0.0.1:8001 を開いてください")
        print("終了するにはこのウィンドウを閉じてください")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass


def main():
    # サーバーをバックグラウンドスレッドで起動
    server_thread = threading.Thread(target=start_server, daemon=True)
    server_thread.start()

    # サーバー起動待機
    if wait_for_server():
        webbrowser.open(f"http://{HOST}:{PORT}/")
    else:
        print("サーバーの起動に失敗しました。ポート競合がないか確認してください。")

    # トレイアイコンで常駐
    run_with_tray()


if __name__ == "__main__":
    main()
