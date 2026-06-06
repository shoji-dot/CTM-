"""Add performance indexes

Revision ID: 002
Revises: 001
Create Date: 2026-06-06
"""

from alembic import op

revision = '002'
down_revision = '001'
branch_labels = None
depends_on = None


def upgrade():
    # ── customers ──────────────────────────────────────────
    op.create_index('ix_customers_category', 'customers', ['category'])

    # ── products ───────────────────────────────────────────
    op.create_index('ix_products_category', 'products', ['category'])
    op.create_index('ix_products_maker',    'products', ['maker'])

    # ── quotes ─────────────────────────────────────────────
    op.create_index('ix_quotes_customer_id',  'quotes', ['customer_id'])
    op.create_index('ix_quotes_status',       'quotes', ['status'])
    op.create_index('ix_quotes_created_at',   'quotes', ['created_at'])

    # ── quote_items ────────────────────────────────────────
    op.create_index('ix_quote_items_quote_id',   'quote_items', ['quote_id'])
    op.create_index('ix_quote_items_product_id', 'quote_items', ['product_id'])

    # ── sales ──────────────────────────────────────────────
    op.create_index('ix_sales_customer_id', 'sales', ['customer_id'])
    op.create_index('ix_sales_product_id',  'sales', ['product_id'])
    op.create_index('ix_sales_quote_id',    'sales', ['quote_id'])
    op.create_index('ix_sales_status',      'sales', ['status'])
    op.create_index('ix_sales_sale_date',   'sales', ['sale_date'])

    # ── invoices ───────────────────────────────────────────
    op.create_index('ix_invoices_customer_id', 'invoices', ['customer_id'])
    op.create_index('ix_invoices_status',      'invoices', ['status'])

    # ── invoice_items ──────────────────────────────────────
    op.create_index('ix_invoice_items_invoice_id', 'invoice_items', ['invoice_id'])
    op.create_index('ix_invoice_items_sale_id',    'invoice_items', ['sale_id'])

    # ── shipments ──────────────────────────────────────────
    op.create_index('ix_shipments_customer_id',    'shipments', ['customer_id'])
    op.create_index('ix_shipments_product_id',     'shipments', ['product_id'])
    op.create_index('ix_shipments_status',         'shipments', ['status'])
    op.create_index('ix_shipments_shipment_type',  'shipments', ['shipment_type'])
    op.create_index('ix_shipments_shipped_date',   'shipments', ['shipped_date'])

    # ── inventory_history ──────────────────────────────────
    op.create_index('ix_inv_history_product_id',    'inventory_history', ['product_id'])
    op.create_index('ix_inv_history_movement_type', 'inventory_history', ['movement_type'])
    op.create_index('ix_inv_history_moved_at',      'inventory_history', ['moved_at'])

    # ── repairs ────────────────────────────────────────────
    op.create_index('ix_repairs_customer_id',   'repairs', ['customer_id'])
    op.create_index('ix_repairs_product_id',    'repairs', ['product_id'])
    op.create_index('ix_repairs_status',        'repairs', ['status'])
    op.create_index('ix_repairs_received_date', 'repairs', ['received_date'])

    # ── demo_loans ─────────────────────────────────────────
    op.create_index('ix_demo_loans_customer_id',  'demo_loans', ['customer_id'])
    op.create_index('ix_demo_loans_demo_unit_id', 'demo_loans', ['demo_unit_id'])
    op.create_index('ix_demo_loans_status',       'demo_loans', ['status'])


def downgrade():
    op.drop_index('ix_customers_category',      table_name='customers')
    op.drop_index('ix_products_category',       table_name='products')
    op.drop_index('ix_products_maker',          table_name='products')
    op.drop_index('ix_quotes_customer_id',      table_name='quotes')
    op.drop_index('ix_quotes_status',           table_name='quotes')
    op.drop_index('ix_quotes_created_at',       table_name='quotes')
    op.drop_index('ix_quote_items_quote_id',    table_name='quote_items')
    op.drop_index('ix_quote_items_product_id',  table_name='quote_items')
    op.drop_index('ix_sales_customer_id',       table_name='sales')
    op.drop_index('ix_sales_product_id',        table_name='sales')
    op.drop_index('ix_sales_quote_id',          table_name='sales')
    op.drop_index('ix_sales_status',            table_name='sales')
    op.drop_index('ix_sales_sale_date',         table_name='sales')
    op.drop_index('ix_invoices_customer_id',    table_name='invoices')
    op.drop_index('ix_invoices_status',         table_name='invoices')
    op.drop_index('ix_invoice_items_invoice_id',table_name='invoice_items')
    op.drop_index('ix_invoice_items_sale_id',   table_name='invoice_items')
    op.drop_index('ix_shipments_customer_id',   table_name='shipments')
    op.drop_index('ix_shipments_product_id',    table_name='shipments')
    op.drop_index('ix_shipments_status',        table_name='shipments')
    op.drop_index('ix_shipments_shipment_type', table_name='shipments')
    op.drop_index('ix_shipments_shipped_date',  table_name='shipments')
    op.drop_index('ix_inv_history_product_id',  table_name='inventory_history')
    op.drop_index('ix_inv_history_movement_type',table_name='inventory_history')
    op.drop_index('ix_inv_history_moved_at',    table_name='inventory_history')
    op.drop_index('ix_repairs_customer_id',     table_name='repairs')
    op.drop_index('ix_repairs_product_id',      table_name='repairs')
    op.drop_index('ix_repairs_status',          table_name='repairs')
    op.drop_index('ix_repairs_received_date',   table_name='repairs')
    op.drop_index('ix_demo_loans_customer_id',  table_name='demo_loans')
    op.drop_index('ix_demo_loans_demo_unit_id', table_name='demo_loans')
    op.drop_index('ix_demo_loans_status',       table_name='demo_loans')
