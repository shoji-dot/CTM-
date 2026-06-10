import os
from utils import now_jst
from datetime import date, datetime, timedelta
from fastapi import APIRouter, Request, Form, HTTPException, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session, joinedload
from database import get_db
from models import Repair, Customer, Product, Shipment
import company_config

from templates_config import templates as TEMPLATES
router = APIRouter(prefix="/repairs", tags=["repairs"])

COMPANY_INFO = {
    "name": company_config.COMPANY_NAME,
    "postal": company_config.COMPANY_POSTAL,
    "address": company_config.COMPANY_ADDRESS,
    "tel": company_config.COMPANY_TEL,
    "fax": company_config.COMPANY_FAX,
    "invoice_no": company_config.COMPANY_INVOICE_NO,
}

STATUS_LABELS = {
    "received":        "受付済",
    "inspecting":      "自社点検中",
    "sent_to_maker":   "メーカー送付済",
    "maker_responded": "メーカー回答済",
    "quote_submitted": "見積提出済",
    "repair_ordered":  "修理発注済",
    "repair_completed":"修理完了",
    "closed":          "クロージング",
}

NEXT_STATUS = {
    "received":        "inspecting",
    "inspecting":      "sent_to_maker",
    "sent_to_maker":   "maker_responded",
    "maker_responded": "quote_submitted",
    "quote_submitted": "repair_ordered",
    "repair_ordered":  "repair_completed",
    "repair_completed":"closed",
}

def _staff(request: Request):
    staff = getattr(request.state, "staff", None)
    if staff is None:
        raise HTTPException(status_code=401)
    return staff

def _require_manager(staff: dict):
    """manager / admin のみ許可。それ以外は 403。"""
    if staff.get("role") not in ("admin", "manager"):
        raise HTTPException(status_code=403, detail="この操作には管理者権限が必要です")

def _gen_repair_number(db: Session):
    prefix = f"REP-{now_jst().strftime('%Y%m')}-"
    row = db.query(Repair).filter(Repair.repair_number.like(f"{prefix}%")).order_by(Repair.id.desc()).first()
    seq = int(row.repair_number.split("-")[-1]) + 1 if row else 1
    return f"{prefix}{seq:04d}"


# ── 一覧 ──────────────────────────────────────────────────
@router.get("/", response_class=HTMLResponse)
async def repair_list(request: Request, status: str = "", q: str = "", db: Session = Depends(get_db)):
    _staff(request)
    query = db.query(Repair).options(
        joinedload(Repair.customer),
        joinedload(Repair.end_user),
        joinedload(Repair.product),
    )
    if status:
        query = query.filter(Repair.status == status)
    if q:
        from sqlalchemy import or_
        like = f"%{q}%"
        query = query.filter(or_(
            Repair.repair_number.ilike(like),
            Repair.serial_number.ilike(like),
        ))
    repairs_raw = query.order_by(Repair.id.desc()).all()
    today = date.today().isoformat()
    repairs = []
    for r in repairs_raw:
        d = {c.name: getattr(r, c.name) for c in r.__table__.columns}
        d["customer_name"]  = r.customer.name if r.customer else ""
        d["end_user_name"]  = r.end_user.name if r.end_user else ""
        d["product_name"]   = r.product.name if r.product else ""
        dl = d.get("step_deadline")
        dl_str = dl.isoformat() if dl else None
        d["step_deadline"]  = dl_str
        d["is_overdue"] = bool(dl_str and dl_str < today and d["status"] != "closed")
        repairs.append(d)
    return TEMPLATES.TemplateResponse(request, "repairs/list.html", {
        "repairs": repairs,
        "status": status, "q": q,
        "status_labels": STATUS_LABELS, "today": today
    })


# ── 新規受付フォーム ───────────────────────────────────────
@router.get("/new", response_class=HTMLResponse)
async def new_repair_form(request: Request, db: Session = Depends(get_db)):
    _staff(request)
    customers = db.query(Customer).order_by(Customer.name).all()
    products  = db.query(Product).order_by(Product.name).all()
    rep_shipments = db.query(Shipment).filter(
        Shipment.shipment_type == "repair", Shipment.status == "shipped"
    ).order_by(Shipment.id.desc()).all()
    return TEMPLATES.TemplateResponse(request, "repairs/form.html", {
        "customers": [{"id": c.id, "name": c.name} for c in customers],
        "products":  [{"id": p.id, "name": p.name} for p in products],
        "rep_shipments": [{"id": s.id, "shipment_number": s.shipment_number,
                           "serial_number": s.serial_number,
                           "product_name": s.product.name if s.product else "",
                           "customer_name": s.customer.name if s.customer else ""} for s in rep_shipments],
        "today": date.today().isoformat()
    })


