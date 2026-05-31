# migrate_notifications_fix.py
# notifications テーブルに message/link カラムを追加し、
# document_id の NOT NULL 制約を解除するマイグレーションスクリプト
#
# 実行方法:
#   venv\Scripts\activate
#   python migrate_notifications_fix.py
import sqlite3
import shutil
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent / "sales_app.db"
BACKUP_PATH = Path(__file__).parent / f"sales_app.db.bak_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

def main():
    if not DB_PATH.exists():
        print(f"ERROR: {DB_PATH} が見つかりません")
        return

    # バックアップ
    shutil.copy2(DB_PATH, BACKUP_PATH)
    print(f"✓ バックアップ作成: {BACKUP_PATH.name}")

    con = sqlite3.connect(str(DB_PATH))
    cur = con.cursor()

    # 整合性チェック
    result = cur.execute("PRAGMA integrity_check").fetchone()
    if result[0] != "ok":
        print(f"ERROR: DB整合性エラー: {result[0]}")
        con.close()
        return
    print("✓ DB整合性チェック: OK")

    # 現在のカラム確認
    cur.execute("PRAGMA table_info(notifications)")
    cols_info = cur.fetchall()
    cols = [r[1] for r in cols_info]
    print(f"現在のカラム: {cols}")

    changed = False

    # ① message カラム追加
    if "message" not in cols:
        cur.execute("ALTER TABLE notifications ADD COLUMN message TEXT DEFAULT ''")
        print("✓ message カラム追加")
        changed = True
    else:
        print("- message カラムは既存")

    # ② link カラム追加
    if "link" not in cols:
        cur.execute("ALTER TABLE notifications ADD COLUMN link TEXT DEFAULT ''")
        print("✓ link カラム追加")
        changed = True
    else:
        print("- link カラムは既存")

    # ③ document_id の NOT NULL 制約を解除（テーブル再作成）
    cur.execute("PRAGMA table_info(notifications)")
    info = cur.fetchall()
    doc_col = next((r for r in info if r[1] == "document_id"), None)
    if doc_col and doc_col[3] == 1:  # notnull=1
        print("document_id の NOT NULL 制約を解除します...")
        cur.execute("PRAGMA foreign_keys=OFF")
        cur.execute("""
            CREATE TABLE notifications_new (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                document_id   INTEGER,
                recipient_id  INTEGER NOT NULL,
                type          TEXT NOT NULL,
                is_sent       INTEGER DEFAULT 0,
                sent_at       TEXT,
                created_at    TEXT DEFAULT (datetime('now','localtime')),
                resource_type TEXT,
                resource_id   INTEGER,
                message       TEXT DEFAULT '',
                link          TEXT DEFAULT ''
            )
        """)
        cur.execute("""
            INSERT INTO notifications_new
                (id, document_id, recipient_id, type, is_sent, sent_at,
                 created_at, resource_type, resource_id, message, link)
            SELECT
                id, document_id, recipient_id, type, is_sent, sent_at,
                created_at, resource_type, resource_id,
                COALESCE(message, ''), COALESCE(link, '')
            FROM notifications
        """)
        cur.execute("DROP TABLE notifications")
        cur.execute("ALTER TABLE notifications_new RENAME TO notifications")
        cur.execute("PRAGMA foreign_keys=ON")
        print("✓ document_id NOT NULL 解除完了")
        changed = True
    else:
        print("- document_id は既に nullable")

    if changed:
        con.commit()
        print("\n✓ コミット完了")

    # 最終確認
    cur.execute("PRAGMA table_info(notifications)")
    print("\n--- 修正後の notifications カラム ---")
    for r in cur.fetchall():
        flag = "NOT NULL" if r[3] else "nullable"
        print(f"  {r[1]:<20s} [{flag}]")

    # 再度整合性チェック
    result = cur.execute("PRAGMA integrity_check").fetchone()
    print(f"\n最終整合性チェック: {result[0]}")

    con.close()
    print("\n✅ マイグレーション完了！アプリを再起動してください。")

if __name__ == "__main__":
    main()
