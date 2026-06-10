"""migrate_returns.py - returnsテーブル作成"""
import os
from sqlalchemy import create_engine, text

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./sales_app.db")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL)

SQL = """
CREATE TABLE IF NOT EXISTS returns (
    id            SERIAL PRIMARY KEY,
    return_number VARCHAR(50) UNIQUE NOT NULL,
    sale_id       INTEGER REFERENCES sales(id),
    customer_id   INTEGER NOT NULL REFERENCES customers(id),
    product_id    INTEGER NOT NULL REFERENCES products(id),
    quantity      INTEGER NOT NULL DEFAULT 1,
    return_date   DATE NOT NULL,
    reason        TEXT,
    restock       BOOLEAN NOT NULL DEFAULT FALSE,
    status        VARCHAR(20) NOT NULL DEFAULT 'returned',
    notes         TEXT,
    staff_name    VARCHAR(100),
    created_at    TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_returns_sale_id     ON returns(sale_id);
CREATE INDEX IF NOT EXISTS ix_returns_customer_id ON returns(customer_id);
CREATE INDEX IF NOT EXISTS ix_returns_return_date ON returns(return_date);
"""

with engine.connect() as conn:
    conn.execute(text(SQL))
    conn.commit()
    print("returns テーブル作成完了")
