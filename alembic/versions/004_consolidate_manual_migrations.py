"""Consolidate manual migrations from main.py _run_migrations()

Revision ID: 004
Revises: 003
Create Date: 2026-06-14

_run_migrations() で管理されていた全変更を Alembic に統合する。
すでに本番 DB に適用済みの可能性があるため、全操作を冪等に実装する。
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text


# ── ヘルパー関数 ──────────────────────────────────────────────────────────────

def _bind():
    return op.get_bind()

def _table_exists(table: str) -> bool:
    return inspect(_bind()).has_table(table)

def _column_exists(table: str, column: str) -> bool:
    cols = [c["name"] for c in inspect(_bind()).get_columns(table)]
    return column in cols

def _index_exists(table: str, index_name: str) -> bool:
    idxs = [i["name"] for i in inspect(_bind()).get_indexes(table)]
    return index_name in idxs

def _add_column_if_not_exists(table: str, column: sa.Column):
    if not _column_exists(table, column.name):
        with op.batch_alter_table(table) as batch_op:
            batch_op.add_column(column)

def _create_index_if_not_exists(name: str, table: str, columns: list):
    if not _index_exists(table, name):
        op.create_index(name, table, columns)


# ── revision 設定 ──────────────────────────────────────────────────────────────

revision = '004'
down_revision = '003'
branch_labels = None
depends_on = None


# ── upgrade ────────────────────────────────────────────────────────────────────

def upgrade() -> None:

    # ── 新規テーブル（CREATE TABLE IF NOT EXISTS 相当）────────────────────────

    if not _table_exists('announcements'):
        op.create_table(
            'announcements',
            sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
            sa.Column('title', sa.Text, nullable=False),
            sa.Column('body', sa.Text, nullable=False),
            sa.Column('author_id', sa.Integer, sa.ForeignKey('staffs.id'), nullable=False),
            sa.Column('is_pinned', sa.Boolean, server_default='false'),
            sa.Column('created_at', sa.DateTime, server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime, server_default=sa.func.now()),
        )

    if not _table_exists('document_types'):
        op.create_table(
            'document_types',
            sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
            sa.Column('name', sa.Text, nullable=False, unique=True),
            sa.Column('description', sa.Text),
            sa.Column('is_active', sa.Boolean, server_default='true'),
            sa.Column('created_at', sa.DateTime, server_default=sa.func.now()),
        )

    if not _table_exists('documents'):
        op.create_table(
            'documents',
            sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
            sa.Column('title', sa.Text, nullable=False),
            sa.Column('document_type_id', sa.Integer, sa.ForeignKey('document_types.id'), nullable=False),
            sa.Column('file_path', sa.Text, nullable=False),
            sa.Column('file_name', sa.Text, nullable=False),
            sa.Column('file_size', sa.Integer),
            sa.Column('mime_type', sa.Text),
            sa.Column('status', sa.Text, nullable=False, server_default='draft'),
            sa.Column('uploaded_by', sa.Integer, sa.ForeignKey('staffs.id'), nullable=False),
            sa.Column('current_step', sa.Integer, server_default='0'),
            sa.Column('comment', sa.Text),
            sa.Column('created_at', sa.DateTime, server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime, server_default=sa.func.now()),
        )

    if not _table_exists('approval_flows'):
        op.create_table(
            'approval_flows',
            sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
            sa.Column('document_type_id', sa.Integer, sa.ForeignKey('document_types.id'), nullable=False),
            sa.Column('name', sa.Text, nullable=False),
            sa.Column('is_active', sa.Boolean, server_default='true'),
            sa.Column('created_at', sa.DateTime, server_default=sa.func.now()),
        )

    if not _table_exists('approval_steps'):
        op.create_table(
            'approval_steps',
            sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
            sa.Column('flow_id', sa.Integer, sa.ForeignKey('approval_flows.id'), nullable=False),
            sa.Column('step_order', sa.Integer, nullable=False),
            sa.Column('step_name', sa.Text, nullable=False),
            sa.Column('approver_id', sa.Integer, sa.ForeignKey('staffs.id')),
            sa.Column('approver_role', sa.Text),
            sa.Column('required_level', sa.Integer, server_default='0'),
            sa.Column('created_at', sa.DateTime, server_default=sa.func.now()),
        )

    if not _table_exists('approval_logs'):
        op.create_table(
            'approval_logs',
            sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
            sa.Column('document_id', sa.Integer, sa.ForeignKey('documents.id'), nullable=False),
            sa.Column('step_order', sa.Integer, nullable=False),
            sa.Column('approver_id', sa.Integer, sa.ForeignKey('staffs.id'), nullable=False),
            sa.Column('action', sa.Text, nullable=False),
            sa.Column('comment', sa.Text),
            sa.Column('created_at', sa.DateTime, server_default=sa.func.now()),
        )

    if not _table_exists('notifications'):
        op.create_table(
            'notifications',
            sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
            sa.Column('document_id', sa.Integer),
            sa.Column('recipient_id', sa.Integer, sa.ForeignKey('staffs.id'), nullable=False),
            sa.Column('type', sa.Text, nullable=False),
            sa.Column('is_sent', sa.Boolean, server_default='false'),
            sa.Column('sent_at', sa.DateTime),
            sa.Column('created_at', sa.DateTime, server_default=sa.func.now()),
            sa.Column('resource_type', sa.Text),
            sa.Column('resource_id', sa.Integer),
            sa.Column('message', sa.Text, server_default=''),
            sa.Column('link', sa.Text, server_default=''),
        )

    if not _table_exists('customer_memos'):
        op.create_table(
            'customer_memos',
            sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
            sa.Column('hospital', sa.Text, nullable=False),
            sa.Column('doctor_name', sa.Text),
            sa.Column('memo', sa.Text),
            sa.Column('staff_id', sa.Integer, sa.ForeignKey('staffs.id')),
            sa.Column('created_at', sa.DateTime, nullable=False, server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime, nullable=False, server_default=sa.func.now()),
        )

    if not _table_exists('shipment_items'):
        op.create_table(
            'shipment_items',
            sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
            sa.Column('shipment_id', sa.Integer, sa.ForeignKey('shipments.id', ondelete='CASCADE'), nullable=False),
            sa.Column('line_no', sa.Integer, nullable=False, server_default='1'),
            sa.Column('shipment_type', sa.String(20), nullable=False),
            sa.Column('product_id', sa.Integer, sa.ForeignKey('products.id'), nullable=False),
            sa.Column('quantity', sa.Integer, nullable=False, server_default='1'),
            sa.Column('serial_number', sa.String(100)),
            sa.Column('lot_number', sa.String(100)),
            sa.Column('expiry_date', sa.Date),
            sa.Column('demo_unit_id', sa.Integer, sa.ForeignKey('demo_units.id')),
        )

    # ── インデックス（shipment_items）─────────────────────────────────────────
    _create_index_if_not_exists('ix_shipment_items_shipment_id', 'shipment_items', ['shipment_id'])
    _create_index_if_not_exists('ix_shipment_items_product_id',  'shipment_items', ['product_id'])

    # ── 列追加: quotes ─────────────────────────────────────────────────────────
    _add_column_if_not_exists('quotes', sa.Column('approval_doc_id', sa.Integer))
    _add_column_if_not_exists('quotes', sa.Column('created_by_id', sa.Integer, sa.ForeignKey('staffs.id')))
    _add_column_if_not_exists('quotes', sa.Column('approved_by_id', sa.Integer, sa.ForeignKey('staffs.id')))
    _add_column_if_not_exists('quotes', sa.Column('approved_at', sa.DateTime))
    _add_column_if_not_exists('quotes', sa.Column('approval_comment', sa.Text))
    _add_column_if_not_exists('quotes', sa.Column('cancelled_by_id', sa.Integer, sa.ForeignKey('staffs.id')))
    _add_column_if_not_exists('quotes', sa.Column('cancel_comment', sa.Text))
    _add_column_if_not_exists('quotes', sa.Column('cancelled_at', sa.DateTime))

    # ── 列追加: products ───────────────────────────────────────────────────────
    _add_column_if_not_exists('products', sa.Column('alert_enabled', sa.Boolean, nullable=False, server_default='true'))

    # ── 列追加: staffs ─────────────────────────────────────────────────────────
    _add_column_if_not_exists('staffs', sa.Column('position', sa.String(100)))
    _add_column_if_not_exists('staffs', sa.Column('approval_level', sa.Integer, server_default='0'))
    _add_column_if_not_exists('staffs', sa.Column('failed_attempts', sa.Integer, nullable=False, server_default='0'))
    _add_column_if_not_exists('staffs', sa.Column('locked_until', sa.DateTime))

    # ── 列追加: sales ──────────────────────────────────────────────────────────
    _add_column_if_not_exists('sales', sa.Column('shipment_item_id', sa.Integer, sa.ForeignKey('shipment_items.id')))

    # ── 列追加: demo_units ─────────────────────────────────────────────────────
    _add_column_if_not_exists('demo_units', sa.Column('location_type', sa.String(50), server_default='own'))
    _add_column_if_not_exists('demo_units', sa.Column('location_name', sa.String(200), server_default='CTM本社'))

    # ── 列追加: shipments ──────────────────────────────────────────────────────
    _add_column_if_not_exists('shipments', sa.Column('shipment_type', sa.String(20)))
    _add_column_if_not_exists('shipments', sa.Column('quantity', sa.Integer, nullable=False, server_default='1'))
    _add_column_if_not_exists('shipments', sa.Column('contact_name', sa.String(100)))
    _add_column_if_not_exists('shipments', sa.Column('end_user_contact', sa.String(100)))

    # ── 列追加: repair_records ─────────────────────────────────────────────────
    _add_column_if_not_exists('repair_records', sa.Column('staff_name', sa.String(100)))


# ── downgrade ─────────────────────────────────────────────────────────────────

def downgrade() -> None:
    # テーブル削除（逆順）
    for tbl in ['shipment_items', 'customer_memos', 'notifications',
                'approval_logs', 'approval_steps', 'approval_flows',
                'documents', 'document_types', 'announcements']:
        if _table_exists(tbl):
            op.drop_table(tbl)

    # 列削除: repair_records
    if _column_exists('repair_records', 'staff_name'):
        with op.batch_alter_table('repair_records') as b:
            b.drop_column('staff_name')

    # 列削除: shipments
    for col in ['end_user_contact', 'contact_name', 'quantity', 'shipment_type']:
        if _column_exists('shipments', col):
            with op.batch_alter_table('shipments') as b:
                b.drop_column(col)

    # 列削除: demo_units
    for col in ['location_name', 'location_type']:
        if _column_exists('demo_units', col):
            with op.batch_alter_table('demo_units') as b:
                b.drop_column(col)

    # 列削除: sales
    if _column_exists('sales', 'shipment_item_id'):
        with op.batch_alter_table('sales') as b:
            b.drop_column('shipment_item_id')

    # 列削除: staffs
    for col in ['locked_until', 'failed_attempts', 'approval_level', 'position']:
        if _column_exists('staffs', col):
            with op.batch_alter_table('staffs') as b:
                b.drop_column(col)

    # 列削除: products
    if _column_exists('products', 'alert_enabled'):
        with op.batch_alter_table('products') as b:
            b.drop_column('alert_enabled')

    # 列削除: quotes
    for col in ['cancelled_at', 'cancel_comment', 'cancelled_by_id',
                'approval_comment', 'approved_at', 'approved_by_id',
                'created_by_id', 'approval_doc_id']:
        if _column_exists('quotes', col):
            with op.batch_alter_table('quotes') as b:
                b.drop_column(col)
