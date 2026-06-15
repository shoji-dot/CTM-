"""
routers/demo.py  -  デモ器台帳・貸出・修理管理
"""
from datetime import date, datetime, timedelta
from fastapi import APIRouter, Depends, Form, Request, HTTPException, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import or_
from collections import defaultdict

from database import get_db
from models import DemoUnit, DemoLoan, RepairRecord, Product, Customer
from notification_service import send_email as _send_email

def send_email(to_list: list[str], subject: str, html_body: str) -> bool:
    """notification_service.send_email に委譲（HTML形式）"""
    return _send_email(to_list, subject, subject, html_body=html_body)

router = APIRouter(prefix="/demo", tags=["demo"])
from templates_config import templates


# ──────────────────────────────────────────────
# ユーティリティ
# ──────────────────────────────────────────────

def _update_loan_statuses(db: Session):
    today = date.today()
    overdue_loans = (
        db.query(DemoLoan)
        .filter(DemoLoan.status == "on_loan", DemoLoan.due_date < today)
        .all()
    )
    for loan in overdue_loans:
        loan.status = "overdue"
        loan.demo_unit.status = "on_loan"
    if overdue_loans:
        db.commit()


def get_alert_counts(db: Session) -> dict:
    today = date.today()
    soon = today + timedelta(days=7)

    overdue = db.query(DemoLoan).filter(
        DemoLoan.status.in_(["on_loan", "overdue"]),
        DemoLoan.due_date < today
    ).count()
    due_soon = db.query(DemoLoan).filter(
        DemoLoan.status == "on_loan",
        DemoLoan.due_date >= today,
        DemoLoan.due_date <= soon
    ).count()

    from models import Shipment, ShipmentItem
    _demo_ship_ids = {r.shipment_id for r in db.query(ShipmentItem).filter(ShipmentItem.shipment_type == "demo").all()}
    ship_overdue = db.query(Shipment).filter(
        Shipment.id.in_(_demo_ship_ids),
        Shipment.status == "shipped",
        Shipment.return_due_date < today
    ).count() if _demo_ship_ids else 0
    ship_soon = db.query(Shipment).filter(
        Shipment.id.in_(_demo_ship_ids),
        Shipment.status == "shipped",
        Shipment.return_due_date >= today,
        Shipment.return_due_date <= soon
    ).count() if _demo_ship_ids else 0

    return {
        "demo_overdue": overdue + ship_overdue,
        "demo_due_soon": due_soon + ship_soon,
        "demo_total_alert": overdue + ship_overdue + due_soon + ship_soon,
    }


# ──────────────────────────────────────────────
# デモ器一覧
# ──────────────────────────────────────────────

@router.get("/", response_class=HTMLResponse)
def demo_list(request: Request, db: Session = Depends(get_db),
              status: str = "", q: str = "", page: int = 1):
    from crud import paginate
    _update_loan_statuses(db)

    query = db.query(DemoUnit).options(joinedload(DemoUnit.product))
    if status:
        query = query.filter(DemoUnit.status == status)
    if q:
        query = query.join(Product).filter(
            or_(DemoUnit.unit_code.contains(q),
                DemoUnit.serial_number.contains(q),
                Product.name.contains(q))
        )
    query = query.order_by(DemoUnit.id.desc())
    pagination = paginate(query, page=page, per_page=50)
    units = pagination.items

    today = date.today()
    soon = today + timedelta(days=7)
    alert_loans = db.query(DemoLoan).filter(
        DemoLoan.status.in_(["on_loan", "overdue"]),
        DemoLoan.due_date <= soon
    ).order_by(DemoLoan.due_date).all()

    from models import Shipment, ShipmentItem
    from sqlalchemy.orm import joinedload as _jl
    _ids = {r.shipment_id for r in db.query(ShipmentItem).filter(ShipmentItem.shipment_type == "demo").all()}
    alert_shipments = db.query(Shipment).options(
        _jl(Shipment.customer), _jl(Shipment.items)
    ).filter(
        Shipment.id.in_(_ids),
        Shipment.status == "shipped",
        Shipment.return_due_date <= soon
    ).order_by(Shipment.return_due_date).all() if _ids else []

    counts = get_alert_counts(db)

    return templates.TemplateResponse(request, "demo/list.html", {
        "units": units,
        "pagination": pagination,
        "alert_loans": alert_loans,
        "alert_shipments": alert_shipments,
        "today": today,
        "soon": soon,
        "status_filter": status,
        "q": q,
        **counts
    })


