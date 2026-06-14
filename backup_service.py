"""
backup_service.py
─────────────────
PostgreSQL / SQLite のバックアップを実行し、Dropbox にアップロードする。

スケジュール: main.py の lifespan で毎日 02:00 JST に呼び出す。
手動実行:     /api/admin/backup  (POST, admin only)

環境変数:
  DATABASE_URL         - Railway が自動設定。なければ SQLite にフォールバック。
  DROPBOX_ACCESS_TOKEN - Dropbox へのアップロードに必要。未設定時はローカル保存のみ。
  BACKUP_RETENTION_DAYS - ローカルバックアップの保持日数（デフォルト 7 日）
"""

import os
import subprocess
import logging
import gzip
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

BACKUP_DIR = Path(__file__).parent / "backups"
BACKUP_DIR.mkdir(exist_ok=True)

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./sales_app.db")
DROPBOX_TOKEN = os.environ.get("DROPBOX_ACCESS_TOKEN", "")
DROPBOX_BACKUP_FOLDER = "/CTM_backups"
RETENTION_DAYS = int(os.environ.get("BACKUP_RETENTION_DAYS", "7"))


def _now_jst() -> datetime:
    return datetime.now(ZoneInfo("Asia/Tokyo"))


# ── PostgreSQL バックアップ ────────────────────────────────────────────────────

def _backup_postgres(db_url: str) -> Path | None:
    """pg_dump で .sql.gz を生成して返す。失敗時は None。"""
    ts = _now_jst().strftime("%Y%m%d_%H%M%S")
    dest = BACKUP_DIR / f"backup_{ts}.sql.gz"
    try:
        proc = subprocess.run(
            ["pg_dump", "--no-password", db_url],
            capture_output=True,
            timeout=120,
        )
        if proc.returncode != 0:
            logger.error("[backup] pg_dump failed: %s", proc.stderr.decode(errors="replace"))
            return None
        with gzip.open(dest, "wb") as f:
            f.write(proc.stdout)
        size_kb = dest.stat().st_size // 1024
        logger.info("[backup] PostgreSQL dump OK: %s (%d KB)", dest.name, size_kb)
        return dest
    except FileNotFoundError:
        logger.error("[backup] pg_dump コマンドが見つかりません。postgresql-client をインストールしてください。")
        return None
    except Exception as e:
        logger.error("[backup] pg_dump exception: %s", e)
        return None


# ── SQLite バックアップ ───────────────────────────────────────────────────────

def _backup_sqlite() -> Path | None:
    """SQLite ファイルを .db.gz にコピーして返す。"""
    db_path = Path(__file__).parent / "sales_app.db"
    if not db_path.exists():
        logger.warning("[backup] SQLite ファイルが見つかりません: %s", db_path)
        return None
    ts = _now_jst().strftime("%Y%m%d_%H%M%S")
    dest = BACKUP_DIR / f"backup_{ts}.db.gz"
    try:
        with open(db_path, "rb") as f_in, gzip.open(dest, "wb") as f_out:
            shutil.copyfileobj(f_in, f_out)
        size_kb = dest.stat().st_size // 1024
        logger.info("[backup] SQLite backup OK: %s (%d KB)", dest.name, size_kb)
        return dest
    except Exception as e:
        logger.error("[backup] SQLite backup exception: %s", e)
        return None


# ── Dropbox アップロード ──────────────────────────────────────────────────────

def _upload_to_dropbox(local_path: Path) -> bool:
    """バックアップファイルを Dropbox にアップロード。成功 True / 失敗 False。"""
    if not DROPBOX_TOKEN:
        logger.warning("[backup] DROPBOX_ACCESS_TOKEN 未設定のため Dropbox アップロードをスキップ")
        return False
    try:
        import dropbox
        dbx = dropbox.Dropbox(DROPBOX_TOKEN)
        remote = f"{DROPBOX_BACKUP_FOLDER}/{local_path.name}"
        with open(local_path, "rb") as f:
            dbx.files_upload(
                f.read(),
                remote,
                mode=dropbox.files.WriteMode.overwrite,
            )
        logger.info("[backup] Dropbox upload OK: %s", remote)
        return True
    except Exception as e:
        logger.error("[backup] Dropbox upload failed: %s", e)
        return False


# ── 古いローカルバックアップを削除 ────────────────────────────────────────────

def _purge_old_backups():
    cutoff = _now_jst() - timedelta(days=RETENTION_DAYS)
    for f in BACKUP_DIR.glob("backup_*"):
        try:
            mtime = datetime.fromtimestamp(f.stat().st_mtime, tz=ZoneInfo("Asia/Tokyo"))
            if mtime < cutoff:
                f.unlink()
                logger.info("[backup] 古いバックアップを削除: %s", f.name)
        except Exception as e:
            logger.warning("[backup] 削除失敗: %s (%s)", f.name, e)


# ── メイン実行関数 ────────────────────────────────────────────────────────────

def run_backup() -> dict:
    """
    バックアップを実行して結果を返す。
    Returns: {"success": bool, "file": str | None, "dropbox": bool}
    """
    logger.info("[backup] バックアップ開始")
    _purge_old_backups()

    if DATABASE_URL.startswith("postgresql"):
        backup_file = _backup_postgres(DATABASE_URL)
    else:
        backup_file = _backup_sqlite()

    if not backup_file:
        logger.error("[backup] バックアップファイルの生成に失敗しました")
        return {"success": False, "file": None, "dropbox": False}

    uploaded = _upload_to_dropbox(backup_file)
    return {
        "success": True,
        "file": backup_file.name,
        "dropbox": uploaded,
    }