# ── 新規受付 POST ──────────────────────────────────────────
@router.post("/new")
async def create_repair(
    request: Request,
    customer_id: int             = Form(...),
    end_user_id: str             = Form(""),
    product_id: int              = Form(...),
    serial_number: str           = Form(""),
    lot_number: str              = Form(""),
    fault_description: str       = Form(...),
    received_date: str           = Form(...),
    replacement_shipment_id: str = Form(""),
    notes: str                   = Form(""),
    db: Session                  = Depends(get_db),
):
    staff = _staff(request)
    num = _gen_repair_number(db)
    repair = Repair(
        repair_number=num,
        customer_id=customer_id,
        end_user_id=int(end_user_id) if end_user_id else None,
        product_id=product_id,
        serial_number=serial_number or None,
        lot_number=lot_number or None,
        fault_description=fault_description,
        received_date=date.fromisoformat(received_date),
        replacement_shipment_id=int(replacement_shipment_id) if replacement_shipment_id else None,
        notes=notes or None,
        staff_name=staff["name"],
    )
    db.add(repair)
    db.commit()
    db.refresh(repair)
    return RedirectResponse(f"/repairs/{repair.id}", status_code=303)


# ── 詳細 ───────────────────────────────────────────────────
@router.get("/{repair_id}", response_class=HTMLResponse)
async def repair_detail(repair_id: int, request: Request, db: Session = Depends(get_db)):
    _staff(request)
    r = db.query(Repair).filter(Repair.id == repair_id).first()
    if not r:
        raise HTTPException(404)
    today = date.today().isoformat()
    dl = r.step_deadline
    dl_str = dl.isoformat() if dl else None
    repair = {c.name: getattr(r, c.name) for c in r.__table__.columns}
    repair["customer_name"]        = r.customer.name if r.customer else ""
    repair["end_user_name"]        = r.end_user.name if r.end_user else ""
    repair["product_name"]         = r.product.name if r.product else ""
    repair["step_deadline"]        = dl_str
    repair["is_overdue"]           = bool(dl_str and dl_str < today and repair["status"] != "closed")
    rep_ship = db.query(Shipment).filter(Shipment.id == r.replacement_shipment_id).first() if r.replacement_shipment_id else None
    repair["rep_shipment_number"]  = rep_ship.shipment_number if rep_ship else None
    repair["rep_product_name"]     = rep_ship.product.name if rep_ship and rep_ship.product else None
    next_status = NEXT_STATUS.get(repair["status"])
    return TEMPLATES.TemplateResponse(request, "repairs/detail.html", {
        "repair": repair,
        "status_labels": STATUS_LABELS,
        "next_status": next_status,
        "next_label": STATUS_LABELS.get(next_status, ""),
        "today": today
    })


