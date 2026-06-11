from datetime import datetime
from utils import now_jst
from sqlalchemy import Column, Integer, String, Float, Numeric, DateTime, Date, ForeignKey, Text, Boolean, Index
from sqlalchemy.orm import relationship, DeclarativeBase


class Base(DeclarativeBase):
    pass


class Staff(Base):
    __tablename__ = "staffs"
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    login_id = Column(String(50), unique=True, nullable=False)
    password_hash = Column(String(200), nullable=False)
    role = Column(String(20), default="user")
    department = Column(String(100), nullable=True)
    email = Column(String(200), nullable=True)
    is_active = Column(Boolean, default=True)
    last_active_at = Column(DateTime, nullable=True)
    last_active_page = Column(String(200), nullable=True)
    position = Column(String(100), nullable=True)
    approval_level = Column(Integer, default=0)
    created_at = Column(DateTime, default=now_jst)


class Customer(Base):
    __tablename__ = "customers"
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(200), nullable=False)
    category = Column(String(50), default="hospital")  # hospital / supplier
    phone = Column(String(50), nullable=True)
    email = Column(String(200), nullable=True)
    address = Column(Text, nullable=True)
    trading_terms = Column(Text, nullable=True)  # 取引条件
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=now_jst)
    staff_id = Column(Integer, ForeignKey("staffs.id"), nullable=True)
    staff = relationship("Staff")
    quotes = relationship("Quote", back_populates="customer", foreign_keys="Quote.customer_id")
    __table_args__ = (
        Index("ix_customers_name", "name"),
        Index("ix_customers_category", "category"),
    )


class Product(Base):
    __tablename__ = "products"
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(200), nullable=False)
    category = Column(String(50), nullable=False)
    sku = Column(String(100), unique=True, nullable=True)
    unit_price = Column(Numeric(12, 2), nullable=False)
    unit = Column(String(20), nullable=True)
    stock_alert_threshold = Column(Integer, default=10)
    alert_enabled = Column(Boolean, default=True, nullable=False)
    tracking_type = Column(String(20), default="none")
    maker = Column(String(200), nullable=True)
    jan_code = Column(String(50), nullable=True)          # JANコード
    approval_number = Column(String(100), nullable=True)  # 承認番号 / 認証番号
    device_class = Column(String(20), nullable=True)      # クラス分類: misc/1/2/3/4
    sales_role = Column(String(20), nullable=True)        # maker / distributor
    model_spec = Column(Text, nullable=True)              # 型式・仕様
    sterility = Column(String(20), nullable=True)         # 滅菌状態: sterile / non_sterile
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=now_jst)
    inventory = relationship("Inventory", back_populates="product", uselist=False)
    inventory_histories = relationship("InventoryHistory", back_populates="product")
    quote_items = relationship("QuoteItem", back_populates="product")
    shipment_items = relationship("ShipmentItem", back_populates="product")
    __table_args__ = (
        Index("ix_products_name", "name"),
        Index("ix_products_category", "category"),
        Index("ix_products_maker", "maker"),
    )


class Inventory(Base):
    __tablename__ = "inventory"
    id = Column(Integer, primary_key=True, autoincrement=True)
    product_id = Column(Integer, ForeignKey("products.id"), unique=True)
    current_stock = Column(Integer, nullable=False, default=0)
    updated_at = Column(DateTime, default=now_jst, onupdate=now_jst)
    product = relationship("Product", back_populates="inventory")


class InventoryHistory(Base):
    __tablename__ = "inventory_history"
    id = Column(Integer, primary_key=True, autoincrement=True)
    product_id = Column(Integer, ForeignKey("products.id"))
    movement_type = Column(String(10), nullable=False)
    quantity = Column(Integer, nullable=False)
    reason = Column(String(200), nullable=True)
    related_quote_id = Column(Integer, ForeignKey("quotes.id"), nullable=True)
    moved_at = Column(DateTime, default=now_jst)
    note = Column(Text, nullable=True)
    staff_name = Column(String(100), nullable=True)
    serial_number = Column(String(100), nullable=True)
    lot_number = Column(String(100), nullable=True)
    expiry_date = Column(String(20), nullable=True)
    product = relationship("Product", back_populates="inventory_histories")
    __table_args__ = (
        Index("ix_inventory_history_product_id", "product_id"),
        Index("ix_inventory_history_moved_at", "moved_at"),
        Index("ix_inventory_history_movement_type", "movement_type"),
    )


