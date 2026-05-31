from datetime import date
from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from database import get_db
import crud
import company_config

router = APIRouter()
templates = Jinja2Templates(directory="templates")

SHIPMENT_TYPES = {
    "sale": "販売",
    "demo": "デモ貸出",
    "sample": "サンプル",
    "repair": "修理代替品",
}

company_info = {
    "name": company_config.COMPANY_NAME,
    "postal": company_config.COMPANY_POSTAL,
    "address": company_config.COMPANY_ADDRESS,
    "tel": company_config.COMPANY_TEL,
    "fax": company_config.COMPANY_FAX,
    "invoice_no": company_config.COMPANY_INVOICE_NO,
}

@router.get("/shipments", response_class=HTMLResponse)
def list_shipments(request: Request, status: str = "", shipment_type: str = "",
                   q: str = "", serial: str = "", lot: str = "",
                   db: Session = Depends(get_db)):
    shipments = crud.get_shipments(db, status=status, shipment_type=shipment_type,
                                   q_text=q, serial=serial, lot=lot)
    return templates.TemplateResponse("shipments/list.html", {
        "request": request, "shipments": shipments,
        "status": status, "shipment_type": shipment_type,
        "q": q, "serial": serial, "lot": lot,
        "shipment_types": SHIPMENT_TYPES,
    })

@router.get("/api/inventory-items", response_class=JSONResponse)
def api_inventory_items(q: str = "", product_id: int = None, db: Session = Depends(get_db)):
    """在庫入庫履歴から検索（販売・サンプル用）"""
    items = crud.search_inventory_items(db, q=q, product_id=product_id)
    return [
        {
            "product_id": i.product_id,
            "product_name": i.product.name,
            "serial_number": i.serial_number or "",
            "lot_number": i.lot_number or "",
            "expiry_date": i.expiry_date or "",
            "moved_at": i.moved_at.strftime("%Y-%m-%d") if i.moved_at else "",
        }
        for i in items
    ]

@router.get("/api/demo-units", response_class=JSONResponse)
def api_demo_units(q: str = "", product_id: int = None, db: Session = Depends(get_db)):
    """デモ器台帳から検索（デモ貸出・修理代替品用）"""
    units = crud.search_demo_units(db, q=q, product_id=product_id)
    STATUS_LABEL = {"available": "貸出可", "on_loan": "貸出中", "in_repair": "修理中", "retired": "廃棄"}
    return [
        {
            "id": u.id,
            "unit_code": u.unit_code,
            "product_id": u.product_id,
            "product_name": u.product.name,
            "serial_number": u.serial_number or "",
            "status": u.status,
            "status_label": STATUS_LABEL.get(u.status, u.status),
        }
        for u in units
    ]

@router.get("/shipments/new", response_class=HTMLResponse)
def new_shipment_form(request: Request, error: str = "", db: Session = Depends(get_db)):
    customers = crud.get_customers(db)
    products = crud.get_products(db)
    today = date.today().isoformat()
    return templates.TemplateResponse("shipments/form.html", {
        "request": request, "customers": customers, "products": products,
        "shipment_types": SHIPMENT_TYPES, "today": today, "shipment": None,
        "error": error,
    })

