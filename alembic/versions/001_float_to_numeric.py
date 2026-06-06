"""Float金額カラムをNumeric(12,2)に変更

Revision ID: 001
Revises: 
Create Date: 2026-06-05
"""
from alembic import op
import sqlalchemy as sa

revision = '001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # products.unit_price
    op.alter_column('products', 'unit_price',
        existing_type=sa.Float(),
        type_=sa.Numeric(12, 2),
        existing_nullable=False)

    # quotes.total_amount
    op.alter_column('quotes', 'total_amount',
        existing_type=sa.Float(),
        type_=sa.Numeric(12, 2),
        existing_nullable=True)

    # quote_items
    op.alter_column('quote_items', 'unit_price',
        existing_type=sa.Float(),
        type_=sa.Numeric(12, 2),
        existing_nullable=False)
    op.alter_column('quote_items', 'subtotal',
        existing_type=sa.Float(),
        type_=sa.Numeric(12, 2),
        existing_nullable=True)

    # sales
    op.alter_column('sales', 'unit_price',
        existing_type=sa.Float(),
        type_=sa.Numeric(12, 2),
        existing_nullable=False)
    op.alter_column('sales', 'subtotal',
        existing_type=sa.Float(),
        type_=sa.Numeric(12, 2),
        existing_nullable=False)
    op.alter_column('sales', 'tax_amount',
        existing_type=sa.Float(),
        type_=sa.Numeric(12, 2),
        existing_nullable=False)
    op.alter_column('sales', 'total_amount',
        existing_type=sa.Float(),
        type_=sa.Numeric(12, 2),
        existing_nullable=False)

    # invoices
    op.alter_column('invoices', 'subtotal',
        existing_type=sa.Float(),
        type_=sa.Numeric(12, 2),
        existing_nullable=True)
    op.alter_column('invoices', 'tax_amount',
        existing_type=sa.Float(),
        type_=sa.Numeric(12, 2),
        existing_nullable=True)
    op.alter_column('invoices', 'total_amount',
        existing_type=sa.Float(),
        type_=sa.Numeric(12, 2),
        existing_nullable=True)

    # invoice_items.amount
    op.alter_column('invoice_items', 'amount',
        existing_type=sa.Float(),
        type_=sa.Numeric(12, 2),
        existing_nullable=False)

    # payments.amount
    op.alter_column('payments', 'amount',
        existing_type=sa.Float(),
        type_=sa.Numeric(12, 2),
        existing_nullable=False)

    # repairs.maker_quote_amount
    op.alter_column('repairs', 'maker_quote_amount',
        existing_type=sa.Float(),
        type_=sa.Numeric(12, 2),
        existing_nullable=True)

    # repair_records.repair_cost
    op.alter_column('repair_records', 'repair_cost',
        existing_type=sa.Float(),
        type_=sa.Numeric(12, 2),
        existing_nullable=True)


def downgrade() -> None:
    # Numeric → Float に戻す（ロールバック用）
    tables_cols = [
        ('products', 'unit_price', False),
        ('quotes', 'total_amount', True),
        ('quote_items', 'unit_price', False),
        ('quote_items', 'subtotal', True),
        ('sales', 'unit_price', False),
        ('sales', 'subtotal', False),
        ('sales', 'tax_amount', False),
        ('sales', 'total_amount', False),
        ('invoices', 'subtotal', True),
        ('invoices', 'tax_amount', True),
        ('invoices', 'total_amount', True),
        ('invoice_items', 'amount', False),
        ('payments', 'amount', False),
        ('repairs', 'maker_quote_amount', True),
        ('repair_records', 'repair_cost', True),
    ]
    for table, col, nullable in tables_cols:
        op.alter_column(table, col,
            existing_type=sa.Numeric(12, 2),
            type_=sa.Float(),
            existing_nullable=nullable)
