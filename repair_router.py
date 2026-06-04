import os
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path
from fastapi import APIRouter, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
import company_config

TEMPLATES = Jinja2Templates(directory="templates")
router = APIRouter(prefix="/repairs", tags=["repairs"])
DB_PATH = os.path.join(os.path.dirname(__file__), "sales_app.db")

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

def get_db():
    con = sqlite3.connect(DB_PATH, timeout=30)
    con.row_factory = sqlite3.Row
    return con

def _staff(request: Request):
    staff = getattr(request.state, "staff", None)
    if staff is None:
        raise HTTPException(status_code=401)
    return staff

def _gen_repair_number(con):
    prefix = f"REP-{datetime.now().strftime('%Y%m')}-"
    row = con.execute(
        "SELECT repair_number FROM repairs WHERE repair_number LIKE ? ORDER BY id DESC LIMIT 1",
        (f"{prefix}%",)
    ).fetchone()
    seq = int(row[0].split("-")[-1]) + 1 if row else 1
    return f"{prefix}{seq:04d}"


# ── 一覧 ─────────────────────────────────────────────────
@router.get("/", response_class=HTMLResponse)
async def repair_list(request: Request, status: str = "", q: str = ""):
    _staff(request)
    con = get_db()
    sql = """
        SELECT r.*,
               c.name  AS customer_name,
               eu.name AS end_user_name,
               p.name  AS product_name
        FROM repairs r
        LEFT JOIN customers c  ON c.id = r.customer_id
        LEFT JOIN customers eu ON eu.id = r.end_user_id
        LEFT JOIN products  p  ON p.id = r.product_id
        WHERE 1=1
    """
    params = []
    if status:
        sql += " AND r.status = ?"
        params.append(status)
    if q:
        sql += """ AND (r.repair_number LIKE ? OR c.name LIKE ? OR eu.name LIKE ?
                        OR p.name LIKE ? OR r.serial_number LIKE ?)"""
        like = f"%{q}%"
        params += [like, like, like, like, like]
    sql += " ORDER BY r.id DESC"
    today = date.today().isoformat()
    repairs = []
    for r in con.execute(sql, params).fetchall():
        d = dict(r)
        d["is_overdue"] = (
            d.get("step_deadline") and d["step_deadline"] < today
            and d["status"] != "closed"
        )
        repairs.append(d)
    con.close()
    return TEMPLATES.TemplateResponse("repairs/list.html", {
        "request": request,
        "repairs": repairs,
        "status": status,
        "q": q,
        "status_labels": STATUS_LABELS,
        "today": today,
    })


# ── 新規受付フォーム ────────────────────────────────────
@router.get("/new", response_class=HTMLResponse)
async def new_repair_form(request: Request):
    _staff(request)
    con = get_db()
    customers = [dict(r) for r in con.execute("SELECT id, name FROM customers ORDER BY name").fetchall()]
    products  = [dict(r) for r in con.execute("SELECT id, name FROM products ORDER BY name").fetchall()]
    # 修理代替品として使える出荷一覧（種別=repair, 状態=shipped）
    rep_shipments = [dict(r) for r in con.execute("""
        SELECT s.id, s.shipment_number, s.serial_number, p.name AS product_name, c.name AS customer_name
        FROM shipments s
        JOIN products  p ON p.id = s.product_id
        JOIN customers c ON c.id = s.customer_id
        WHERE s.shipment_type = 'repair' AND s.status = 'shipped'
        ORDER BY s.id DESC
    """).fetchall()]
    con.close()
    return TEMPLATES.TemplateResponse("repairs/form.html", {
        "request": request,
        "customers": customers,
        "products": products,
        "rep_shipments": rep_shipments,
        "today": date.today().isoformat(),
    })


# ── 新規受付 POST ──────────────────────────────────────
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
):
    staff = _staff(request)
    con = get_db()
    num = _gen_repair_number(con)
    con.execute("""
        INSERT INTO repairs
            (repair_number, customer_id, end_user_id, product_id,
             serial_number, lot_number, fault_description, received_date,
             replacement_shipment_id, notes, staff_name)
        VALUES (?,?,?,?,?,?,?,?,?,?,?)
    """, (
        num,
        customer_id,
        int(end_user_id) if end_user_id else None,
        product_id,
        serial_number or None,
        lot_number or None,
        fault_description,
        received_date,
        int(replacement_shipment_id) if replacement_shipment_id else None,
        notes or None,
        staff["name"],
    ))
    con.commit()
    repair_id = con.execute("SELECT id FROM repairs WHERE repair_number=?", (num,)).fetchone()[0]
    con.close()
    return RedirectResponse(f"/repairs/{repair_id}", status_code=303)


# ── 詳細 ──────────────────────────────────────────────
@router.get("/{repair_id}", response_class=HTMLResponse)
async def repair_detail(repair_id: int, request: Request):
    _staff(request)
    con = get_db()
    row = con.execute("""
        SELECT r.*,
               c.name  AS customer_name,
               eu.name AS end_user_name,
               p.name  AS product_name,
               s.shipment_number AS rep_shipment_number,
               sp.name AS rep_product_name
        FROM repairs r
        LEFT JOIN customers c  ON c.id = r.customer_id
        LEFT JOIN customers eu ON eu.id = r.end_user_id
        LEFT JOIN products  p  ON p.id = r.product_id
        LEFT JOIN shipments s  ON s.id = r.replacement_shipment_id
        LEFT JOIN products  sp ON sp.id = s.product_id
        WHERE r.id = ?
    """, (repair_id,)).fetchone()
    if not row:
        raise HTTPException(404)
    repair = dict(row)
    con.close()
    today = date.today().isoformat()
    repair["is_overdue"] = (
        repair.get("step_deadline") and repair["step_deadline"] < today
        and repair["status"] != "closed"
    )
    next_status = NEXT_STATUS.get(repair["status"])
    return TEMPLATES.TemplateResponse("repairs/detail.html", {
        "request": request,
        "repair": repair,
        "status_labels": STATUS_LABELS,
        "next_status": next_status,
        "next_label": STATUS_LABELS.get(next_status, ""),
        "today": today,
    })