class Quote(Base):
    __tablename__ = "quotes"
    id = Column(Integer, primary_key=True, autoincrement=True)
    quote_number = Column(String(50), unique=True)
    customer_id = Column(Integer, ForeignKey("customers.id"))
    end_user_id = Column(Integer, ForeignKey("customers.id"), nullable=True)
    status = Column(String(20), default="draft")
    total_amount = Column(Numeric(12, 2), default=0.0)
    valid_until = Column(Date, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=now_jst)
    staff_name = Column(String(100), nullable=True)
    approval_doc_id = Column(Integer, nullable=True)
    created_by_id = Column(Integer, ForeignKey("staffs.id"), nullable=True)
    # [C5] 承認・取消フローで参照されるカラムをモデルに明示定義
    approved_by_id = Column(Integer, ForeignKey("staffs.id"), nullable=True)
    approved_at = Column(DateTime, nullable=True)
    approval_comment = Column(Text, nullable=True)
    cancelled_by_id = Column(Integer, ForeignKey("staffs.id"), nullable=True)
    cancel_comment = Column(Text, nullable=True)
    cancelled_at = Column(DateTime, nullable=True)
    customer = relationship("Customer", back_populates="quotes", foreign_keys=[customer_id])
    created_by = relationship("Staff", foreign_keys=[created_by_id])
    approved_by = relationship("Staff", foreign_keys=[approved_by_id])
    cancelled_by = relationship("Staff", foreign_keys=[cancelled_by_id])
    end_user = relationship("Customer", foreign_keys=[end_user_id])
    items = relationship("QuoteItem", back_populates="quote", cascade="all, delete-orphan")
    __table_args__ = (
        Index("ix_quotes_customer_id", "customer_id"),
        Index("ix_quotes_status", "status"),
        Index("ix_quotes_created_at", "created_at"),
    )


class QuoteItem(Base):
    __tablename__ = "quote_items"
    id = Column(Integer, primary_key=True, autoincrement=True)
    quote_id = Column(Integer, ForeignKey("quotes.id"))
    product_id = Column(Integer, ForeignKey("products.id"))
    quantity = Column(Integer, nullable=False)
    unit_price = Column(Numeric(12, 2), nullable=False)
    discount_rate = Column(Float, default=1.0)
    subtotal = Column(Numeric(12, 2), default=0.0)
    quote = relationship("Quote", back_populates="items")
    product = relationship("Product", back_populates="quote_items")


class Shipment(Base):
    __tablename__ = "shipments"
    id            = Column(Integer, primary_key=True, autoincrement=True)
    shipment_number = Column(String(50), unique=True)
    customer_id   = Column(Integer, ForeignKey("customers.id"))
    end_user_id   = Column(Integer, ForeignKey("customers.id"), nullable=True)
    shipped_date  = Column(Date, nullable=False)
    return_due_date = Column(Date, nullable=True)   # デモ・代替品用
    returned_date = Column(Date, nullable=True)
    status        = Column(String(20), default="shipped")
    notes         = Column(Text, nullable=True)
    staff_name    = Column(String(100), nullable=True)
    created_at    = Column(DateTime, default=now_jst)
    customer  = relationship("Customer", foreign_keys=[customer_id])
    end_user  = relationship("Customer", foreign_keys=[end_user_id])
    items     = relationship("ShipmentItem", back_populates="shipment",
                             cascade="all, delete-orphan", order_by="ShipmentItem.line_no")
    __table_args__ = (
        Index("ix_shipments_customer_id", "customer_id"),
        Index("ix_shipments_status", "status"),
        Index("ix_shipments_shipped_date", "shipped_date"),
    )


