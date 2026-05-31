import sqlite3, os
db_path = os.path.join(os.path.dirname(__file__), "sales_app.db")
con = sqlite3.connect(db_path)
cur = con.cursor()

# quotes テーブルに承認連携カラムを追加
cols = [row[1] for row in cur.execute("PRAGMA table_info(quotes)")]
migrations = [
    ("approval_doc_id",  "INTEGER"),   # documents.id への外部キー
    ("created_by_id",    "INTEGER"),   # 作成者スタッフID
    ("approval_comment", "TEXT"),      # 承認時コメント
    ("approved_by_id",   "INTEGER"),   # 承認者スタッフID
    ("approved_at",      "DATETIME"),  # 承認日時
    ("cancelled_by_id",  "INTEGER"),   # 取消者スタッフID
    ("cancel_comment",   "TEXT"),      # 取消コメント
    ("cancelled_at",     "DATETIME"),  # 取消日時
]
for col, type_ in migrations:
    if col not in cols:
        cur.execute(f"ALTER TABLE quotes ADD COLUMN {col} {type_}")
        print(f"Added to quotes: {col}")

# document_types に「見積」が未登録なら追加
row = cur.execute("SELECT id FROM document_types WHERE name='見積'").fetchone()
if not row:
    cur.execute("INSERT INTO document_types (name, description) VALUES ('見積', '見積書の承認フロー')")
    print("Added document_type: 見積")
else:
    print(f"document_type '見積' already exists (id={row[0]})")

con.commit()
con.close()
print("Done")
