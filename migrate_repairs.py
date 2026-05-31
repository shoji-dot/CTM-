# migrate_repairs.py
# repairs テーブルを追加するマイグレーションスクリプト
#
# 実行方法:
#   venv\Scripts\activate
#   python migrate_repairs.py
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

    shutil.copy2(DB_PATH, BACKUP_PATH)
    print(f"✓ バックアップ作成: {BACKUP_PATH.name}")

    con = sqlite3.connect(str(DB_PATH))
    cur = con.cursor()

    result = cur.execute("PRAGMA integrity_check").fetchone()
    if result[0] != "ok":
        print(f"ERROR: DB整合性エラー: {result[0]}")
        con.close()
        return
    print("✓ DB整合性チェック: OK")

    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='repairs'")
    if cur.fetchone():
        print("- repairs テーブルは既存。スキップします。")
        con.close()
        return

    cur.executescript("""
        CREATE TABLE repairs (
            id                          INTEGER PRIMARY KEY AUTOINCREMENT,
            repair_number               TEXT UNIQUE NOT NULL,
            customer_id                 INTEGER NOT NULL,
            end_user_id                 INTEGER,
            product_id                  INTEGER NOT NULL,
            serial_number               TEXT,
            lot_number                  TEXT,
            fault_description           TEXT NOT NULL,
            received_date               DATE NOT NULL,
            replacement_shipment_id     INTEGER,
            status                      TEXT NOT NULL DEFAULT 'received',
            inspection_date             DATE,
            inspection_result           TEXT,
            inspector                   TEXT,
            sent_to_maker_date          DATE,
            maker_response              TEXT,
            maker_response_date         DATE,
            maker_quote_amount          REAL,
            maker_response_note         TEXT,
            quote_id                    INTEGER,
            quote_submitted_date        DATE,
            repair_ordered_date         DATE,
            repair_completed_date       DATE,
            delivery_type               TEXT,
            delivery_address            TEXT,
            replacement_returned_date   DATE,
            closed_date                 DATE,
            notes                       TEXT,
            staff_name                  TEXT,
            created_at                  DATETIME DEFAULT (datetime('now','localtime')),
            updated_at                  DATETIME DEFAULT (datetime('now','localtime'))
        );
    """)
    con.commit()
    print("✓ repairs テーブル作成完了")

    cur.execute("PRAGMA integrity_check")
    print(f"最終整合性チェック: {cur.fetchone()[0]}")
    con.close()
    print("\n✅ マイグレーション完了！アプリを再起動してください。")

if __name__ == "__main__":
    main()
