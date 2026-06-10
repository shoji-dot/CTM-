"""
出荷明細テーブル追加マイグレーション
- shipment_items テーブル作成
- sales.shipment_id → shipment_item_id へ変更（既存データなし前提）
"""
import os
from sqlalchemy import create_engine, text

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./sales.db")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL)
with engine.connect() as conn:
    # shipment_items テーブル作成
    try:
        conn.execute(text("""
            CREATE TABLE shipment_items (
                id            SERIAL PRIMARY KEY,
                shipment_id   INTEGER NOT NULL REFERENCES shipments(id) ON DELETE CASCADE,
                line_no       INTEGER NOT NULL DEFAULT 1,
                shipment_type VARCHAR(20) NOT NULL,
                product_id    INTEGER NOT NULL REFERENCES products(id),
                quantity      INTEGER NOT NULL DEFAULT 1,
                serial_number VARCHAR(100),
                lot_number    VARCHAR(100),
                expiry_date   DATE,
                demo_unit_id  INTEGER REFERENCES demo_units(id)
            )
        """))
        conn.execute(text("CREATE INDEX ix_shipment_items_shipment_id ON shipment_items(shipment_id)"))
        conn.execute(text("CREATE INDEX ix_shipment_items_product_id  ON shipment_items(product_id)"))
        print("Created shipment_items table")
    except Exception as e:
        print(f"shipment_items: {e}")

    # sales テーブル: shipment_id → shipment_item_id
    for sql, label in [
        ("ALTER TABLE sales ADD COLUMN shipment_item_id INTEGER REFERENCES shipment_items(id)", "sales.shipment_item_id ADD"),
        ("ALTER TABLE sales DROP COLUMN IF EXISTS shipment_id", "sales.shipment_id DROP"),
    ]:
        try:
            conn.execute(text(sql))
            print(f"OK: {label}")
        except Exception as e:
            print(f"Skip {label}: {e}")

    # shipments テーブルから item系カラムを削除
    for col in ["shipment_type", "product_id", "quantity", "serial_number",
                "lot_number", "expiry_date"]:
        try:
            conn.execute(text(f"ALTER TABLE shipments DROP COLUMN IF EXISTS {col}"))
            print(f"Dropped shipments.{col}")
        except Exception as e:
            print(f"Skip shipments.{col}: {e}")

    conn.commit()
print("Done")
