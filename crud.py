from utils import now_jst
from datetime import datetime, date
from fastapi import HTTPException
from sqlalchemy import or_

# ── [I4] ページネーションユーティリティ ──────────────────────────────────────
from dataclasses import dataclass

@dataclass
class Paginator:
    items: list
    page: int
    per_page: int
    total: int

    @property
    def total_pages(self) -> int:
        return max(1, (self.total + self.per_page - 1) // self.per_page)

    @property
    def has_prev(self) -> bool:
        return self.page > 1

    @property
    def has_next(self) -> bool:
        return self.page < self.total_pages

    @property
    def prev_page(self) -> int:
        return self.page - 1

    @property
    def next_page(self) -> int:
        return self.page + 1


def paginate(query, page: int = 1, per_page: int = 50) -> Paginator:
    """SQLAlchemyクエリにページネーションを適用して Paginator を返す。"""
    page = max(1, page)
    total = query.count()
    items = query.offset((page - 1) * per_page).limit(per_page).all()
    return Paginator(items=items, page=page, per_page=per_page, total=total)

from sqlalchemy.orm import Session, aliased, joinedload
from models import Customer, Product, Inventory, InventoryHistory, Quote, QuoteItem, Shipment, DemoUnit
from sqlalchemy import text as _sa_text

def _now_str():
    return now_jst().strftime('%Y-%m-%d %H:%M:%S')



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
    # [I10] 関連データが存在する場合は削除を拒否
    obj = db.query(Customer).filter(Customer.id == customer_id).first()
    if not obj:
        return None
    quote_count = db.query(Quote).filter(Quote.customer_id == customer_id).count()
    if quote_count > 0:
        raise HTTPException(400, f"この顧客には見積が{quote_count}件あるため削除できません。先に見積を削除してください。")
    from models import Sale, Repair, DemoLoan
    sale_count = db.query(Sale).filter(Sale.customer_id == customer_id).count()
    if sale_count > 0:
        raise HTTPException(400, f"この顧客には売上が{sale_count}件あるため削除できません。")
    # [C5] 出荷・修理・デモ貸出の存在チェック
    ship_count = db.query(Shipment).filter(Shipment.customer_id == customer_id).count()
    if ship_count > 0:
        raise HTTPException(400, f"この顧客には出荷記録が{ship_count}件あるため削除できません。")
    repair_count = db.query(Repair).filter(Repair.customer_id == customer_id).count()
    if repair_count > 0:
        raise HTTPException(400, f"この顧客には修理受付が{repair_count}件あるため削除できません。")
    demo_count = db.query(DemoLoan).filter(DemoLoan.customer_id == customer_id).count()
    if demo_count > 0:
        raise HTTPException(400, f"この顧客にはデモ貸出が{demo_count}件あるため削除できません。")
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

def get_products_query(db: Session, search: str = "", category: str = "", maker: str = ""):
    """get_products と同じフィルタ条件でクエリオブジェクトを返す（ページネーション用）"""
    q = db.query(Product)
    if search:
        q = q.filter(Product.name.contains(search))
    if maker:
        q = q.filter(Product.maker.contains(maker))
    if category:
        q = q.filter(Product.category == category)
    return q.order_by(Product.id.desc())


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
    # [I10] 在庫・見積明細・売上が存在する場合は削除を拒否
    obj = db.query(Product).filter(Product.id == product_id).first()
    if not obj:
        return None
    inv = db.query(Inventory).filter(Inventory.product_id == product_id).first()
    if inv and inv.current_stock > 0:
        raise HTTPException(400, f"在庫が{inv.current_stock}個あるため削除できません。在庫を0にしてから削除してください。")
    qi_count = db.query(QuoteItem).filter(QuoteItem.product_id == product_id).count()
    if qi_count > 0:
        raise HTTPException(400, f"この商品は{qi_count}件の見積明細で使用中のため削除できません。")
    from models import Sale
    sale_count = db.query(Sale).filter(Sale.product_id == product_id).count()
    if sale_count > 0:
        raise HTTPException(400, f"この商品には売上が{sale_count}件あるため削除できません。")
    # [I8] 出荷履歴チェック
    ship_count = db.query(Shipment).filter(Shipment.product_id == product_id).count()
    if ship_count > 0:
        raise HTTPException(400, f"この商品には出荷記録が{ship_count}件あるため削除できません。")
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
                   staff_name=None, allow_negative=False):
    """在庫移動。出庫時に在庫不足の場合は ValueError を送出する。
    allow_negative=True を指定した場合のみ在庫不足でも続行（廃棄等の特殊用途）。
    """
    # PostgreSQL: 行レベルロックで同時出庫による競合を防ぐ（SQLiteは無視される）
    inv = db.query(Inventory).filter(Inventory.product_id == product_id).with_for_update().first()
    if not inv:
        return None
    if movement_type == "in":
        inv.current_stock += quantity
    else:
        # [I5] 在庫マイナス防止: 不足時は ValueError を送出
        if not allow_negative and inv.current_stock < quantity:
            raise ValueError(
                f"在庫不足です（現在庫: {inv.current_stock}, 要求数: {quantity}）"
            )
        inv.current_stock = max(0, inv.current_stock - quantity)
    inv.updated_at = now_jst()
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
    return q.order_by(InventoryHistory.moved_at.desc())