@router.post("/shipments/new")
async def create_shipment(request: Request, db: Session = Depends(get_db)):
    form_data = await request.form()
    shipment_type = form_data.get("shipment_type")
    serial_number = form_data.get("serial_number") or None
    lot_number = form_data.get("lot_number") or None

    def redirect_error(msg: str):
        from urllib.parse import quote
        return RedirectResponse(f"/shipments/new?error={quote(msg)}", status_code=303)

    # ── バリデーション ──────────────────────────────────────
    product_id_str = form_data.get("product_id", "")
    if not product_id_str:
        return redirect_error("商品を選択してください。")
    product_id = int(product_id_str)

    if shipment_type in ("sale", "sample"):
        # シリアル/ロットが入力されている場合は在庫履歴に存在するか確認
        if serial_number or lot_number:
            if not crud.validate_inventory_item(db, product_id, serial_number, lot_number):
                label = f"シリアル番号「{serial_number}」" if serial_number else f"ロット番号「{lot_number}」"
                return redirect_error(f"{label}は在庫台帳に登録されていません。")
    elif shipment_type in ("demo", "repair"):
        # シリアル番号がデモ器台帳に存在するか確認
        if not serial_number:
            return redirect_error("デモ器・修理代替品はシリアル番号の選択が必要です。")
        if not crud.validate_demo_unit_exists(db, product_id, serial_number):
            return redirect_error(f"シリアル番号「{serial_number}」はデモ器台帳に登録されていません。")

    # ── 登録 ───────────────────────────────────────────────
    shipped_date_str = form_data.get("shipped_date", "")
    return_due_date_str = form_data.get("return_due_date", "")
    expiry_date_str = form_data.get("expiry_date", "")
    end_user_id_str = form_data.get("end_user_id", "")
    data = {
        "shipment_type": shipment_type,
        "customer_id": int(form_data.get("customer_id")),
        "end_user_id": int(end_user_id_str) if end_user_id_str else None,
        "product_id": product_id,
        "quantity": int(form_data.get("quantity", 1)),
        "serial_number": serial_number,
        "lot_number": lot_number,
        "expiry_date": date.fromisoformat(expiry_date_str) if expiry_date_str else None,
        "shipped_date": date.fromisoformat(shipped_date_str) if shipped_date_str else date.today(),
        "return_due_date": date.fromisoformat(return_due_date_str) if return_due_date_str else None,
        "notes": form_data.get("notes") or None,
    }
    crud.create_shipment(db, data)
    return RedirectResponse("/shipments", status_code=303)

@router.get("/shipments/{shipment_id}/edit", response_class=HTMLResponse)
def edit_shipment_form(shipment_id: int, request: Request, db: Session = Depends(get_db)):
    shipment = crud.get_shipment(db, shipment_id)
    customers = crud.get_customers(db)
    products = crud.get_products(db)
    today = date.today().isoformat()
    return templates.TemplateResponse("shipments/form.html", {
        "request": request, "shipment": shipment,
        "customers": customers, "products": products,
        "shipment_types": SHIPMENT_TYPES, "today": today,
        "error": "",
    })

@router.post("/shipments/{shipment_id}/edit")
async def update_shipment(shipment_id: int, request: Request, db: Session = Depends(get_db)):
    form_data = await request.form()
    shipped_date_str = form_data.get("shipped_date", "")
    return_due_date_str = form_data.get("return_due_date", "")
    expiry_date_str = form_data.get("expiry_date", "")
    end_user_id_str = form_data.get("end_user_id", "")
    data = {
        "end_user_id": int(end_user_id_str) if end_user_id_str else None,
        "serial_number": form_data.get("serial_number") or None,
        "lot_number": form_data.get("lot_number") or None,
        "expiry_date": date.fromisoformat(expiry_date_str) if expiry_date_str else None,
        "shipped_date": date.fromisoformat(shipped_date_str) if shipped_date_str else date.today(),
        "return_due_date": date.fromisoformat(return_due_date_str) if return_due_date_str else None,
        "notes": form_data.get("notes") or None,
    }
    crud.update_shipment(db, shipment_id, data)
    return RedirectResponse(f"/shipments/{shipment_id}", status_code=303)

@router.get("/shipments/{shipment_id}", response_class=HTMLResponse)
def detail_shipment(shipment_id: int, request: Request, db: Session = Depends(get_db)):
    shipment = crud.get_shipment(db, shipment_id)
    today = date.today().isoformat()
    return templates.TemplateResponse("shipments/detail.html", {
        "request": request, "shipment": shipment,
        "shipment_types": SHIPMENT_TYPES, "today": today,
        "company": company_info,
    })

@router.post("/shipments/{shipment_id}/return")
async def return_shipment(shipment_id: int, request: Request, db: Session = Depends(get_db)):
    form_data = await request.form()
    returned_date_str = form_data.get("returned_date", "")
    returned_date = date.fromisoformat(returned_date_str) if returned_date_str else date.today()
    crud.return_shipment(db, shipment_id, returned_date)
    return RedirectResponse(f"/shipments/{shipment_id}", status_code=303)

@router.post("/shipments/{shipment_id}/complete")
def complete_shipment(shipment_id: int, db: Session = Depends(get_db)):
    crud.complete_shipment(db, shipment_id)
    return RedirectResponse(f"/shipments/{shipment_id}", status_code=303)