class ShipmentItem(Base):
    """出荷明細行 — 1出荷に複数商品・複数種別を持てる"""
    __tablename__ = "shipment_items"
    id           = Column(Integer, primary_key=True, autoincrement=True)
    shipment_id  = Column(Integer, ForeignKey("shipments.id"), nullable=False)
    line_no      = Column(Integer, nullable=False, default=1)
    shipment_type = Column(String(20), nullable=False)
    # sale / demo / sample / repair_sub
    product_id   = Column(Integer, ForeignKey("products.id"), nullable=False)
    quantity     = Column(Integer, nullable=False, default=1)
    serial_number = Column(String(100), nullable=True)
    lot_number   = Column(String(100), nullable=True)
    expiry_date  = Column(Date, nullable=True)
    demo_unit_id = Column(Integer, ForeignKey("demo_units.id"), nullable=True)
    shipment  = relationship("Shipment", back_populates="items")
    product   = relationship("Product", back_populates="shipment_items")
    demo_unit = relationship("DemoUnit")
    sale      = relationship("Sale", back_populates="shipment_item", uselist=False)
    __table_args__ = (
        Index("ix_shipment_items_shipment_id", "shipment_id"),
        Index("ix_shipment_items_product_id", "product_id"),
    )


class Sale(Base):
    __tablename__ = "sales"
    id = Column(Integer, primary_key=True, autoincrement=True)
    sale_number = Column(String(50), unique=True, nullable=False)
    shipment_item_id = Column(Integer, ForeignKey("shipment_items.id"), nullable=True)
    quote_id = Column(Integer, ForeignKey("quotes.id"), nullable=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    quantity = Column(Integer, nullable=False, default=1)
    unit_price = Column(Numeric(12, 2), nullable=False)
    subtotal = Column(Numeric(12, 2), nullable=False)
    tax_rate = Column(Float, default=0.10)
    tax_amount = Column(Numeric(12, 2), nullable=False)
    total_amount = Column(Numeric(12, 2), nullable=False)
    sale_date = Column(Date, nullable=False)
    status = Column(String(20), default="confirmed")  # confirmed / invoiced / paid
    notes = Column(Text, nullable=True)
    staff_name = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=now_jst)
    shipment_item = relationship("ShipmentItem", back_populates="sale", foreign_keys=[shipment_item_id])
    quote = relationship("Quote", foreign_keys=[quote_id])
    customer = relationship("Customer", foreign_keys=[customer_id])
    product = relationship("Product", foreign_keys=[product_id])
    invoice_items = relationship("InvoiceItem", back_populates="sale", cascade="all, delete-orphan")
    __table_args__ = (
        Index("ix_sales_customer_id", "customer_id"),
        Index("ix_sales_product_id", "product_id"),
        Index("ix_sales_sale_date", "sale_date"),
        Index("ix_sales_status", "status"),
    )


class Invoice(Base):
    __tablename__ = "invoices"
    id = Column(Integer, primary_key=True, autoincrement=True)
    invoice_number = Column(String(50), unique=True, nullable=False)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False)
    issue_date = Column(Date, nullable=False)
    due_date = Column(Date, nullable=True)
    subtotal = Column(Numeric(12, 2), default=0.0)
    tax_amount = Column(Numeric(12, 2), default=0.0)
    total_amount = Column(Numeric(12, 2), default=0.0)
    status = Column(String(20), default="unpaid")  # unpaid / partial / paid
    notes = Column(Text, nullable=True)
    staff_name = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=now_jst)
    customer = relationship("Customer", foreign_keys=[customer_id])
    items = relationship("InvoiceItem", back_populates="invoice", cascade="all, delete-orphan")
    payments = relationship("Payment", back_populates="invoice", cascade="all, delete-orphan")


class InvoiceItem(Base):
    __tablename__ = "invoice_items"
    id = Column(Integer, primary_key=True, autoincrement=True)
    invoice_id = Column(Integer, ForeignKey("invoices.id"), nullable=False)
    sale_id = Column(Integer, ForeignKey("sales.id"), nullable=False)
    amount = Column(Numeric(12, 2), nullable=False)
    invoice = relationship("Invoice", back_populates="items")
    sale = relationship("Sale", back_populates="invoice_items")


