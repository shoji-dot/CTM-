"""add FK constraints to repairs table

Revision ID: 007
Revises: 006
Create Date: 2026-06-15

repairs.replacement_shipment_id -> shipments.id
repairs.quote_id                -> quotes.id

SQLite does not support ADD CONSTRAINT after the fact, so we use
batch_alter_table (which recreates the table) to add FK constraints.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


def _fk_exists(table: str, fk_name: str) -> bool:
    """SQLiteのFKはCREATE TABLE文で定義されるため、
    既存カラムに対してbatch操作が必要。
    冪等性のため、カラムが既にFKとして定義済みかチェックする。"""
    bind = op.get_bind()
    insp = inspect(bind)
    fks = insp.get_foreign_keys(table)
    return any(fk.get("name") == fk_name for fk in fks)


def upgrade():
    # SQLite では batch_alter_table でテーブルを再作成してFKを付与する
    with op.batch_alter_table("repairs", recreate="always") as batch_op:
        batch_op.alter_column(
            "replacement_shipment_id",
            existing_type=sa.Integer(),
            type_=sa.Integer(),
            existing_nullable=True,
            nullable=True,
        )
        # FKを追加（既存データがNULLなので参照整合性は問題なし）
        batch_op.create_foreign_key(
            "fk_repairs_replacement_shipment_id",
            "shipments",
            ["replacement_shipment_id"],
            ["id"],
        )
        batch_op.create_foreign_key(
            "fk_repairs_quote_id",
            "quotes",
            ["quote_id"],
            ["id"],
        )


def downgrade():
    with op.batch_alter_table("repairs", recreate="always") as batch_op:
        batch_op.drop_constraint("fk_repairs_replacement_shipment_id", type_="foreignkey")
        batch_op.drop_constraint("fk_repairs_quote_id", type_="foreignkey")