# ── Quotes ─────────────────────────────────────────────────
def _gen_quote_number(db: Session):
    # [I3] MAX(id)+1 方式でrace conditionを解消
    today = now_jst().strftime("%Y%m%d")
    prefix = f"Q-{today}-"
    max_id = db.query(Quote.id).order_by(Quote.id.desc()).first()
    seq = (max_id[0] + 1) if max_id else 1
    return f"{prefix}{seq:05d}"



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

def get_quotes_query(db: Session, status: str = "", customer: str = "", end_user: str = "", product: str = "", staff_name: str = ""):
    """get_quotes と同じフィルタ条件でクエリオブジェクトを返す（ページネーション用）"""
    q = db.query(Quote).join(Quote.customer)
    if status:
        q = q.filter(Quote.status == status)
    if staff_name:
        q = q.filter(Quote.staff_name == staff_name)
    if customer:
        q = q.filter(Customer.name.contains(customer))
    if end_user:
        EndUser = aliased(Customer)
        q = q.join(EndUser, Quote.end_user_id == EndUser.id)
        q = q.filter(EndUser.name.contains(end_user))
    if product:
        q = q.join(Quote.items).join(QuoteItem.product)
        q = q.filter(Product.name.contains(product))
    q = q.options(
        joinedload(Quote.end_user),
        joinedload(Quote.items).joinedload(QuoteItem.product),
    )
    return q.order_by(Quote.id.desc()).distinct()

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
        # item に unit_price が明示されていればそちらを優先（修理費用など）
        price = item.get("unit_price") or (product.unit_price if product else 0.0)
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
            dt_row = db.execute(
                _sa_text("SELECT id FROM document_types WHERE name='見積' AND is_active=TRUE LIMIT 1")
            ).fetchone()
            if dt_row:
                dt_id = dt_row[0]
                flow = db.execute(
                    _sa_text("SELECT id FROM approval_flows WHERE document_type_id=:t AND is_active=TRUE LIMIT 1"),
                    {"t": dt_id}
                ).fetchone()
                if flow:
                    flow_id = flow[0]
                    result = db.execute(
                        _sa_text("""
                            INSERT INTO documents
                              (title, document_type_id, file_path, file_name, file_size, mime_type, uploaded_by, status)
                            VALUES (:title,:dtype,'', :fname, 0,'application/quote',:uploader,'draft')
                            RETURNING id
                        """),
                        {"title": f"見積書 {quote.quote_number}", "dtype": dt_id,
                         "fname": quote.quote_number, "uploader": created_by_id}
                    )
                    doc_id = result.scalar()

                    steps = db.execute(
                        _sa_text("SELECT id, step_order, approver_id FROM approval_steps WHERE flow_id=:f ORDER BY step_order"),
                        {"f": flow_id}
                    ).fetchall()
                    if steps:
                        db.execute(
                            _sa_text("UPDATE documents SET status='in_review', current_step=1, updated_at=:t WHERE id=:i"),
                            {"t": _now_str(), "i": doc_id}
                        )
                        db.execute(
                            _sa_text("""
                                INSERT INTO approval_logs (document_id, step_order, approver_id, action, comment)
                                VALUES (:d,0,:a,'submitted','見積作成により自動申請')
                            """),
                            {"d": doc_id, "a": created_by_id}
                        )
                        first = steps[0]
                        if first[2]:  # approver_id
                            db.execute(
                                _sa_text("INSERT INTO notifications (document_id, recipient_id, type) VALUES (:d,:r,'approval_request')"),
                                {"d": doc_id, "r": first[2]}
                            )
                    db.commit()
                    quote.approval_doc_id = doc_id
                    db.commit()
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
    if not obj:
        return None
    # [C6] 売上が紐づく見積は削除不可
    from models import Sale
    sale_count = db.query(Sale).filter(Sale.quote_id == quote_id).count()
    if sale_count > 0:
        raise HTTPException(400, f"この見積には売上が{sale_count}件紐づいているため削除できません。")
    db.delete(obj)
    db.commit()
    return obj


