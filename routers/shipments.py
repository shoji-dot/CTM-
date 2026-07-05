import json
from datetime import date
from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from sqlalchemy.orm import Session
from database import get_db
import crud
import company_config

router = APIRouter()
from templates_config import templates

SHIPMENT_TYPES = {
    "sale":       "販売",
    "demo":       "デモ貸出",
    "sample":     "サンプル",
    "repair_sub": "修理代替品",
}

company_info = {
    "name":       company_config.COMPANY_NAME,
    "postal":     company_config.COMPANY_POSTAL,
    "address":    company_config.COMPANY_ADDRESS,
    "tel":        company_config.COMPANY_TEL,
    "fax":        company_config.COMPANY_FAX,
    "invoice_no": company_config.COMPANY_INVOICE_NO,
}


# ── 在庫検索API ────────────────────────────────────────────
@router.get("/api/inventory-items", response_class=JSONResponse)
def api_inventory_items(q: str = "", product_id: int = None, db: Session = Depends(get_db)):
    items = crud.search_inventory_items(db, q=q, product_id=product_id)
    return [
        {
            "product_id": i.product_id,
            "product_name": i.product.name,
            "serial_number": i.serial_number or "",
            "lot_number": i.lot_number or "",
            "expiry_date": str(i.expiry_date) if i.expiry_date else "",
            "moved_at": i.moved_at.strftime("%Y-%m-%d") if i.moved_at else "",
        }
        for i in items
    ]


# ── デモ器検索API ──────────────────────────────────────────
@router.get("/api/demo-units", response_class=JSONResponse)
def api_demo_units(q: str = "", product_id: int = None, db: Session = Depends(get_db)):
    units = crud.search_demo_units(db, q=q, product_id=product_id)
    STATUS_LABEL = {"available": "貸出可", "on_loan": "貸出中",
                    "in_repair": "修理中", "retired": "廃棄"}
    return [
        {
            "id": u.id,
            "unit_code": u.unit_code,
            "product_id": u.product_id,
            "product_name": u.product.name,
            "sku": u.product.sku or "",
            "serial_number": u.serial_number or "",
            "lot_number": u.lot_number or "",
            "status": u.status,
            "status_label": STATUS_LABEL.get(u.status, u.status),
        }
        for u in units
    ]


# ── 一覧 ───────────────────────────────────────────────────
@router.get("/shipments", response_class=HTMLResponse)
def list_shipments(request: Request, status: str = "", shipment_type: str = "",
                   q: str = "", serial: str = "", lot: str = "",
                   page: int = 1, db: Session = Depends(get_db)):
    shipments_query = crud.get_shipments_query(db, status=status, shipment_type=shipment_type,
                                               q_text=q, serial=serial, lot=lot)
    pagination = crud.paginate(shipments_query, page=page, per_page=50)
    return templates.TemplateResponse(request, "shipments/list.html", {
        "shipments": pagination.items,
        "pagination": pagination,
        "status": status, "shipment_type": shipment_type,
        "q": q, "serial": serial, "lot": lot,
        "shipment_types": SHIPMENT_TYPES,
    })


# ── 新規登録フォーム ───────────────────────────────────────
@router.get("/shipments/new", response_class=HTMLResponse)
def new_shipment_form(request: Request, error: str = "", db: Session = Depends(get_db)):
    customers = crud.get_customers(db)
    today = date.today().isoformat()
    return templates.TemplateResponse(request, "shipments/form.html", {
        "customers": customers,
        "shipment_types": SHIPMENT_TYPES,
        "today": today,
        "shipment": None,
        "error": error,
    })


