"""add return_destination_id to demo_loans

Revision ID: 008
Revises: 007
Create Date: 2026-06-15

拠点間デモ器管理: 返却先を自由に選択できるようにする。
NULLはデフォルト（CTM本社）を意味する。
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


def _column_exists(table: str, column: str) -> bool:
    bind = op.get_bind()
    insp = inspect(bind)
    return column in [c["name"] for c in insp.get_columns(table)]


def upgrade():
    if not _column_exists("demo_loans", "return_destination_id"):
        op.add_column(
            "demo_loans",
            sa.Column(
                "return_destination_id",
                sa.Integer(),
                sa.ForeignKey("customers.id"),
                nullable=True,
            ),
        )


def downgrade():
    if _column_exists("demo_loans", "return_destination_id"):
        op.drop_column("demo_loans", "return_destination_id")
