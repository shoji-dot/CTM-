import sqlite3, os
db_path = os.path.join(os.path.dirname(__file__), "sales_app.db")
con = sqlite3.connect(db_path)
cur = con.cursor()
cols = [row[1] for row in cur.execute("PRAGMA table_info(products)")]
if "model_spec" not in cols:
    cur.execute("ALTER TABLE products ADD COLUMN model_spec TEXT")
    print("Added: model_spec")
if "sterility" not in cols:
    cur.execute("ALTER TABLE products ADD COLUMN sterility VARCHAR(20)")
    print("Added: sterility")
con.commit()
con.close()
print("Done")
