"""
backup_service.py
─────────────────
PostgreSQL / SQLite のバックアップを実行し、Dropbox にアップロードする。
pg_dump 不要、psycopg2 で純Python実装。

スケジュール: main.py の lifespan で毎日 02:00 JST に呼び出す。
手動実行:     /api/admin/backup  (POST, admin only)
"""

import os
import logging
import gzip
import shutil
import tarfile
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


# ── PostgreSQL バックアップ（psycopg2 純Python）───────────────────────

def _val_to_sql(v) -> str:
    """Python値を SQL リテラルに変換する。"""
    if v is None:
        return "NULL"
    if isinstance(v, bool):
        return "TRUE" if v else "FALSE"
    if isinstance(v, (int, float)):
        return str(v)
    if isinstance(v, datetime):
        return f"\'{v.isoformat()}\'"
    escaped = str(v).replace("\\", "\\\\").replace("\'", "\'\'"  )
    return f"\'{escaped}\'"


def _backup_postgres(db_url: str) -> "Path | None":
    """psycopg2 で全テーブルの INSERT ステートメントを生成して .sql.gz で保存。"""
    ts = _now_jst().strftime("%Y%m%d_%H%M%S")
    dest = BACKUP_DIR / f"backup_{ts}.sql.gz"
    try:
        import psycopg2
        conn = psycopg2.connect(db_url)
        cur = conn.cursor()

        # public スキーマの全テーブル名を取得
        cur.execute("""
            SELECT tablename FROM pg_tables
            WHERE schemaname = 'public'
            ORDER BY tablename
        """)
        tables = [row[0] for row in cur.fetchall()]

        lines = [
            f"-- CTM販喲管理システム バックアップ",
            f"-- 生成日時: {_now_jst().isoformat()}",
            f"-- テーブル数: {len(tables)}",
            "",
        ]

        for table in tables:
            cur.execute(f'SELECT * FROM "{table}" LIMIT 0')
            cols = [desc[0] for desc in cur.description]
            cur.execute(f'SELECT * FROM "{table}"')
            rows = cur.fetchall()
            lines.append(f"-- [{table}] {len(rows)}行")
            if rows:
                col_list = ", ".join(f'"{c}"' for c in cols)
                for row in rows:
                    vals = ", ".join(_val_to_sql(v) for v in row)
                    lines.append(f'INSERT INTO "{table}" ({col_list}) VALUES ({vals});')
            lines.append("")

        conn.close()

        content = "\n".join(lines).encode("utf-8")
        with gzip.open(dest, "wb") as f:
            f.write(content)

        size_kb = dest.stat().st_size // 1024
        logger.info("[backup] PostgreSQL dump OK: %s (%d KB)", dest.name, size_kb)
        return dest

    except Exception as e:
        logger.error("[backup] PostgreSQL backup exception: %s", e, exc_info=True)
        return None


# ── SQLite バックアップ ───────────────────────────────────────────────

def _backup_sqlite() -> "Path | None":
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


# ── Dropbox アップロード ─────────────────────────────────────────────────────────

def _upload_to_dropbox(local_path: Path) -> bool:
    if not DROPBOX_TOKEN:
        logger.warning("[backup] DROPBOX_ACCESS_TOKEN 未設定のため Dropbox アップロードをスキップ")
        return False
    try:
        import dropbox
        dbx = dropbox.Dropbox(DROPBOX_TOKEN)
        remote = f"{DROPBOX_BACKUP_FOLDER}/{local_path.name}"
        with open(local_path, "rb") as f:
            dbx.files_upload(f.read(), remote, mode=dropbox.files.WriteMode.overwrite)
        logger.info("[backup] Dropbox upload OK: %s", remote)
        return True
    except Exception as e:
        logger.error("[backup] Dropbox upload failed: %s", e)
        return False



# ── uploads/ バックアップ ────────────────────────────────────────────────────────

UPLOADS_DIR = Path(__file__).parent / "uploads"

def _backup_uploads() -> "Path | None":
    """uploads/ ディレクトリを tar.gz にまとめて返す。"""
    if not UPLOADS_DIR.exists():
        logger.warning("[backup] uploads/ ディレクトリが見つかりません: %s", UPLOADS_DIR)
        return None
    ts = _now_jst().strftime("%Y%m%d_%H%M%S")
    dest = BACKUP_DIR / f"uploads_{ts}.tar.gz"
    try:
        with tarfile.open(dest, "w:gz") as tar:
            tar.add(UPLOADS_DIR, arcname="uploads")
        size_kb = dest.stat().st_size // 1024
        logger.info("[backup] uploads backup OK: %s (%d KB)", dest.name, size_kb)
        return dest
    except Exception as e:
        logger.error("[backup] uploads backup exception: %s", e, exc_info=True)
        return None


# ── 古いローカルバックアップを削除 ───────────────────────────────────────────────

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


# ── メイン実行関数 ───────────────────────────────────────────────────────────────

def run_backup() -> dict:
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

    # uploads/ のバックアップ（失敗してもメインの成否に影響しない）
    uploads_file = _backup_uploads()
    uploads_uploaded = False
    if uploads_file:
        uploads_uploaded = _upload_to_dropbox(uploads_file)
    else:
        logger.warning("[backup] uploads バックアップをスキップ")

    return {
        "success": True,
        "file": backup_file.name,
        "dropbox": uploaded,
        "uploads_file": uploads_file.name if uploads_file else None,
        "uploads_dropbox": uploads_uploaded,
    }