# ── Shipments ──────────────────────────────────────────────
def _gen_shipment_number(db: Session):
    # [I3] MAX(id)+1 方式
    today = now_jst().strftime("%Y%m%d")
    prefix = f"SH-{today}-"
    max_id = db.query(Shipment.id).order_by(Shipment.id.desc()).first()
    seq = (max_id[0] + 1) if max_id else 1
    return f"{prefix}{seq:05d}"

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
    # 数量変更時は在庫差分を再計算
    old_qty = obj.quantity
    new_qty = data.get("quantity", old_qty)
    if new_qty != old_qty and obj.status == "shipped":
        diff = new_qty - old_qty
        if diff > 0:
            move_inventory(db, obj.product_id, "out", diff, reason="出荷数量修正")
        else:
            move_inventory(db, obj.product_id, "in", abs(diff), reason="出荷数量修正")
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
    from models import DemoUnit
    from sqlalchemy.orm import joinedload
    query = db.query(DemoUnit).options(joinedload(DemoUnit.product)).filter(
        DemoUnit.status != "retired"
    )
    if product_id:
        query = query.filter(DemoUnit.product_id == product_id)
    if q:
        from models import Product
        like = f"%{q}%"
        query = query.join(Product, DemoUnit.product_id == Product.id).filter(
            (DemoUnit.unit_code.ilike(like)) |
            (DemoUnit.serial_number.ilike(like)) |
            (Product.name.ilike(like))
        )
    return query.order_by(DemoUnit.unit_code).all()


def get_expiry_alerts(db: Session, days: int = 30):
    """使用期限がdays日以内 or 期限切れの入庫ロットを返す（在庫あり商品のみ）"""
    from datetime import date, timedelta
    from models import InventoryHistory, Inventory, Product
    today = date.today()
    threshold = today + timedelta(days=days)

    # 在庫あり商品IDセット
    stocked_ids = {r.product_id for r in db.query(Inventory).filter(Inventory.current_stock > 0).all()}
    if not stocked_ids:
        return []

    rows = (
        db.query(InventoryHistory)
        .join(Product, InventoryHistory.product_id == Product.id)
        .filter(
            InventoryHistory.movement_type == "in",
            InventoryHistory.expiry_date.isnot(None),
            InventoryHistory.product_id.in_(stocked_ids),
        )
        .order_by(InventoryHistory.expiry_date)
        .all()
    )

    alerts = []
    seen = set()  # (product_id, expiry_date) 重複除去
    for r in rows:
        try:
            exp = date.fromisoformat(str(r.expiry_date)[:10])
        except (ValueError, TypeError):
            continue
        if exp > threshold:
            continue
        key = (r.product_id, str(exp))
        if key in seen:
            continue
        seen.add(key)
        alerts.append({
            "product_id":   r.product_id,
            "product_name": r.product.name if r.product else "",
            "lot_number":   r.lot_number or "",
            "expiry_date":  exp,
            "days_left":    (exp - today).days,
            "is_expired":   exp < today,
        })
    return alerts


def get_expiry_alerts(db, days: int = 30):
    """使用期限がdays日以内 or 期限切れの入庫ロットを返す（在庫あり商品のみ）"""
    from datetime import date, timedelta
    from models import InventoryHistory, Inventory
    today = date.today()
    threshold = today + timedelta(days=days)

    stocked_ids = {r.product_id for r in db.query(Inventory).filter(Inventory.current_stock > 0).all()}
    if not stocked_ids:
        return []

    rows = (
        db.query(InventoryHistory)
        .filter(
            InventoryHistory.movement_type == "in",
            InventoryHistory.expiry_date.isnot(None),
            InventoryHistory.product_id.in_(stocked_ids),
        )
        .order_by(InventoryHistory.expiry_date)
        .all()
    )

    alerts = []
    seen = set()
    for r in rows:
        try:
            exp = date.fromisoformat(str(r.expiry_date)[:10])
        except (ValueError, TypeError):
            continue
        if exp > threshold:
            continue
        key = (r.product_id, str(exp))
        if key in seen:
            continue
        seen.add(key)
        alerts.append({
            "product_id":   r.product_id,
            "product_name": r.product.name if r.product else "",
            "lot_number":   r.lot_number or "",
            "expiry_date":  exp,
            "days_left":    (exp - today).days,
            "is_expired":   exp < today,
        })
    return alerts