# ──────────────────────────────────────────────
# デモ器 登録・編集
# ──────────────────────────────────────────────

@router.get("/new", response_class=HTMLResponse)
def demo_new(request: Request, db: Session = Depends(get_db)):
    products = db.query(Product).order_by(Product.name).all()
    return templates.TemplateResponse(request, "demo/form.html", {
        "unit": None, "products": products
    })


def _gen_unit_code(db: Session) -> str:
    """DEMO-001 形式の連番を自動生成（既存の最大番号＋1）"""
    from sqlalchemy import func
    last = db.query(DemoUnit).filter(
        DemoUnit.unit_code.like("DEMO-%")
    ).order_by(DemoUnit.unit_code.desc()).first()
    if last:
        try:
            num = int(last.unit_code.split("-")[-1]) + 1
        except ValueError:
            num = db.query(func.count(DemoUnit.id)).scalar() + 1
    else:
        num = 1
    candidate = f"DEMO-{num:03d}"
    # 万が一重複する場合はインクリメント
    while db.query(DemoUnit).filter(DemoUnit.unit_code == candidate).first():
        num += 1
        candidate = f"DEMO-{num:03d}"
    return candidate


@router.post("/new")
def demo_create(
    request: Request,
    db: Session = Depends(get_db),
    product_id: int = Form(...),
    serial_number: str = Form(""),
    lot_number: str = Form(""),
    purchase_date: str = Form(""),
    location_type: str = Form("own"),
    location_name: str = Form("CTM本社"),
    notes: str = Form(""),
):
    unit_code = _gen_unit_code(db)
    unit = DemoUnit(
        unit_code=unit_code,
        product_id=product_id,
        serial_number=serial_number or None,
        lot_number=lot_number or None,
        purchase_date=date.fromisoformat(purchase_date) if purchase_date else None,
        location_type=location_type or "own",
        location_name=location_name or "CTM本社",
        notes=notes or None,
    )
    db.add(unit)
    db.commit()
    return RedirectResponse(f"/demo/{unit.id}", status_code=303)


@router.get("/{unit_id}/edit", response_class=HTMLResponse)
def demo_edit(unit_id: int, request: Request, db: Session = Depends(get_db)):
    unit = db.query(DemoUnit).filter(DemoUnit.id == unit_id).first()
    if not unit:
        raise HTTPException(404)
    products = db.query(Product).order_by(Product.name).all()
    return templates.TemplateResponse(request, "demo/form.html", {
        "unit": unit, "products": products
    })


@router.post("/{unit_id}/edit")
def demo_update(
    unit_id: int,
    db: Session = Depends(get_db),
    unit_code: str = Form(...),
    product_id: int = Form(...),
    serial_number: str = Form(""),
    lot_number: str = Form(""),
    purchase_date: str = Form(""),
    status: str = Form(...),
    location_type: str = Form("own"),
    location_name: str = Form("CTM本社"),
    notes: str = Form(""),
):
    unit = db.query(DemoUnit).filter(DemoUnit.id == unit_id).first()
    if not unit:
        raise HTTPException(404)
    unit.unit_code = unit_code
    unit.product_id = product_id
    unit.serial_number = serial_number or None
    unit.lot_number = lot_number or None
    unit.purchase_date = date.fromisoformat(purchase_date) if purchase_date else None
    unit.status = status
    unit.location_type = location_type or "own"
    unit.location_name = location_name or "CTM本社"
    unit.notes = notes or None
    db.commit()
    return RedirectResponse(f"/demo/{unit_id}", status_code=303)


# ──────────────────────────────────────────────
# デモ器詳細
# ──────────────────────────────────────────────

@router.get("/{unit_id}", response_class=HTMLResponse)
def demo_detail(unit_id: int, request: Request, db: Session = Depends(get_db)):
    _update_loan_statuses(db)
    unit = db.query(DemoUnit).filter(DemoUnit.id == unit_id).first()
    if not unit:
        raise HTTPException(404)
    today = date.today()
    active_loan = next(
        (l for l in unit.loans if l.status in ("on_loan", "overdue")), None
    )
    active_repair = next(
        (r for r in unit.repairs if r.status in ("pending", "in_repair")), None
    )
    internal_bases = db.query(Customer).filter(
        Customer.category == "internal_base"
    ).order_by(Customer.name).all()
    return templates.TemplateResponse(request, "demo/detail.html", {
        "unit": unit,
        "today": today,
        "active_loan": active_loan,
        "active_repair": active_repair,
        "internal_bases": internal_bases,
    })


