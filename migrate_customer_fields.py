"""
顧客テーブルの変更マイグレーション
  - trading_terms カラム追加（取引条件）
  - category の既存値を hospital/supplier に変換（medical→hospital, ham→supplier）

実行方法:
  venv\Scripts\python migrate_customer_fields.py
"""
import sqlite3, os, shutil
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "sales_app.db")

bak = DB_PATH + ".bak_" + datetime.now().strftime("%Y%m%d_%H%M%S")
shutil.copy2(DB_PATH, bak)
print(f"バックアップ作成: {bak}")

conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

cur.execute("PRAGMA table_info(customers)")
existing = [row[1] for row in cur.fetchall()]
print(f"既存カラム: {existing}")

# trading_terms 追加
if "trading_terms" not in existing:
    cur.execute("ALTER TABLE customers ADD COLUMN trading_terms TEXT")
    print("  追加: trading_terms")
else:
    print("  スキップ（既存）: trading_terms")

# category 値の変換
cur.execute("UPDATE customers SET category = 'hospital' WHERE category = 'medical'")
cur.execute("UPDATE customers SET category = 'supplier' WHERE category = 'ham'")
updated = cur.rowcount
print(f"  category 変換完了（{cur.execute('SELECT COUNT(*) FROM customers').fetchone()[0]}件）")

conn.commit()
conn.close()
print("マイグレーション完了")
