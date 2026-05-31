import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), 'sales_app.db')

def migrate():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # staffsテーブル拡張
    extend_staffs = [
        "ALTER TABLE staffs ADD COLUMN position TEXT",           # 役職
        "ALTER TABLE staffs ADD COLUMN approval_level INTEGER DEFAULT 0",  # 承認権限レベル
    ]
    for sql in extend_staffs:
        try:
            cur.execute(sql)
        except sqlite3.OperationalError:
            pass  # カラム追加済みはスキップ

    # ① ドキュメント種別マスタ
    cur.execute("""
    CREATE TABLE IF NOT EXISTS document_types (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,          -- 例: 売買契約書, NDA, 見積書
        description TEXT,
        is_active INTEGER DEFAULT 1,
        created_at TEXT DEFAULT (datetime('now', 'localtime'))
    )
    """)

    # ② ドキュメント
    cur.execute("""
    CREATE TABLE IF NOT EXISTS documents (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        document_type_id INTEGER NOT NULL REFERENCES document_types(id),
        file_path TEXT NOT NULL,
        file_name TEXT NOT NULL,
        file_size INTEGER,
        mime_type TEXT,
        status TEXT NOT NULL DEFAULT 'draft'
            CHECK(status IN ('draft','in_review','approved','rejected','revising')),
        uploaded_by INTEGER NOT NULL REFERENCES staffs(id),
        current_step INTEGER DEFAULT 0,     -- 現在の承認ステップ番号
        comment TEXT,                       -- 最新コメント
        created_at TEXT DEFAULT (datetime('now', 'localtime')),
        updated_at TEXT DEFAULT (datetime('now', 'localtime'))
    )
    """)

    # ③ 承認フロー定義（ドキュメント種別ごと）
    cur.execute("""
    CREATE TABLE IF NOT EXISTS approval_flows (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        document_type_id INTEGER NOT NULL REFERENCES document_types(id),
        name TEXT NOT NULL,                 -- フロー名（例: 標準承認ルート）
        is_active INTEGER DEFAULT 1,
        created_at TEXT DEFAULT (datetime('now', 'localtime'))
    )
    """)

    # ④ 承認ステップ（フローの各ステップ）
    cur.execute("""
    CREATE TABLE IF NOT EXISTS approval_steps (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        flow_id INTEGER NOT NULL REFERENCES approval_flows(id),
        step_order INTEGER NOT NULL,        -- ステップ順序（1, 2, 3...）
        step_name TEXT NOT NULL,            -- 例: 担当者確認, 課長承認, 部長承認
        approver_id INTEGER REFERENCES staffs(id),       -- 特定の承認者
        approver_role TEXT,                 -- 役職ベース割当（例: 部長）※approver_idがNULLの場合
        required_level INTEGER DEFAULT 0,  -- 必要な承認権限レベル
        created_at TEXT DEFAULT (datetime('now', 'localtime'))
    )
    """)

    # ⑤ 承認ログ（誰が・いつ・何をしたか）
    cur.execute("""
    CREATE TABLE IF NOT EXISTS approval_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        document_id INTEGER NOT NULL REFERENCES documents(id),
        step_order INTEGER NOT NULL,
        approver_id INTEGER NOT NULL REFERENCES staffs(id),
        action TEXT NOT NULL
            CHECK(action IN ('approved','rejected','commented','submitted','revise_submitted')),
        comment TEXT,
        created_at TEXT DEFAULT (datetime('now', 'localtime'))
    )
    """)

    # ⑥ 通知
    cur.execute("""
    CREATE TABLE IF NOT EXISTS notifications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        document_id INTEGER NOT NULL REFERENCES documents(id),
        recipient_id INTEGER NOT NULL REFERENCES staffs(id),
        type TEXT NOT NULL
            CHECK(type IN ('approval_request','rejected','approved','reminder')),
        is_sent INTEGER DEFAULT 0,
        sent_at TEXT,
        created_at TEXT DEFAULT (datetime('now', 'localtime'))
    )
    """)

    # 初期データ：ドキュメント種別
    initial_types = [
        ('売買契約書', '製品の売買に関する契約書'),
        ('NDA', '秘密保持契約書'),
        ('見積書', '顧客向け見積書'),
    ]
    for name, desc in initial_types:
        cur.execute("""
            INSERT OR IGNORE INTO document_types (name, description) VALUES (?, ?)
        """, (name, desc))

    conn.commit()
    conn.close()
    print("✅ マイグレーション完了")
    print("追加テーブル: document_types, documents, approval_flows, approval_steps, approval_logs, notifications")
    print("staffs拡張: position, approval_level")

if __name__ == '__main__':
    migrate()
