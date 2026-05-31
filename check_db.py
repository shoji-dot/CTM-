import sqlite3
con = sqlite3.connect('sales_app.db')
for r in con.execute('PRAGMA table_info(notifications)'):
    print(r[1])