# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec ファイル
# 使い方: pyinstaller app.spec

import os
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# ★ プロジェクトルートのパス（このspecファイルと同じ場所を想定）
PROJECT_ROOT = os.path.dirname(os.path.abspath(SPEC))

# --- バンドルに含めるデータファイル ---
datas = [
    # 静的ファイル (static/) をそのまま同梱
    (os.path.join(PROJECT_ROOT, "static"), "static"),
    # テンプレート (templates/) がある場合
    (os.path.join(PROJECT_ROOT, "templates"), "templates"),
    # ★ 他にデータフォルダがあれば追加
    # (os.path.join(PROJECT_ROOT, "uploads"), "uploads"),
]

# SQLite DBはデータフォルダに分離するため同梱しない
# （インストーラーが初回起動時に生成する）

# --- FastAPI / Uvicorn 関連の隠しインポート ---
hiddenimports = [
    "uvicorn",
    "uvicorn.loops",
    "uvicorn.loops.auto",
    "uvicorn.protocols",
    "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan",
    "uvicorn.lifespan.on",
    "fastapi",
    "fastapi.middleware",
    "fastapi.middleware.cors",
    "starlette",
    "starlette.staticfiles",
    "starlette.templating",
    "aiosqlite",
    "sqlalchemy",
    "sqlalchemy.dialects.sqlite",
    "pystray",
    "PIL",
    "PIL._imagingtk",
    "email.mime.multipart",
    "email.mime.text",
]

a = Analysis(
    ["launcher.py"],           # ★ エントリーポイント
    pathex=[PROJECT_ROOT],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "numpy", "pandas"],  # 不要なものを除外してサイズ削減
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="CTM販売管理",           # ★ exeファイル名
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,              # コンソールウィンドウを非表示
    disable_windowed_traceback=False,
    argv_emulation=False,
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="CTM販売管理",           # dist/ 以下のフォルダ名
)
