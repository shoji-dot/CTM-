"""
SQLite → PostgreSQL データ移行スクリプト
対象テーブル: announcements, document_types, documents,
              approval_flows, approval_steps, approval_logs,
              notifications, customer_memos, tasks, task_comments

使い方:
  DATABASE_URL=postgresql://... python migrate_sqlite_to_pg.py

注意:
  - 実行前にPostgreSQLのテーブルが空であること（重複スキップあり）
  - 外部キー依存のため挿入順序に注意（スクリプトが制御済み）
"""

import os
import sqlite3
import sys
from sqlalchemy import create_engine, text

SQLITE_PATH = os.path.join(os.path.dirname(__file__), 'sales_app.db')
PG_URL = os.environ.get("DATABASE_URL")

if not PG_URL:
    print("ERROR: DATABASE_URL 環境変数が設定されていません")
    sys.exit(1)

if PG_URL.startswith("postgres://"):
    PG_URL = PG_URL.replace("postgres://", "postgresql://", 1)

print(f"SQLite: {SQLITE_PATH}")
print(f"PostgreSQL: {PG_URL[:40]}...")

# 接続
sqlite_conn = sqlite3.connect(SQLITE_PATH, timeout=30)
sqlite_conn.row_factory = sqlite3.Row
pg_engine = create_engine(PG_URL, pool_pre_ping=True)

def migrate_table(table: str, columns: list[str], pk: str = "id"):
    """テーブルを SQLite → PostgreSQL へコピー（既存行はスキップ）"""
    rows = sqlite_conn.execute(f"SELECT * FROM {table} ORDER BY {pk}").fetchall()
    if not rows:
        print(f"  {table}: 0件（スキップ）")
        return

    col_str = ", ".join(columns)
    bind_str = ", ".join(f":{c}" for c in columns)
    inserted = 0
    skipped = 0

    with pg_engine.begin() as pg:
        for row in rows:
            data = {c: row[c] for c in columns if c in row.keys()}
            try:
                pg.execute(
                    text(f"INSERT INTO {table} ({col_str}) VALUES ({bind_str}) ON CONFLICT ({pk}) DO NOTHING"),
                    data
                )
                inserted += 1
            except Exception as e:
                print(f"  [{table}] 行スキップ id={row[pk]}: {e}")
                skipped += 1

        # シーケンスをリセット（PostgreSQL のみ）
        try:
            max_id = pg.execute(text(f"SELECT MAX({pk}) FROM {table}")).scalar() or 0
            pg.execute(text(f"SELECT setval(pg_get_serial_sequence('{table}', '{pk}'), :v, true)"), {"v": max_id})
        except Exception:
            pass  # pk が serial でない場合は無視

    print(f"  {table}: {inserted}件挿入, {skipped}件スキップ")


print("\n=== 移行開始 ===")

# 依存関係順に移行
migrate_table("document_types", ["id","name","description","is_active","created_at"])
migrate_table("documents", ["id","title","document_type_id","file_path","file_name",
                             "file_size","mime_type","status","uploaded_by","current_step",
                             "comment","created_at","updated_at"])
migrate_table("approval_flows", ["id","document_type_id","name","is_active","created_at"])
migrate_table("approval_steps", ["id","flow_id","step_order","step_name",
                                  "approver_id","approver_role","required_level","created_at"])
migrate_table("approval_logs", ["id","document_id","step_order","approver_id",
                                 "action","comment","created_at"])
migrate_table("announcements", ["id","title","body","author_id","is_pinned","created_at","updated_at"])
migrate_table("customer_memos", ["id","hospital","doctor_name","memo","staff_id","created_at","updated_at"])
migrate_table("tasks", ["id","title","description","status","priority",
                         "assignee_id","created_by","due_date","created_at","updated_at"])
migrate_table("task_comments", ["id","task_id","author_id","body","created_at"])
migrate_table("notifications", ["id","document_id","recipient_id","type","message","link",
                                 "resource_type","resource_id","is_sent","sent_at","created_at"])

print("\n=== 移行完了 ===")
sqlite_conn.close()