# ──────────────────────────────────────────────
# 貸出登録
# ──────────────────────────────────────────────

@router.get("/{unit_id}/loan/new", response_class=HTMLResponse)
def loan_new(unit_id: int, request: Request, db: Session = Depends(get_db)):
    unit = db.query(DemoUnit).filter(DemoUnit.id == unit_id).first()
    if not unit:
        raise HTTPException(404)
    if unit.status not in ("available",):
        return RedirectResponse(f"/demo/{unit_id}?error=not_available", status_code=303)
    customers = db.query(Customer).order_by(Customer.name).all()
    today = date.today()
    default_due = today + timedelta(days=14)
    return templates.TemplateResponse(request, "demo/loan_form.html", {
        "unit": unit, "customers": customers,
        "today": today, "default_due": default_due
    })


@router.post("/{unit_id}/loan/new")
def loan_create(
    unit_id: int,
    db: Session = Depends(get_db),
    customer_id: int = Form(...),
    end_user_id: str = Form(""),
    loan_date: str = Form(...),
    due_date: str = Form(...),
    contact_name: str = Form(""),
    purpose: str = Form(""),
    condition_out: str = Form(""),
    staff_name: str = Form(""),
    notes: str = Form(""),
):
    unit = db.query(DemoUnit).filter(DemoUnit.id == unit_id).first()
    if not unit:
        raise HTTPException(404)

    end_user_id_val = int(end_user_id) if end_user_id else None

    loan = DemoLoan(
        demo_unit_id=unit_id,
        customer_id=customer_id,
        end_user_id=end_user_id_val,
        loan_date=date.fromisoformat(loan_date),
        due_date=date.fromisoformat(due_date),
        contact_name=contact_name or None,
        purpose=purpose or None,
        condition_out=condition_out or None,
        staff_name=staff_name or None,
        notes=notes or None,
        status="on_loan",
    )
    unit.status = "on_loan"
    # 所在地を取引先に自動更新
    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    unit.location_type = "customer"
    unit.location_name = customer.name if customer else ""
    db.add(loan)
    db.commit()
    return RedirectResponse(f"/demo/{unit_id}", status_code=303)


# ──────────────────────────────────────────────
# 返却登録
# ──────────────────────────────────────────────

@router.post("/{unit_id}/loan/{loan_id}/return")
def loan_return(
    unit_id: int,
    loan_id: int,
    db: Session = Depends(get_db),
    returned_date: str = Form(...),
    condition_in: str = Form(""),
    notes: str = Form(""),
    used: str = Form(None),
    return_destination_id: str = Form(""),
):
    loan = db.query(DemoLoan).filter(DemoLoan.id == loan_id).first()
    if not loan:
        raise HTTPException(404)
    loan.returned_date = date.fromisoformat(returned_date)
    loan.condition_in = condition_in or None
    loan.notes = (loan.notes or "") + ("\n返却備考: " + notes if notes else "")
    loan.status = "returned"
    loan.demo_unit.status = "available"

    # 返却先の所在地を設定（内部拠点選択時はその拠点名、未選択はCTM本社）
    dest_id = int(return_destination_id) if return_destination_id else None
    loan.return_destination_id = dest_id
    if dest_id:
        dest = db.query(Customer).filter(Customer.id == dest_id).first()
        loan.demo_unit.location_type = "own"
        loan.demo_unit.location_name = dest.name if dest else "CTM本社"
    else:
        loan.demo_unit.location_type = "own"
        loan.demo_unit.location_name = "CTM本社"

    # 使用回数カウント（チェックON=使用あり → +1、OFFは変化なし）
    if used == "on":
        loan.demo_unit.usage_count = (loan.demo_unit.usage_count or 0) + 1
    db.commit()
    return RedirectResponse(f"/demo/{unit_id}", status_code=303)


# ──────────────────────────────────────────────
# 故障・修理登録
# ──────────────────────────────────────────────

@router.get("/{unit_id}/repair/new", response_class=HTMLResponse)
def repair_new(unit_id: int, request: Request, db: Session = Depends(get_db)):
    unit = db.query(DemoUnit).filter(DemoUnit.id == unit_id).first()
    if not unit:
        raise HTTPException(404)
    return templates.TemplateResponse(request, "demo/repair_form.html", {
        "unit": unit, "repair": None,
        "today": date.today()
    })