class Payment(Base):
    __tablename__ = "payments"
    id = Column(Integer, primary_key=True, autoincrement=True)
    invoice_id = Column(Integer, ForeignKey("invoices.id"), nullable=False)
    payment_date = Column(Date, nullable=False)
    amount = Column(Numeric(12, 2), nullable=False)
    method = Column(String(50), nullable=True)  # 銀行振込 / 現金 等
    notes = Column(Text, nullable=True)
    staff_name = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=now_jst)
    invoice = relationship("Invoice", back_populates="payments")


class DemoUnit(Base):
    """デモ機マスタ - デモ器1台1台を管理"""
    __tablename__ = "demo_units"
    id = Column(Integer, primary_key=True, autoincrement=True)
    unit_code = Column(String(50), unique=True, nullable=False)   # 管理番号 例: DEMO-001
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    serial_number = Column(String(100), nullable=True)            # 機器シリアル番号
    lot_number = Column(String(100), nullable=True)               # ロット番号
    status = Column(String(20), default="available")
    # available(貸出可) / on_loan(貸出中) / in_repair(修理中) / retired(廃棄)
    location_type = Column(String(20), default="own")
    # own(自社) / customer(取引先) / maker(製造元) / end_user(エンドユーザー)
    location_name = Column(String(200), default="CTM本社")       # 拠点名・取引先名など
    purchase_date = Column(Date, nullable=True)                   # 自社購入日
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=now_jst)

    product = relationship("Product")
    loans = relationship("DemoLoan", back_populates="demo_unit", cascade="all, delete-orphan")
    repairs = relationship("RepairRecord", back_populates="demo_unit", cascade="all, delete-orphan")
    __table_args__ = (
        Index("ix_demo_units_status", "status"),
        Index("ix_demo_units_product_id", "product_id"),
    )


class DemoLoan(Base):
    """デモ器貸出記録 - 誰にいつ貸してどう返ってきたか"""
    __tablename__ = "demo_loans"
    id = Column(Integer, primary_key=True, autoincrement=True)
    demo_unit_id = Column(Integer, ForeignKey("demo_units.id"), nullable=False)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False)
    end_user_id = Column(Integer, ForeignKey("customers.id"), nullable=True)
    loan_date = Column(Date, nullable=False)
    due_date = Column(Date, nullable=False)
    returned_date = Column(Date, nullable=True)
    contact_name = Column(String(100), nullable=True)
    purpose = Column(String(200), nullable=True)
    status = Column(String(20), default="on_loan")
    condition_out = Column(String(200), nullable=True)
    condition_in = Column(String(200), nullable=True)
    staff_name = Column(String(100), nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=now_jst)

    demo_unit = relationship("DemoUnit", back_populates="loans")
    customer  = relationship("Customer", foreign_keys=[customer_id])
    end_user  = relationship("Customer", foreign_keys=[end_user_id])


class Repair(Base):
    """修理受付管理"""
    __tablename__ = "repairs"
    id                       = Column(Integer, primary_key=True, autoincrement=True)
    repair_number            = Column(String(50), nullable=False, unique=True)
    customer_id              = Column(Integer, ForeignKey("customers.id"), nullable=False)
    end_user_id              = Column(Integer, ForeignKey("customers.id"), nullable=True)
    product_id               = Column(Integer, ForeignKey("products.id"), nullable=False)
    serial_number            = Column(String(100), nullable=True)
    lot_number               = Column(String(100), nullable=True)
    fault_description        = Column(Text, nullable=False)
    received_date            = Column(Date, nullable=False)
    replacement_shipment_id  = Column(Integer, nullable=True)
    status                   = Column(String(30), nullable=False, default="received")
    inspection_date          = Column(Date, nullable=True)
    inspection_result        = Column(Text, nullable=True)
    inspector                = Column(String(100), nullable=True)
    sent_to_maker_date       = Column(Date, nullable=True)
    maker_response           = Column(String(20), nullable=True)
    maker_response_date      = Column(Date, nullable=True)
    maker_quote_amount       = Column(Numeric(12, 2), nullable=True)
    maker_response_note      = Column(Text, nullable=True)
    quote_id                 = Column(Integer, nullable=True)
    quote_submitted_date     = Column(Date, nullable=True)
    repair_ordered_date      = Column(Date, nullable=True)
    repair_completed_date    = Column(Date, nullable=True)
    delivery_type            = Column(String(20), nullable=True)
    delivery_address         = Column(Text, nullable=True)
    replacement_returned_date = Column(Date, nullable=True)
    returned_serial_number   = Column(String(100), nullable=True)
    closed_date              = Column(Date, nullable=True)
    step_deadline            = Column(Date, nullable=True)
    notes                    = Column(Text, nullable=True)
    staff_name               = Column(String(100), nullable=True)
    created_at               = Column(DateTime, default=now_jst)
    updated_at               = Column(DateTime, default=now_jst, onupdate=now_jst)

    customer  = relationship("Customer", foreign_keys=[customer_id])
    end_user  = relationship("Customer", foreign_keys=[end_user_id])
    product   = relationship("Product")
    __table_args__ = (
        Index("ix_repairs_customer_id", "customer_id"),
        Index("ix_repairs_product_id", "product_id"),
        Index("ix_repairs_status", "status"),
        Index("ix_repairs_received_date", "received_date"),
    )


