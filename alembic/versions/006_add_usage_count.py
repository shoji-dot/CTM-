"""add usage_count to demo_units and max_usage_count to products

Revision ID: 006
Revises: 005
Create Date: 2026-06-15
"""
from alembic import op
import sqlalchemy as sa

revision = '006'
down_revision = '005'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('demo_units') as batch_op:
        batch_op.add_column(sa.Column('usage_count', sa.Integer(), nullable=False, server_default='0'))

    with op.batch_alter_table('products') as batch_op:
        batch_op.add_column(sa.Column('max_usage_count', sa.Integer(), nullable=True))


def downgrade():
    with op.batch_alter_table('demo_units') as batch_op:
        batch_op.drop_column('usage_count')

    with op.batch_alter_table('products') as batch_op:
        batch_op.drop_column('max_usage_count')