@router.post("/{unit_id}/repair/new")
def repair_create(
    unit_id: int,
    db: Session = Depends(get_db),
    reported_date: str = Form(...),
    symptom: str = Form(...),
    cause: str = Form(""),
    repair_vendor: str = Form(""),
    repair_cost: str = Form(""),
    sent_date: str = Form(""),
    staff_name: str = Form(""),
    notes: str = Form(""),
):
    unit = db.query(DemoUnit).filter(DemoUnit.id == unit_id).first()
    if not unit:
        raise HTTPException(404)

    repair = RepairRecord(
        demo_unit_id=unit_id,
        reported_date=date.fromisoformat(reported_date),
        symptom=symptom,
        cause=cause or None,
        repair_vendor=repair_vendor or None,
        repair_cost=float(repair_cost) if repair_cost else None,
        sent_date=date.fromisoformat(sent_date) if sent_date else None,
        staff_name=staff_name or None,
        notes=notes or None,
        status="pending",
    )
    unit.status = "in_repair"
    db.add(repair)
    db.commit()
    return RedirectResponse(f"/demo/{unit_id}", status_code=303)


@router.get("/{unit_id}/repair/{repair_id}/edit", response_class=HTMLResponse)
def repair_edit(unit_id: int, repair_id: int, request: Request,
                db: Session = Depends(get_db)):
    unit = db.query(DemoUnit).filter(DemoUnit.id == unit_id).first()
    repair = db.query(RepairRecord).filter(RepairRecord.id == repair_id).first()
    if not unit or not repair:
        raise HTTPException(404)
    return templates.TemplateResponse(request, "demo/repair_form.html", {
        "unit": unit, "repair": repair,
        "today": date.today()
    })


@router.post("/{unit_id}/repair/{repair_id}/edit")
def repair_update(
    unit_id: int,
    repair_id: int,
    db: Session = Depends(get_db),
    reported_date: str = Form(...),
    symptom: str = Form(...),
    cause: str = Form(""),
    repair_vendor: str = Form(""),
    repair_cost: str = Form(""),
    sent_date: str = Form(""),
    repaired_date: str = Form(""),
    status: str = Form(...),
    staff_name: str = Form(""),
    notes: str = Form(""),
):
    repair = db.query(RepairRecord).filter(RepairRecord.id == repair_id).first()
    unit = db.query(DemoUnit).filter(DemoUnit.id == unit_id).first()
    if not repair or not unit:
        raise HTTPException(404)

    repair.reported_date = date.fromisoformat(reported_date)
    repair.symptom = symptom
    repair.cause = cause or None
    repair.repair_vendor = repair_vendor or None
    repair.repair_cost = float(repair_cost) if repair_cost else None
    repair.sent_date = date.fromisoformat(sent_date) if sent_date else None
    repair.repaired_date = date.fromisoformat(repaired_date) if repaired_date else None
    repair.status = status
    repair.staff_name = staff_name or None
    repair.notes = notes or None

    if status == "completed":
        unit.status = "available"
    elif status == "scrapped":
        unit.status = "retired"

    db.commit()
    return RedirectResponse(f"/demo/{unit_id}", status_code=303)


# ──────────────────────────────────────────────
# 修理ウィザード ステップ別エンドポイント
# ──────────────────────────────────────────────

@router.post("/{unit_id}/repair/{repair_id}/step-send")
def repair_step_send(
    unit_id: int, repair_id: int,
    db: Session = Depends(get_db),
    repair_vendor: str = Form(""),
    sent_date: str = Form(...),
):
    """ステップ2: メーカーへ送付完了"""
    repair = db.query(RepairRecord).filter(RepairRecord.id == repair_id).first()
    unit = db.query(DemoUnit).filter(DemoUnit.id == unit_id).first()
    if not repair or not unit:
        raise HTTPException(404)
    if repair_vendor:
        repair.repair_vendor = repair_vendor
    repair.sent_date = date.fromisoformat(sent_date)
    repair.status = "in_repair"
    unit.location_type = "maker"
    unit.location_name = repair_vendor or "製造元"
    db.commit()
    return RedirectResponse(f"/demo/{unit_id}", status_code=303)