class RepairRecord(Base):
    """故障・修理記録 - 故障の内容と修理経緯を追跡"""
    __tablename__ = "repair_records"
    id = Column(Integer, primary_key=True, autoincrement=True)
    demo_unit_id = Column(Integer, ForeignKey("demo_units.id"), nullable=False)
    reported_date = Column(Date, nullable=False)                  # 故障報告日
    symptom = Column(Text, nullable=False)                        # 故障症状
    cause = Column(Text, nullable=True)                           # 原因（判明後）
    repair_vendor = Column(String(200), nullable=True)            # 修理業者
    repair_cost = Column(Numeric(12, 2), nullable=True)           # 修理費用
    sent_date = Column(Date, nullable=True)                       # メーカー送付日
    repaired_date = Column(Date, nullable=True)                   # 修理完了・返却日
    status = Column(String(20), nullable=False, default="pending")
    staff_name = Column(String(100), nullable=True)               # 担当スタッフ
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=now_jst)

    demo_unit = relationship("DemoUnit", back_populates="repairs")


# ── 資料ライブラリ ──────────────────────────────────────────────────────────────

class MaterialCategory(Base):
    __tablename__ = "material_categories"
    id         = Column(Integer, primary_key=True, autoincrement=True)
    name       = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime, default=now_jst)

    materials  = relationship("Material", back_populates="category")


class Material(Base):
    __tablename__ = "materials"
    id            = Column(Integer, primary_key=True, autoincrement=True)
    title         = Column(String(300), nullable=False)
    description   = Column(Text, nullable=True)
    category_id   = Column(Integer, ForeignKey("material_categories.id"), nullable=True)
    file_path     = Column(String(500), nullable=False)
    file_name     = Column(String(300), nullable=False)
    file_type     = Column(String(20), nullable=False)
    file_size     = Column(Integer, nullable=False)
    ai_summary    = Column(Text, nullable=True)
    version       = Column(Integer, default=1)
    is_active     = Column(Boolean, default=True)
    uploaded_by   = Column(Integer, ForeignKey("staffs.id"), nullable=True)
    from_approval = Column(Integer, nullable=True)
    created_at    = Column(DateTime, default=now_jst)
    updated_at    = Column(DateTime, default=now_jst, onupdate=now_jst)

    category      = relationship("MaterialCategory", back_populates="materials")
    uploader      = relationship("Staff", foreign_keys=[uploaded_by])
    tag_relations = relationship("MaterialTagRelation", back_populates="material", cascade="all, delete-orphan")
    versions      = relationship("MaterialVersion", back_populates="material", cascade="all, delete-orphan")
    favorites     = relationship("Favorite", back_populates="material", cascade="all, delete-orphan")


class MaterialTag(Base):
    __tablename__ = "material_tags"
    id         = Column(Integer, primary_key=True, autoincrement=True)
    name       = Column(String(100), nullable=False, unique=True)
    created_at = Column(DateTime, default=now_jst)
    relations  = relationship("MaterialTagRelation", back_populates="tag", cascade="all, delete-orphan")


