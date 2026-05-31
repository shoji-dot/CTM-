import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), 'sales_app.db')

def migrate():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # タスク
    cur.execute("""
    CREATE TABLE IF NOT EXISTS tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        description TEXT,
        status TEXT NOT NULL DEFAULT 'todo'
            CHECK(status IN ('todo','in_progress','done','cancelled')),
        priority TEXT NOT NULL DEFAULT 'medium'
            CHECK(priority IN ('high','medium','low')),
        assignee_id INTEGER REFERENCES staffs(id),   -- 担当者
        created_by INTEGER NOT NULL REFERENCES staffs(id),
        due_date TEXT,                                -- NULL=期限なし
        created_at TEXT DEFAULT (datetime('now', 'localtime')),
        updated_at TEXT DEFAULT (datetime('now', 'localtime'))
    )
    """)

    # タスクコメント
    cur.execute("""
    CREATE TABLE IF NOT EXISTS task_comments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        task_id INTEGER NOT NULL REFERENCES tasks(id),
        author_id INTEGER NOT NULL REFERENCES staffs(id),
        body TEXT NOT NULL,
        created_at TEXT DEFAULT (datetime('now', 'localtime'))
    )
    """)

    conn.commit()
    conn.close()
    print("✅ タスク管理マイグレーション完了")
    print("追加テーブル: tasks, task_comments")

if __name__ == '__main__':
    migrate()