@router.post("/{unit_id}/repair/{repair_id}/step-complete")
def repair_step_complete(
    unit_id: int, repair_id: int,
    db: Session = Depends(get_db),
    repaired_date: str = Form(...),
    repair_cost: str = Form(""),
    notes: str = Form(""),
):
    """ステップ3a: 修理完了・デモ器を貸出可に戻す"""
    repair = db.query(RepairRecord).filter(RepairRecord.id == repair_id).first()
    unit = db.query(DemoUnit).filter(DemoUnit.id == unit_id).first()
    if not repair or not unit:
        raise HTTPException(404)
    repair.repaired_date = date.fromisoformat(repaired_date)
    repair.repair_cost = float(repair_cost) if repair_cost else None
    if notes:
        repair.notes = (repair.notes or "") + "\n" + notes
    repair.status = "completed"
    unit.status = "available"
    unit.location_type = "own"
    unit.location_name = "CTM本社"
    db.commit()
    return RedirectResponse(f"/demo/{unit_id}", status_code=303)


@router.post("/{unit_id}/repair/{repair_id}/step-scrap")
def repair_step_scrap(
    unit_id: int, repair_id: int,
    db: Session = Depends(get_db),
    notes: str = Form(""),
):
    """ステップ3b: 修理不能・廃棄決定"""
    repair = db.query(RepairRecord).filter(RepairRecord.id == repair_id).first()
    unit = db.query(DemoUnit).filter(DemoUnit.id == unit_id).first()
    if not repair or not unit:
        raise HTTPException(404)
    repair.status = "scrapped"
    if notes:
        repair.notes = (repair.notes or "") + "\n廃棄理由: " + notes
    unit.status = "retired"
    db.commit()
    return RedirectResponse(f"/demo/{unit_id}", status_code=303)


# ──────────────────────────────────────────────
# 廃棄登録
# ──────────────────────────────────────────────

@router.post("/{unit_id}/retire")
def demo_retire(
    unit_id: int,
    db: Session = Depends(get_db),
    retire_reason: str = Form(...),
    retire_notes: str = Form(""),
):
    unit = db.query(DemoUnit).filter(DemoUnit.id == unit_id).first()
    if not unit:
        raise HTTPException(404)
    unit.status = "retired"
    note_text = f"廃棄理由: {retire_reason}"
    if retire_notes:
        note_text += f"\n{retire_notes}"
    unit.notes = (unit.notes + "\n" if unit.notes else "") + note_text
    db.commit()
    return RedirectResponse(f"/demo/{unit_id}", status_code=303)


# ──────────────────────────────────────────────
# デモ器削除（個別・一括）
# ──────────────────────────────────────────────

@router.post("/{unit_id}/delete")
def demo_delete(unit_id: int, request: Request, db: Session = Depends(get_db)):
    staff = request.state.staff
    if not staff or staff.get("role") not in ("admin", "manager"):
        return RedirectResponse("/demo/?error=権限がありません", status_code=303)
    unit = db.query(DemoUnit).filter(DemoUnit.id == unit_id).first()
    if not unit:
        raise HTTPException(404)
    db.delete(unit)
    db.commit()
    return RedirectResponse("/demo/", status_code=303)


@router.post("/bulk-delete")
async def demo_bulk_delete(request: Request, db: Session = Depends(get_db)):
    staff = request.state.staff
    if not staff or staff.get("role") not in ("admin", "manager"):
        return JSONResponse({"error": "権限がありません"}, status_code=403)
    body = await request.json()
    ids = body.get("ids", [])
    deleted = 0
    errors = []
    for uid in ids:
        unit = db.query(DemoUnit).filter(DemoUnit.id == int(uid)).first()
        if unit:
            try:
                db.delete(unit)
                deleted += 1
            except Exception as e:
                errors.append(f"ID {uid}: {str(e)}")
    db.commit()
    return JSONResponse({"deleted": deleted, "errors": errors})


# ──────────────────────────────────────────────
# アラートメール送信
# ──────────────────────────────────────────────

