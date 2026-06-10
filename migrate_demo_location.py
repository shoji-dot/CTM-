"""デモ器に所在地フィールドを追加するマイグレーション"""
import os
from sqlalchemy import create_engine, text

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./sales.db")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL)
with engine.connect() as conn:
    for col, definition in [
        ("location_type", "VARCHAR(20) DEFAULT 'own'"),
        ("location_name", "VARCHAR(200) DEFAULT 'CTM本社'"),
    ]:
        try:
            conn.execute(text(f"ALTER TABLE demo_units ADD COLUMN {col} {definition}"))
            print(f"Added {col}")
        except Exception as e:
            print(f"Skip {col}: {e}")
    conn.commit()
print("Done")