class MaterialTagRelation(Base):
    __tablename__ = "material_tag_relations"
    id          = Column(Integer, primary_key=True, autoincrement=True)
    material_id = Column(Integer, ForeignKey("materials.id"), nullable=False)
    tag_id      = Column(Integer, ForeignKey("material_tags.id"), nullable=False)
    material    = relationship("Material", back_populates="tag_relations")
    tag         = relationship("MaterialTag", back_populates="relations")


class MaterialVersion(Base):
    __tablename__ = "material_versions"
    id          = Column(Integer, primary_key=True, autoincrement=True)
    material_id = Column(Integer, ForeignKey("materials.id"), nullable=False)
    version     = Column(Integer, nullable=False)
    file_path   = Column(String(500), nullable=False)
    file_name   = Column(String(300), nullable=False)
    file_size   = Column(Integer, nullable=False)
    ai_summary  = Column(Text, nullable=True)
    uploaded_by = Column(Integer, ForeignKey("staffs.id"), nullable=True)
    note        = Column(Text, nullable=True)
    created_at  = Column(DateTime, default=now_jst)
    material    = relationship("Material", back_populates="versions")


class Favorite(Base):
    __tablename__ = "favorites"
    id          = Column(Integer, primary_key=True, autoincrement=True)
    staff_id    = Column(Integer, ForeignKey("staffs.id"), nullable=False)
    material_id = Column(Integer, ForeignKey("materials.id"), nullable=False)
    created_at  = Column(DateTime, default=now_jst)
    material    = relationship("Material", back_populates="favorites")


class Task(Base):
    __tablename__ = "tasks"
    id          = Column(Integer, primary_key=True, autoincrement=True)
    title       = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    priority    = Column(String(20), default="medium")
    status      = Column(String(20), default="todo")
    assignee_id = Column(Integer, ForeignKey("staffs.id"), nullable=True)
    created_by  = Column(Integer, ForeignKey("staffs.id"), nullable=True)
    due_date    = Column(Date, nullable=True)
    created_at  = Column(DateTime, default=now_jst)
    updated_at  = Column(DateTime, default=now_jst, onupdate=now_jst)
    assignee    = relationship("Staff", foreign_keys=[assignee_id])
    creator     = relationship("Staff", foreign_keys=[created_by])
    comments    = relationship("TaskComment", back_populates="task", cascade="all, delete-orphan")


class TaskComment(Base):
    __tablename__ = "task_comments"
    id         = Column(Integer, primary_key=True, autoincrement=True)
    task_id    = Column(Integer, ForeignKey("tasks.id"), nullable=False)
    staff_id   = Column(Integer, ForeignKey("staffs.id"), nullable=True)
    body       = Column(Text, nullable=False)
    created_at = Column(DateTime, default=now_jst)
    task       = relationship("Task", back_populates="comments")
    author     = relationship("Staff", foreign_keys=[staff_id])


class Return(Base):
    """返品管理 - 売上に対する返品を記録"""
    __tablename__ = "returns"
    id            = Column(Integer, primary_key=True, autoincrement=True)
    return_number = Column(String(50), unique=True, nullable=False)
    sale_id       = Column(Integer, ForeignKey("sales.id"), nullable=True)
    customer_id   = Column(Integer, ForeignKey("customers.id"), nullable=False)
    product_id    = Column(Integer, ForeignKey("products.id"), nullable=False)
    quantity      = Column(Integer, nullable=False, default=1)
    return_date   = Column(Date, nullable=False)
    reason        = Column(Text, nullable=True)
    restock       = Column(Boolean, default=False)   # 在庫に戻すか
    status        = Column(String(20), default="returned")  # returned / restocked / disposed
    notes         = Column(Text, nullable=True)
    staff_name    = Column(String(100), nullable=True)
    created_at    = Column(DateTime, default=now_jst)

    sale     = relationship("Sale",     foreign_keys=[sale_id])
    customer = relationship("Customer", foreign_keys=[customer_id])
    product  = relationship("Product",  foreign_keys=[product_id])
    __table_args__ = (
        Index("ix_returns_sale_id",     "sale_id"),
        Index("ix_returns_customer_id", "customer_id"),
        Index("ix_returns_product_id",  "product_id"),
        Index("ix_returns_return_date", "return_date"),
    )