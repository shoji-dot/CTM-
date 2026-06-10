"""add lot_number to demo_units

Revision ID: 003
Revises: 002
Create Date: 2026-06-10
"""
from alembic import op
import sqlalchemy as sa

revision = '003'
down_revision = '002'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('demo_units') as batch_op:
        batch_op.add_column(sa.Column('lot_number', sa.String(100), nullable=True))


def downgrade():
    with op.batch_alter_table('demo_units') as batch_op:
        batch_op.drop_column('lot_number')
