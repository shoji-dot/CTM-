"""
商品テーブルに以下4カラムを追加するマイグレーション
  - jan_code        : JANコード
  - approval_number : 承認番号 / 認証番号
  - device_class    : クラス分類 (misc/1/2/3/4)
  - sales_role      : メーカー/代理店 (maker/distributor)

実行方法:
  venv\Scripts\python migrate_product_fields.py
"""
import sqlite3, os, shutil
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "sales_app.db")

# バックアップ
bak = DB_PATH + ".bak_" + datetime.now().strftime("%Y%m%d_%H%M%S")
shutil.copy2(DB_PATH, bak)
print(f"バックアップ作成: {bak}")

conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

cur.execute("PRAGMA table_info(products)")
existing = [row[1] for row in cur.fetchall()]
print(f"既存カラム: {existing}")

new_cols = [
    ("jan_code",        "VARCHAR(50)"),
    ("approval_number", "VARCHAR(100)"),
    ("device_class",    "VARCHAR(20)"),
    ("sales_role",      "VARCHAR(20)"),
]

for col_name, col_type in new_cols:
    if col_name not in existing:
        cur.execute(f"ALTER TABLE products ADD COLUMN {col_name} {col_type}")
        print(f"  追加: {col_name}")
    else:
        print(f"  スキップ（既存）: {col_name}")

conn.commit()
conn.close()
print("マイグレーション完了")
