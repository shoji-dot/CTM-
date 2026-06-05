"""
quotes テーブルに approval_doc_id 列を追加するマイグレーション
PostgreSQL / SQLite 両対応
"""
import os
from database import engine

def migrate():
    with engine.connect() as conn:
        try:
            conn.execute(__import__('sqlalchemy').text(
                "ALTER TABLE quotes ADD COLUMN approval_doc_id INTEGER"
            ))
            conn.commit()
            print("OK: quotes.approval_doc_id 追加完了")
        except Exception as e:
            msg = str(e).lower()
            if "already exists" in msg or "duplicate column" in msg:
                print("SKIP: approval_doc_id は既に存在します")
            else:
                print(f"ERROR: {e}")
                raise

if __name__ == "__main__":
    migrate()
