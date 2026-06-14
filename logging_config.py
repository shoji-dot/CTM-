"""
logging_config.py
─────────────────
アプリ全体の logging 設定を一元管理する。

使い方:
    from logging_config import get_logger
    logger = get_logger(__name__)

ログレベル（環境変数 LOG_LEVEL で制御、デフォルト INFO）:
    DEBUG   - 詳細なデバッグ情報
    INFO    - 通常の動作ログ
    WARNING - 軽微な異常（処理は継続）
    ERROR   - エラー（処理は継続）
    CRITICAL - 致命的なエラー（処理停止の可能性）

Railway では stdout に出力されたログが自動収集される。
"""

import logging
import os
import sys

_configured = False


def setup_logging() -> None:
    """アプリ起動時に一度だけ呼び出す。"""
    global _configured
    if _configured:
        return
    _configured = True

    level_name = os.environ.get("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    fmt = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(fmt)

    root = logging.getLogger()
    root.setLevel(level)

    # 既存ハンドラを削除して重複出力を防ぐ
    root.handlers.clear()
    root.addHandler(handler)

    # 外部ライブラリの冗長ログを抑制
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("apscheduler").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """モジュールごとのロガーを取得する。"""
    return logging.getLogger(name)
