from datetime import datetime, date
from sqlalchemy import or_
from sqlalchemy.orm import Session, aliased, joinedload
from models import Customer, Product, Inventory, InventoryHistory, Quote, QuoteItem, Shipment, DemoUnit
import sqlite3 as _sqlite3
import os as _os

_DB_PATH = _os.path.join(_os.path.dirname(__file__), "sales_app.db")

def _raw_db():
    conn = _sqlite3.connect(_DB_PATH, timeout=30)
    conn.row_factory = _sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn

def _now_str():
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')



# ── Customers ──────────────────────────────────────────────
def get_customers(db: Session, search: str = "", category: str = ""):
    q = db.query(Customer)
    if search:
        q = q.filter(Customer.name.contains(search))
    if category:
        q = q.filter(Customer.category == category)
    return q.order_by(Customer.id.desc()).all()

def get_customer(db: Session, customer_id: int):
    return db.query(Customer).filter(Customer.id == customer_id).first()

def create_customer(db: Session, data: dict):
    obj = Customer(**data)
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj

def update_customer(db: Session, customer_id: int, data: dict):
    obj = db.query(Customer).filter(Customer.id == customer_id).first()
    if not obj:
        return None
    for k, v in data.items():
        setattr(obj, k, v)
    db.commit()
    db.refresh(obj)
    return obj

def delete_customer(db: Session, customer_id: int):
    obj = db.query(Customer).filter(Customer.id == customer_id).first()
    if obj:
        db.delete(obj)
        db.commit()
    return obj


# ── Products ───────────────────────────────────────────────
def get_products(db: Session, search: str = "", category: str = "", maker: str = ""):
    q = db.query(Product)
    if search:
        q = q.filter(Product.name.contains(search))
    if maker:
        q = q.filter(Product.maker.contains(maker))
    if category:
        q = q.filter(Product.category == category)
    return q.order_by(Product.id.desc()).all()

def get_product(db: Session, product_id: int):
    return db.query(Product).filter(Product.id == product_id).first()

def create_product(db: Session, data: dict):
    obj = Product(**data)
    db.add(obj)
    db.flush()
    inv = Inventory(product_id=obj.id, current_stock=0)
    db.add(inv)
    db.commit()
    db.refresh(obj)
    return obj

def duplicate_product(db: Session, product_id: int):
    src = db.query(Product).filter(Product.id == product_id).first()
    if not src:
        return None
    new_obj = Product(
        name=src.name + " のコピー",
        category=src.category,
        sku=None,  # SKUはユニーク制約のためクリア
        unit_price=src.unit_price,
        unit=src.unit,
        stock_alert_threshold=src.stock_alert_threshold,
        tracking_type=src.tracking_type,
        maker=src.maker,
        jan_code=src.jan_code,
        approval_number=src.approval_number,
        device_class=src.device_class,
        sales_role=src.sales_role,
        model_spec=src.model_spec,
        sterility=src.sterility,
        notes=src.notes,
    )
    db.add(new_obj)
    db.flush()
    inv = Inventory(product_id=new_obj.id, current_stock=0)
    db.add(inv)
    db.commit()
    db.refresh(new_obj)
    return new_obj

def update_product(db: Session, product_id: int, data: dict):
    obj = db.query(Product).filter(Product.id == product_id).first()
    if not obj:
        return None
    for k, v in data.items():
        setattr(obj, k, v)
    db.commit()
    db.refresh(obj)
    return obj

def delete_product(db: Session, product_id: int):
    obj = db.query(Product).filter(Product.id == product_id).first()
    if obj:
        db.delete(obj)
        db.commit()
    return obj


# ── Inventory ──────────────────────────────────────────────
def get_inventory_list(db: Session):
    return db.query(Inventory).join(Product).all()

def get_alerts(db: Session):
    rows = db.query(Inventory).join(Product).all()
    return [r for r in rows if r.product.alert_enabled and r.current_stock <= r.product.stock_alert_threshold]

