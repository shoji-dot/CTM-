import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), 'sales_app.db')

def migrate():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS announcements (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        body TEXT NOT NULL,
        author_id INTEGER NOT NULL REFERENCES staffs(id),
        is_pinned INTEGER DEFAULT 0,
        created_at TEXT DEFAULT (datetime('now', 'localtime')),
        updated_at TEXT DEFAULT (datetime('now', 'localtime'))
    )
    """)

    conn.commit()
    conn.close()
    print("✅ お知らせテーブル作成完了")

if __name__ == '__main__':
    migrate()