# ── ステータス更新（汎用） ────────────────────────────
@router.post("/{repair_id}/advance")
async def advance_status(
    repair_id: int,
    request: Request,
    inspection_date: str         = Form(""),
    inspection_result: str       = Form(""),
    inspector: str               = Form(""),
    sent_to_maker_date: str      = Form(""),
    maker_response: str          = Form(""),
    maker_response_date: str     = Form(""),
    maker_quote_amount: str      = Form(""),
    maker_response_note: str     = Form(""),
    quote_submitted_date: str    = Form(""),
    repair_ordered_date: str     = Form(""),
    repair_completed_date: str   = Form(""),
    delivery_type: str           = Form(""),
    delivery_address: str        = Form(""),
    replacement_returned_date: str = Form(""),
    closed_date: str             = Form(""),
    notes: str                   = Form(""),
):
    _staff(request)
    con = get_db()
    row = con.execute("SELECT status FROM repairs WHERE id=?", (repair_id,)).fetchone()
    if not row:
        raise HTTPException(404)
    current = row["status"]
    next_st = NEXT_STATUS.get(current)
    if not next_st:
        con.close()
        return RedirectResponse(f"/repairs/{repair_id}", status_code=303)

    deadline = (date.today() + timedelta(days=14)).isoformat()
    fields = {"status": next_st, "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "step_deadline": deadline}
    def _d(v): return v if v else None
    def _f(v): return float(v) if v else None

    if next_st == "inspecting":
        fields.update(inspection_date=_d(inspection_date), inspection_result=_d(inspection_result), inspector=_d(inspector))
    elif next_st == "sent_to_maker":
        fields["sent_to_maker_date"] = _d(sent_to_maker_date)
    elif next_st == "maker_responded":
        fields.update(maker_response=_d(maker_response), maker_response_date=_d(maker_response_date),
                      maker_quote_amount=_f(maker_quote_amount), maker_response_note=_d(maker_response_note))
    elif next_st == "quote_submitted":
        fields["quote_submitted_date"] = _d(quote_submitted_date)
    elif next_st == "repair_ordered":
        fields["repair_ordered_date"] = _d(repair_ordered_date)
    elif next_st == "repair_completed":
        fields.update(repair_completed_date=_d(repair_completed_date),
                      delivery_type=_d(delivery_type), delivery_address=_d(delivery_address))
    elif next_st == "closed":
        fields.update(replacement_returned_date=_d(replacement_returned_date), closed_date=_d(closed_date))
        fields["step_deadline"] = None
    if notes:
        fields["notes"] = notes

    set_clause = ", ".join(f"{k}=?" for k in fields)
    con.execute(f"UPDATE repairs SET {set_clause} WHERE id=?", (*fields.values(), repair_id))
    con.commit()
    con.close()
    return RedirectResponse(f"/repairs/{repair_id}", status_code=303)


# ── 期限変更 ─────────────────────────────────────────
@router.post("/{repair_id}/set-deadline")
async def set_deadline(
    repair_id: int,
    request: Request,
    step_deadline: str = Form(...),
):
    _staff(request)
    con = get_db()
    con.execute(
        "UPDATE repairs SET step_deadline=?, updated_at=? WHERE id=?",
        (step_deadline or None, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), repair_id)
    )
    con.commit()
    con.close()
    return RedirectResponse(f"/repairs/{repair_id}", status_code=303)


# ── 発注書 印刷ビュー ────────────────────────────────
@router.get("/{repair_id}/order-print", response_class=HTMLResponse)
async def order_print(repair_id: int, request: Request):
    _staff(request)
    con = get_db()
    row = con.execute("""
        SELECT r.*, c.name AS customer_name, eu.name AS end_user_name, p.name AS product_name
        FROM repairs r
        LEFT JOIN customers c  ON c.id = r.customer_id
        LEFT JOIN customers eu ON eu.id = r.end_user_id
        LEFT JOIN products  p  ON p.id = r.product_id
        WHERE r.id = ?
    """, (repair_id,)).fetchone()
    if not row:
        raise HTTPException(404)
    con.close()
    return TEMPLATES.TemplateResponse("repairs/order_print.html", {
        "request": request,
        "repair": dict(row),
        "company": COMPANY_INFO,
        "today": date.today().isoformat(),
    })


# ── 修理明細書 印刷ビュー ─────────────────────────────
@router.get("/{repair_id}/detail-print", response_class=HTMLResponse)
async def detail_print(repair_id: int, request: Request):
    _staff(request)
    con = get_db()
    row = con.execute("""
        SELECT r.*, c.name AS customer_name, eu.name AS end_user_name, p.name AS product_name,
               s.shipment_number AS rep_shipment_number
        FROM repairs r
        LEFT JOIN customers c  ON c.id = r.customer_id
        LEFT JOIN customers eu ON eu.id = r.end_user_id
        LEFT JOIN products  p  ON p.id = r.product_id
        LEFT JOIN shipments s  ON s.id = r.replacement_shipment_id
        WHERE r.id = ?
    """, (repair_id,)).fetchone()
    if not row:
        raise HTTPException(404)
    con.close()
    return TEMPLATES.TemplateResponse("repairs/detail_print.html", {
        "request": request,
        "repair": dict(row),
        "company": COMPANY_INFO,
        "today": date.today().isoformat(),
    })
