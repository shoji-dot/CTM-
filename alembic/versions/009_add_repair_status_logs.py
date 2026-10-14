"""add repair_status_logs

Revision ID: 009
Revises: 008
Create Date: 2026-07-07

修理工程の変更履歴（進める／戻す／記録編集）テーブル。
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = '009'
down_revision = '008'


def _table_exists(name: str) -> bool:
    return name in inspect(op.get_bind()).get_table_names()


def upgrade():
    if not _table_exists("repair_status_logs"):
        op.create_table(
            "repair_status_logs",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("repair_id", sa.Integer(), sa.ForeignKey("repairs.id"), nullable=False),
            sa.Column("action", sa.String(20), nullable=False),
            sa.Column("from_status", sa.String(30), nullable=True),
            sa.Column("to_status", sa.String(30), nullable=True),
            sa.Column("staff_name", sa.String(100), nullable=True),
            sa.Column("note", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
        )
        op.create_index("ix_repair_status_logs_repair_id", "repair_status_logs", ["repair_id"])


def downgrade():
    if _table_exists("repair_status_logs"):
        op.drop_table("repair_status_logs")