def move_inventory(db, product_id, movement_type, quantity,
                   reason="", note="", related_quote_id=None,
                   serial_number=None, lot_number=None, expiry_date=None,
                   staff_name=None):
    inv = db.query(Inventory).filter(Inventory.product_id == product_id).first()
    if not inv:
        return None
    if movement_type == "in":
        inv.current_stock += quantity
    else:
        inv.current_stock = max(0, inv.current_stock - quantity)
    inv.updated_at = datetime.now()
    history = InventoryHistory(
        product_id=product_id,
        movement_type=movement_type,
        quantity=quantity,
        reason=reason,
        note=note,
        related_quote_id=related_quote_id,
        serial_number=serial_number,
        lot_number=lot_number,
        expiry_date=str(expiry_date) if expiry_date else None,
        staff_name=staff_name,
    )
    db.add(history)
    db.commit()
    db.refresh(inv)
    return inv

def get_inventory_history(db: Session, product_id: int = None):
    q = db.query(InventoryHistory).join(Product)
    if product_id:
        q = q.filter(InventoryHistory.product_id == product_id)
    return q.order_by(InventoryHistory.moved_at.desc()).all()

def get_inventory_history_filtered(db, product_id=None, movement_type=None, date_from=None, date_to=None, staff_name=None, customer=None):
    from sqlalchemy import cast, Date
    q = db.query(InventoryHistory).join(Product)
    if product_id:
        q = q.filter(InventoryHistory.product_id == product_id)
    if movement_type:
        q = q.filter(InventoryHistory.movement_type == movement_type)
    if date_from:
        q = q.filter(cast(InventoryHistory.moved_at, Date) >= date_from)
    if date_to:
        q = q.filter(cast(InventoryHistory.moved_at, Date) <= date_to)
    if staff_name:
        q = q.filter(InventoryHistory.staff_name.ilike(f"%{staff_name}%"))
    if customer:
        q = q.filter(
            (InventoryHistory.reason.ilike(f"%{customer}%")) |
            (InventoryHistory.note.ilike(f"%{customer}%"))
        )
    return q.order_by(InventoryHistory.moved_at.desc()).all()


# ── Quotes ─────────────────────────────────────────────────
def _gen_quote_number(db: Session):
    today = datetime.now().strftime("%Y%m%d")
    prefix = f"Q-{today}-"
    count = db.query(Quote).filter(Quote.quote_number.like(f"{prefix}%")).count()
    return f"{prefix}{count + 1:03d}"



def get_quotes(db: Session, status: str = "", customer: str = "", end_user: str = "", product: str = ""):
    q = db.query(Quote).join(Quote.customer)

    if status:
        q = q.filter(Quote.status == status)
    if customer:
        q = q.filter(Customer.name.contains(customer))
    if end_user:
        EndUser = aliased(Customer)
        q = q.join(EndUser, Quote.end_user_id == EndUser.id)
        q = q.filter(EndUser.name.contains(end_user))
    if product:
        q = q.join(Quote.items).join(QuoteItem.product)
        q = q.filter(Product.name.contains(product))

    # テンプレートで q.end_user / q.items / q.items[0].product を使うために先読み
    q = q.options(
        joinedload(Quote.end_user),
        joinedload(Quote.items).joinedload(QuoteItem.product),
    )

    return q.order_by(Quote.id.desc()).distinct().all()
def get_quote(db: Session, quote_id: int):
    return db.query(Quote).filter(Quote.id == quote_id).first()