# ── 登録POST ───────────────────────────────────────────────
@router.post("/shipments/new")
async def create_shipment(request: Request, db: Session = Depends(get_db)):
    form_data = await request.form()

    def redirect_error(msg: str):
        from urllib.parse import quote
        return RedirectResponse(f"/shipments/new?error={quote(msg)}", status_code=303)

    # ヘッダー
    customer_id_str = form_data.get("customer_id", "")
    if not customer_id_str:
        return redirect_error("取引先を選択してください。")
    shipped_date_str  = form_data.get("shipped_date", "")
    return_due_str    = form_data.get("return_due_date", "")
    end_user_id_str   = form_data.get("end_user_id", "")

    header = {
        "customer_id":    int(customer_id_str),
        "end_user_id":    int(end_user_id_str) if end_user_id_str else None,
        "shipped_date":   date.fromisoformat(shipped_date_str) if shipped_date_str else date.today(),
        "return_due_date": date.fromisoformat(return_due_str) if return_due_str else None,
        "contact_name":      form_data.get("contact_name") or None,
        "end_user_contact":  form_data.get("end_user_contact") or None,
        "notes":             form_data.get("notes") or None,
        "staff_name":        form_data.get("staff_name") or None,
    }

    # 明細（JSON配列で受け取る）
    items_json = form_data.get("items_json", "[]")
    try:
        raw_items = json.loads(items_json)
    except Exception:
        return redirect_error("明細データが不正です。")

    if not raw_items:
        return redirect_error("明細を1行以上追加してください。")

    has_demo_or_repair = any(
        it.get("shipment_type") in ("demo", "repair_sub") for it in raw_items
    )
    if has_demo_or_repair and not return_due_str:
        return redirect_error("デモ貸出・修理代替品が含まれる場合、返却期限を入力してください。")

    items = []
    for idx, it in enumerate(raw_items, start=1):
        pid = it.get("product_id")
        if not pid:
            return redirect_error(f"{idx}行目: 商品を選択してください。")
        stype = it.get("shipment_type", "sale")
        exp_str = it.get("expiry_date", "")
        items.append({
            "shipment_type": stype,
            "product_id":    int(pid),
            "quantity":      int(it.get("quantity", 1)),
            "serial_number": it.get("serial_number") or None,
            "lot_number":    it.get("lot_number") or None,
            "expiry_date":   date.fromisoformat(exp_str) if exp_str else None,
            "demo_unit_id":  int(it["demo_unit_id"]) if it.get("demo_unit_id") else None,
        })

    # NOTE: デモ器購入日 <= 出荷日 のバリデーションは意図的に未実装。
    # 運用上の矛盾は認識済みだが、制約の必要性が確定するまで追加しない。(2026-06-12)
    try:
        crud.create_shipment(db, header, items)
    except Exception as e:
        return redirect_error(f"登録エラー: {type(e).__name__}: {str(e)[:200]}")
    return RedirectResponse("/shipments", status_code=303)


# ── 詳細 ───────────────────────────────────────────────────
@router.get("/shipments/{shipment_id}", response_class=HTMLResponse)
def detail_shipment(shipment_id: int, request: Request, db: Session = Depends(get_db)):
    shipment = crud.get_shipment(db, shipment_id)
    today = date.today().isoformat()
    return templates.TemplateResponse(request, "shipments/detail.html", {
        "shipment":       shipment,
        "shipment_types": SHIPMENT_TYPES,
        "today":          today,
        "company":        company_info,
    })


# ── 出荷伝票 印刷ビュー ─────────────────────────────────────
@router.get("/shipments/{shipment_id}/print", response_class=HTMLResponse)
def print_shipment(shipment_id: int, request: Request, db: Session = Depends(get_db)):
    shipment = crud.get_shipment(db, shipment_id)
    return templates.TemplateResponse(request, "shipments/detail_print.html", {
        "shipment":       shipment,
        "shipment_types": SHIPMENT_TYPES,
        "today":          date.today().isoformat(),
        "company":        company_info,
    })


# ── 返却登録 ──────────────────────────────────────────────
@router.post("/shipments/{shipment_id}/return")
async def return_shipment(shipment_id: int, request: Request, db: Session = Depends(get_db)):
    form_data = await request.form()
    returned_date_str = form_data.get("returned_date", "")
    returned_date = date.fromisoformat(returned_date_str) if returned_date_str else date.today()
    crud.return_shipment(db, shipment_id, returned_date)
    return RedirectResponse(f"/shipments/{shipment_id}", status_code=303)


# ── 完了 ──────────────────────────────────────────────────
@router.post("/shipments/{shipment_id}/complete")
def complete_shipment(shipment_id: int, db: Session = Depends(get_db)):
    crud.complete_shipment(db, shipment_id)
    return RedirectResponse(f"/shipments/{shipment_id}", status_code=303)


# ── 削除 ──────────────────────────────────────────────
@router.post("/shipments/{shipment_id}/delete")
def delete_shipment(shipment_id: int, db: Session = Depends(get_db)):
    crud.delete_shipment(db, shipment_id)
    return RedirectResponse("/shipments", status_code=303)
