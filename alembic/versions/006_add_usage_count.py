"""add usage_count to demo_units and max_usage_count to products

Revision ID: 006
Revises: 005
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
    if not _column_exists('demo_units', 'usage_count'):
        op.add_column('demo_units',
            sa.Column('usage_count', sa.Integer(), nullable=False, server_default='0'))

    if not _column_exists('products', 'max_usage_count'):
        op.add_column('products',
            sa.Column('max_usage_count', sa.Integer(), nullable=True))


def downgrade():
    if _column_exists('demo_units', 'usage_count'):
        op.drop_column('demo_units', 'usage_count')

    if _column_exists('products', 'max_usage_count'):
        op.drop_column('products', 'max_usage_count')