def create_quote(db: Session, customer_id: int, valid_until: date, notes: str, items: list, end_user_id: int = None, created_by_id: int = None):
    quote = Quote(
        quote_number=_gen_quote_number(db),
        customer_id=customer_id,
        end_user_id=end_user_id, 
        valid_until=valid_until,
        notes=notes,)
    db.add(quote)
    db.flush()
    total = 0.0
    for item in items:
        product = db.query(Product).filter(Product.id == item["product_id"]).first()
        price = product.unit_price if product else 0.0
        qty = item["quantity"]
        discount_rate = item.get("discount_rate", 1.0)  
        subtotal = price * qty * discount_rate   
        total += subtotal
        qi = QuoteItem(
            quote_id=quote.id,
            product_id=item["product_id"],
            quantity=qty,
            unit_price=price,
            discount_rate=discount_rate,   
            subtotal=subtotal,
        )
        db.add(qi)
    quote.total_amount = total
    if created_by_id:
        quote.created_by_id = created_by_id
    db.commit()
    db.refresh(quote)

    # ── 承認フローに自動登録 ──────────────────────────────
    if created_by_id:
        try:
            conn = _raw_db()
            dt_row = conn.execute(
                "SELECT id FROM document_types WHERE name='見積' AND is_active=1 LIMIT 1"
            ).fetchone()
            if dt_row:
                dt_id = dt_row['id']
                flow = conn.execute(
                    "SELECT * FROM approval_flows WHERE document_type_id=? AND is_active=1 LIMIT 1",
                    (dt_id,)
                ).fetchone()
                if flow:
                    # documents レコード作成
                    cur = conn.execute("""
                        INSERT INTO documents
                          (title, document_type_id, file_path, file_name, file_size, mime_type, uploaded_by, status)
                        VALUES (?,?,?,?,?,?,?,'draft')
                    """, (
                        f"見積書 {quote.quote_number}",
                        dt_id, '', quote.quote_number, 0, 'application/quote', created_by_id
                    ))
                    doc_id = cur.lastrowid

                    # 申請状態に遷移
                    steps = conn.execute(
                        "SELECT * FROM approval_steps WHERE flow_id=? ORDER BY step_order",
                        (flow['id'],)
                    ).fetchall()
                    if steps:
                        conn.execute("""
                            UPDATE documents SET status='in_review', current_step=1, updated_at=? WHERE id=?
                        """, (_now_str(), doc_id))
                        conn.execute("""
                            INSERT INTO approval_logs (document_id, step_order, approver_id, action, comment)
                            VALUES (?,0,?,'submitted','見積作成により自動申請')
                        """, (doc_id, created_by_id))
                        # 最初の承認者に通知
                        first = steps[0]
                        if first['approver_id']:
                            conn.execute(
                                "INSERT INTO notifications (document_id, recipient_id, type) VALUES (?,?,?)",
                                (doc_id, first['approver_id'], 'approval_request')
                            )

                    conn.commit()

                    # quote に approval_doc_id を保存
                    quote.approval_doc_id = doc_id
                    db.commit()
            conn.close()
        except Exception as e:
            print(f"[warn] 承認フロー自動登録に失敗: {e}")

    return quote

def update_quote_status(db: Session, quote_id: int, status: str):
    obj = db.query(Quote).filter(Quote.id == quote_id).first()
    if not obj:
        return None
    obj.status = status
    db.commit()
    db.refresh(obj)
    return obj

def delete_quote(db: Session, quote_id: int):
    obj = db.query(Quote).filter(Quote.id == quote_id).first()
    if obj:
        db.delete(obj)
        db.commit()
    return obj


# ── Shipments ──────────────────────────────────────────────
def _gen_shipment_number(db: Session):
    today = datetime.now().strftime("%Y%m%d")
    prefix = f"SH-{today}-"
    count = db.query(Shipment).filter(Shipment.shipment_number.like(f"{prefix}%")).count()
    return f"{prefix}{count + 1:03d}"

def get_shipments(db: Session, status: str = "", shipment_type: str = "",
                  q_text: str = "", serial: str = "", lot: str = ""):
    from sqlalchemy import or_
    EndUser = aliased(Customer)
    q = db.query(Shipment).join(Customer, Shipment.customer_id == Customer.id, isouter=True)\
        .join(EndUser, Shipment.end_user_id == EndUser.id, isouter=True)\
        .join(Product, Shipment.product_id == Product.id, isouter=True)
    if status:
        q = q.filter(Shipment.status == status)
    if shipment_type:
        q = q.filter(Shipment.shipment_type == shipment_type)
    if q_text:
        like = f"%{q_text}%"
        q = q.filter(or_(
            Shipment.shipment_number.ilike(like),
            Customer.name.ilike(like),
            EndUser.name.ilike(like),
            Product.name.ilike(like),
        ))
    if serial:
        q = q.filter(Shipment.serial_number.ilike(f"%{serial}%"))
    if lot:
        q = q.filter(Shipment.lot_number.ilike(f"%{lot}%"))
    return q.order_by(Shipment.id.desc()).all()

