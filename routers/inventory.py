from datetime import date
from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from database import get_db
import crud

router = APIRouter()
from templates_config import templates

DISPOSAL_REASONS = {
    "failure": "故障",
    "expired": "有効期限切れ",
    "damage": "破損",
    "lost": "紛失",
    "other": "その他",
}


@router.get("/inventory", response_class=HTMLResponse)
def list_inventory(request: Request, db: Session = Depends(get_db)):
    inventory = crud.get_inventory_list(db)
    alerts = crud.get_alerts(db)
    alert_ids = {a.product_id for a in alerts}
    return templates.TemplateResponse(request, "inventory/list.html", {
        "inventory": inventory, "alert_ids": alert_ids
    })


@router.get("/inventory/history", response_class=HTMLResponse)
def history(request: Request,
            product_id: str = "",
            movement_type: str = "",
            date_from: str = "",
            date_to: str = "",
            staff_name: str = "",
            customer: str = "",
            db: Session = Depends(get_db)):
    histories = crud.get_inventory_history_filtered(
        db,
        product_id=int(product_id) if product_id else None,
        movement_type=movement_type,
        date_from=date.fromisoformat(date_from) if date_from else None,
        date_to=date.fromisoformat(date_to) if date_to else None,
        staff_name=staff_name,
        customer=customer,
    )
    products = crud.get_products(db)
    return templates.TemplateResponse(request, "inventory/history.html", {
        "histories": histories,
        "products": products,
        "product_id": product_id,
        "movement_type": movement_type,
        "date_from": date_from,
        "date_to": date_to,
        "staff_name": staff_name,
        "customer": customer
    })


@router.get("/inventory/receive", response_class=HTMLResponse)
def receive_form(request: Request, db: Session = Depends(get_db)):
    products = crud.get_products(db)
    today = date.today().isoformat()
    return templates.TemplateResponse(request, "inventory/receive.html", {
        "products": products, "today": today
    })


@router.post("/inventory/receive")
async def register_receive(request: Request, db: Session = Depends(get_db)):
    form_data = await request.form()
    product_id = int(form_data.get("product_id"))
    quantity = int(form_data.get("quantity", 1))
    serial_number = form_data.get("serial_number") or None
    lot_number = form_data.get("lot_number") or None
    expiry_date_str = form_data.get("expiry_date") or None
    note = form_data.get("note") or ""
    reason = form_data.get("reason") or "入荷"
    staff = getattr(request.state, "staff", None)
    staff_name = staff["name"] if staff else None
    crud.move_inventory(
        db, product_id, "in", quantity,
        reason=reason,
        note=note,
        serial_number=serial_number,
        lot_number=lot_number,
        expiry_date=expiry_date_str,
        staff_name=staff_name,
    )
    return RedirectResponse("/inventory/receive?done=1", status_code=303)


@router.post("/inventory/move")
async def move_inventory(request: Request, db: Session = Depends(get_db)):
    form_data = await request.form()
    product_id = int(form_data.get("product_id"))
    movement_type = form_data.get("movement_type")
    quantity = int(form_data.get("quantity", 1))
    reason = form_data.get("reason") or ""
    note = form_data.get("note") or ""
    staff = getattr(request.state, "staff", None)
    staff_name = staff["name"] if staff else None
    try:
        crud.move_inventory(db, product_id, movement_type, quantity,
                            reason=reason, note=note, staff_name=staff_name)
    except ValueError as e:
        products = crud.get_products(db)
        return templates.TemplateResponse(request, "inventory/move.html", {
        "products": products, "error": str(e)
    })
    return RedirectResponse("/inventory", status_code=303)


@router.get("/inventory/disposal", response_class=HTMLResponse)
def disposal_form(request: Request, db: Session = Depends(get_db)):
    products = crud.get_products(db)
    return templates.TemplateResponse(request, "inventory/disposal.html", {
        "products": products,
        "disposal_reasons": DISPOSAL_REASONS
    })


@router.post("/inventory/disposal")
async def register_disposal(request: Request, db: Session = Depends(get_db)):
    form_data = await request.form()
    product_id = int(form_data.get("product_id"))
    quantity = int(form_data.get("quantity", 1))
    reason_code = form_data.get("reason_code")
    serial_lot = form_data.get("serial_lot") or ""
    note = form_data.get("note") or ""
    reason_label = DISPOSAL_REASONS.get(reason_code, "廃棄")
    full_note = f"廃棄理由：{reason_label}"
    if serial_lot:
        full_note += f" / シリアル・ロット：{serial_lot}"
    if note:
        full_note += f" / 備考：{note}"
    staff = getattr(request.state, "staff", None)
    staff_name = staff["name"] if staff else None
    staff_name = staff["name"] if staff else None
    crud.move_inventory(
        db, product_id, "out", quantity,
        reason=f"廃棄：{reason_label}", note=full_note, staff_name=staff_name,
        allow_negative=True,  # [I5] 廃棄は在庫不足でも記録を許可
    )
    return RedirectResponse("/inventory/disposal?done=1", status_code=303)