# ── ステータス更新 ─────────────────────────────────────────
@router.post("/{repair_id}/advance")
async def advance_status(
    repair_id: int,
    request: Request,
    inspection_date: str           = Form(""),
    inspection_result: str         = Form(""),
    inspector: str                 = Form(""),
    sent_to_maker_date: str        = Form(""),
    maker_response: str            = Form(""),
    maker_response_date: str       = Form(""),
    maker_quote_amount: str        = Form(""),
    maker_response_note: str       = Form(""),
    quote_submitted_date: str      = Form(""),
    repair_ordered_date: str       = Form(""),
    repair_completed_date: str     = Form(""),
    delivery_type: str             = Form(""),
    delivery_address: str          = Form(""),
    replacement_returned_date: str = Form(""),
    returned_serial_number: str    = Form(""),
    closed_date: str               = Form(""),
    notes: str                     = Form(""),
    db: Session                    = Depends(get_db),
):
    staff = _staff(request)
    r = db.query(Repair).filter(Repair.id == repair_id).first()
    if not r:
        raise HTTPException(404)
    next_st = NEXT_STATUS.get(r.status)
    if not next_st:
        return RedirectResponse(f"/repairs/{repair_id}", status_code=303)
    # closed（最終完了）への変更はmanager以上のみ
    if next_st == "closed":
        _require_manager(staff)

    def _d(v): return date.fromisoformat(v) if v else None
    def _f(v): return float(v) if v else None

    r.status = next_st
    r.step_deadline = date.today() + timedelta(days=14)

    if next_st == "inspecting":
        r.inspection_date   = _d(inspection_date)
        r.inspection_result = inspection_result or None
        r.inspector         = inspector or None
    elif next_st == "sent_to_maker":
        r.sent_to_maker_date = _d(sent_to_maker_date)
    elif next_st == "maker_responded":
        r.maker_response      = maker_response or None
        r.maker_response_date = _d(maker_response_date)
        r.maker_quote_amount  = _f(maker_quote_amount)
        r.maker_response_note = maker_response_note or None
    elif next_st == "quote_submitted":
        r.quote_submitted_date = _d(quote_submitted_date)
    elif next_st == "repair_ordered":
        r.repair_ordered_date = _d(repair_ordered_date)
    elif next_st == "repair_completed":
        r.repair_completed_date = _d(repair_completed_date)
        r.delivery_type         = delivery_type or None
        r.delivery_address      = delivery_address or None
    elif next_st == "closed":
        r.replacement_returned_date = _d(replacement_returned_date)
        r.returned_serial_number    = returned_serial_number or None
        r.closed_date               = _d(closed_date)
        r.step_deadline             = None
    if notes:
        r.notes = notes

    db.commit()
    return RedirectResponse(f"/repairs/{repair_id}", status_code=303)


# ── 期限変更 ───────────────────────────────────────────────
@router.post("/{repair_id}/set-deadline")
async def set_deadline(
    repair_id: int,
    request: Request,
    step_deadline: str = Form(...),
    db: Session        = Depends(get_db),
):
    _staff(request)
    r = db.query(Repair).filter(Repair.id == repair_id).first()
    if not r:
        raise HTTPException(404)
    r.step_deadline = date.fromisoformat(step_deadline) if step_deadline else None
    db.commit()
    return RedirectResponse(f"/repairs/{repair_id}", status_code=303)


# ── 発注書 印刷ビュー ──────────────────────────────────────
@router.get("/{repair_id}/order-print", response_class=HTMLResponse)
async def order_print(repair_id: int, request: Request, db: Session = Depends(get_db)):
    _staff(request)
    r = db.query(Repair).filter(Repair.id == repair_id).first()
    if not r:
        raise HTTPException(404)
    repair = {c.name: getattr(r, c.name) for c in r.__table__.columns}
    repair["customer_name"] = r.customer.name if r.customer else ""
    repair["end_user_name"] = r.end_user.name if r.end_user else ""
    repair["product_name"]  = r.product.name if r.product else ""
    return TEMPLATES.TemplateResponse(request, "repairs/order_print.html", {
        "repair": repair,
        "company": COMPANY_INFO, "today": date.today().isoformat()
    })


# ── 修理明細書 印刷ビュー ──────────────────────────────────
@router.get("/{repair_id}/detail-print", response_class=HTMLResponse)
async def detail_print(repair_id: int, request: Request, db: Session = Depends(get_db)):
    _staff(request)
    r = db.query(Repair).filter(Repair.id == repair_id).first()
    if not r:
        raise HTTPException(404)
    repair = {c.name: getattr(r, c.name) for c in r.__table__.columns}
    repair["customer_name"] = r.customer.name if r.customer else ""
    repair["end_user_name"] = r.end_user.name if r.end_user else ""
    repair["product_name"]  = r.product.name if r.product else ""
    rep_ship = db.query(Shipment).filter(Shipment.id == r.replacement_shipment_id).first() if r.replacement_shipment_id else None
    repair["rep_shipment_number"] = rep_ship.shipment_number if rep_ship else None
    return TEMPLATES.TemplateResponse(request, "repairs/detail_print.html", {
        "repair": repair,
        "company": COMPANY_INFO, "today": date.today().isoformat()
    })