@router.post("/csv-import")
async def demo_csv_import(
    request: Request,
    db: Session = Depends(get_db),
    file: UploadFile = File(...),
):
    """CSVで複数デモ器を一括登録。
    フォーマット（ヘッダー行あり）:
      製品名,型番,シリアル番号,ロット番号,数量,登録日,備考
    製品名・型番（SKU）どちらかで製品マスタを照合します。
    数量が2以上の場合、同じロット・製品で複数のDemoUnitを生成します。
    """
    import csv, io

    content = await file.read()
    try:
        text = content.decode("utf-8-sig")  # BOM付きUTF-8も対応
    except UnicodeDecodeError:
        text = content.decode("shift_jis", errors="replace")

    reader = csv.DictReader(io.StringIO(text))

    # 製品名→ID、SKU→IDの2つのマップを用意
    products = db.query(Product).all()
    prod_map_name = {p.name: p.id for p in products}
    prod_map_sku  = {p.sku: p.id for p in products if p.sku}

    ok_count = 0
    errors = []

    for i, row in enumerate(reader, start=2):  # 2行目から（1行目はヘッダー）
        product_name = (row.get("製品名") or "").strip()
        model_number = (row.get("型番") or "").strip()
        serial = (row.get("シリアル番号") or "").strip()
        lot = (row.get("ロット番号") or "").strip()
        qty_str = (row.get("数量") or "1").strip()
        date_str = (row.get("登録日") or "").strip()
        notes = (row.get("備考") or "").strip()

        try:
            qty = max(1, int(qty_str))
        except ValueError:
            qty = 1

        if not product_name and not model_number:
            errors.append(f"行{i}: 製品名または型番を入力してください")
            continue

        # 型番(SKU)が指定されていればSKU優先、なければ製品名で照合
        if model_number:
            product_id = prod_map_sku.get(model_number)
        if not product_id:
            product_id = prod_map_name.get(product_name)
        if not product_id:
            label = product_name or model_number
            errors.append(f"行{i}: 製品「{label}」が見つかりません（製品名・型番を確認してください）")
            continue

        purchase_date = None
        if date_str:
            for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y/%m/%d", "%Y.%m.%d",
                        "%Y-%m-%d", "%y-%m-%d", "%y/%m/%d"):
                try:
                    purchase_date = datetime.strptime(date_str, fmt).date()
                    break
                except ValueError:
                    continue
            if purchase_date is None:
                errors.append(f"行{i}: 登録日の形式が不正です（例: 2026-06-11 または 2026/6/11）: {date_str}")
                continue

        row_error = False
        for n in range(qty):
            unit_code = _gen_unit_code(db)
            unit = DemoUnit(
                unit_code=unit_code,
                product_id=product_id,
                serial_number=serial or None,
                lot_number=lot or None,
                purchase_date=purchase_date,
                notes=notes or None,
            )
            db.add(unit)
            try:
                db.flush()
                ok_count += 1
            except Exception as e:
                db.rollback()
                errors.append(f"行{i}({n+1}台目): DB登録エラー: {e}")
                row_error = True
                break
        if row_error:
            continue

    db.commit()
    return JSONResponse({"ok": ok_count, "errors": errors})


@router.post("/send-alert-emails")
def send_alert_emails(db: Session = Depends(get_db)):
    today     = date.today()
    threshold = today + timedelta(days=7)

    loans = (
        db.query(DemoLoan)
        .join(DemoLoan.customer)
        .filter(
            DemoLoan.returned_date == None,
            DemoLoan.due_date <= threshold,
        )
        .all()
    )

    if not loans:
        return RedirectResponse(
            url="/demo/?mail_sent=0&mail_no_staff=0&mail_type=info",
            status_code=303
        )

    grouped: dict[int, list] = defaultdict(list)
    no_staff_loans = []

    for loan in loans:
        staff = loan.customer.staff if loan.customer else None
        if staff and staff.email:
            grouped[staff.id].append((staff, loan))
        else:
            no_staff_loans.append(loan)

    sent_count = 0
    errors = []

    for staff_id, items in grouped.items():
        staff        = items[0][0]
        target_loans = [item[1] for item in items]
        subject      = f"【デモ器返却アラート】担当案件 {len(target_loans)}件の返却期限をご確認ください"
        html_body    = _build_alert_html(staff.name, target_loans, today)
        try:
            send_email([staff.email], subject, html_body)
            sent_count += 1
        except Exception as e:
            errors.append(f"{staff.name}: {str(e)}")
           

    import urllib.parse
    error_msg = urllib.parse.quote("; ".join(errors)) if errors else ""
    return RedirectResponse(
        url=f"/demo/?mail_sent={sent_count}&mail_no_staff={len(no_staff_loans)}&mail_type={mail_type}",
        status_code=303,
    )
