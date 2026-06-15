"""Add failed_attempts and locked_until to staffs for login security

Revision ID: 005
Revises: 004
Create Date: 2026-06-15
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


def _column_exists(table: str, column: str) -> bool:
    bind = op.get_bind()
    insp = inspect(bind)
    return column in [c["name"] for c in insp.get_columns(table)]


def upgrade():
    if not _column_exists("staffs", "failed_attempts"):
        with op.batch_alter_table("staffs") as b:
            b.add_column(sa.Column("failed_attempts", sa.Integer(), nullable=False, server_default="0"))

    if not _column_exists("staffs", "locked_until"):
        with op.batch_alter_table("staffs") as b:
            b.add_column(sa.Column("locked_until", sa.DateTime(), nullable=True))


def downgrade():
    if _column_exists("staffs", "locked_until"):
        with op.batch_alter_table("staffs") as b:
            b.drop_column("locked_until")

    if _column_exists("staffs", "failed_attempts"):
        with op.batch_alter_table("staffs") as b:
            b.drop_column("failed_attempts")