def get_shipment(db: Session, shipment_id: int):
    return db.query(Shipment).filter(Shipment.id == shipment_id).first()

def create_shipment(db: Session, data: dict):
    data["shipment_number"] = _gen_shipment_number(db)
    obj = Shipment(**data)
    db.add(obj)
    db.flush()
    type_label = {"sale": "販売出荷", "demo": "デモ貸出", "sample": "サンプル出荷", "repair": "修理代替品出荷"}
    move_inventory(db, obj.product_id, "out", obj.quantity,
                   reason=type_label.get(obj.shipment_type, "出荷"))
    db.commit()
    db.refresh(obj)
    return obj

def update_shipment(db: Session, shipment_id: int, data: dict):
    obj = db.query(Shipment).filter(Shipment.id == shipment_id).first()
    if not obj:
        return None
    for k, v in data.items():
        setattr(obj, k, v)
    db.commit()
    db.refresh(obj)
    return obj

def return_shipment(db: Session, shipment_id: int, returned_date: date):
    obj = db.query(Shipment).filter(Shipment.id == shipment_id).first()
    if not obj:
        return None
    obj.returned_date = returned_date
    obj.status = "returned"
    if obj.shipment_type in ("demo", "repair"):
        move_inventory(db, obj.product_id, "in", obj.quantity, reason="返却入庫")
    db.commit()
    db.refresh(obj)
    return obj

def complete_shipment(db: Session, shipment_id: int):
    obj = db.query(Shipment).filter(Shipment.id == shipment_id).first()
    if not obj:
        return None
    obj.status = "completed"
    db.commit()
    db.refresh(obj)
    return obj

def delete_shipment(db: Session, shipment_id: int):
    obj = db.query(Shipment).filter(Shipment.id == shipment_id).first()
    if obj:
        if obj.status == "shipped":
            move_inventory(db, obj.product_id, "in", obj.quantity, reason="出荷取消")
        db.delete(obj)
        db.commit()
    return obj


# ── 在庫検索（販売・サンプル用）────────────────────────────
def search_inventory_items(db: Session, q: str = "", product_id: int = None):
    """在庫入庫履歴からシリアル/ロット番号を検索して返す"""
    query = db.query(InventoryHistory).join(
        Product, InventoryHistory.product_id == Product.id
    ).filter(InventoryHistory.movement_type == "in")
    if product_id:
        query = query.filter(InventoryHistory.product_id == product_id)
    if q:
        query = query.filter(or_(
            InventoryHistory.serial_number.ilike(f"%{q}%"),
            InventoryHistory.lot_number.ilike(f"%{q}%"),
            Product.name.ilike(f"%{q}%"),
        ))
    return query.order_by(InventoryHistory.moved_at.desc()).limit(30).all()


def validate_inventory_item(db: Session, product_id: int,
                             serial_number: str = None, lot_number: str = None) -> bool:
    """指定のserial/lotが在庫入庫履歴に存在するか確認"""
    if not serial_number and not lot_number:
        return True  # 指定なし → 在庫数チェックのみ（別途）
    q = db.query(InventoryHistory).filter(
        InventoryHistory.product_id == product_id,
        InventoryHistory.movement_type == "in",
    )
    if serial_number:
        q = q.filter(InventoryHistory.serial_number == serial_number)
    if lot_number:
        q = q.filter(InventoryHistory.lot_number == lot_number)
    return q.first() is not None


# ── デモ器検索（デモ貸出・修理代替品用）─────────────────────
def search_demo_units(db: Session, q: str = "", product_id: int = None):
    """デモ器台帳を型番・管理番号・シリアル番号で検索"""
    query = db.query(DemoUnit).join(
        Product, DemoUnit.product_id == Product.id
    )
    if product_id:
        query = query.filter(DemoUnit.product_id == product_id)
    if q:
        query = query.filter(or_(
            DemoUnit.serial_number.ilike(f"%{q}%"),
            DemoUnit.unit_code.ilike(f"%{q}%"),
            Product.name.ilike(f"%{q}%"),
        ))
    return query.order_by(DemoUnit.unit_code).limit(30).all()
