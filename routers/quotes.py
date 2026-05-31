from datetime import date, datetime as _dt
from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from database import get_db
import crud
import company_config
import sqlite3 as _sq
import os as _os

router = APIRouter()
templates = Jinja2Templates(directory="templates")

company_info = {
    "name": company_config.COMPANY_NAME,
    "postal": company_config.COMPANY_POSTAL,
    "address": company_config.COMPANY_ADDRESS,
    "tel": company_config.COMPANY_TEL,
    "fax": company_config.COMPANY_FAX,
    "invoice_no": company_config.COMPANY_INVOICE_NO,
}

_DB_PATH = _os.path.join(_os.path.dirname(__file__), '..', 'sales_app.db')

def _raw():
    c = _sq.connect(_DB_PATH, timeout=30)
    c.row_factory = _sq.Row
    c.execute("PRAGMA journal_mode=WAL")
    return c

def _now():
    return _dt.now().strftime('%Y-%m-%d %H:%M:%S')

def _get_approval_context(quote, staff: dict) -> dict:
    """見積の承認フロー状態と権限を返す"""
    ctx = {"can_approve": False, "can_cancel": False, "doc": None, "step": None}
    if not getattr(quote, 'approval_doc_id', None):
        return ctx
    conn = _raw()
    try:
        doc = conn.execute("SELECT * FROM documents WHERE id=?", (quote.approval_doc_id,)).fetchone()
        if not doc:
            return ctx
        ctx["doc"] = dict(doc)
        # 承認可能チェック（in_review かつ現ステップ担当者）
        if doc['status'] == 'in_review':
            flow = conn.execute(
                "SELECT * FROM approval_flows WHERE document_type_id=? AND is_active=1 LIMIT 1",
                (doc['document_type_id'],)
            ).fetchone()
            if flow:
                step = conn.execute(
                    "SELECT * FROM approval_steps WHERE flow_id=? AND step_order=?",
                    (flow['id'], doc['current_step'])
                ).fetchone()
                if step:
                    ctx["step"] = dict(step)
                    ctx["can_approve"] = (
                        step['approver_id'] == staff['id'] or
                        step['approver_role'] == staff.get('role')
                    )
        # 取消可能チェック（承認済み かつ admin or 承認者本人）
        if quote.status == 'accepted':
            ctx["can_cancel"] = (
                staff.get('role') == 'admin' or
                quote.approved_by_id == staff['id']
            )
        return ctx
    finally:
        conn.close()


@router.get("/quotes", response_class=HTMLResponse)
def list_quotes(
    request: Request,
    db: Session = Depends(get_db),
    status: str = "",
    customer: str = "",
    end_user: str = "",
    product: str = "",
):
    quotes = crud.get_quotes(db, status=status, customer=customer, end_user=end_user, product=product)
    return templates.TemplateResponse("quotes/list.html", {
        "request": request,
        "quotes": quotes,
        "status": status,
        "customer": customer,
        "end_user": end_user,
        "product": product,
    })

@router.get("/quotes/new", response_class=HTMLResponse)
def new_quote_form(request: Request, db: Session = Depends(get_db)):
    customers = crud.get_customers(db)
    products = crud.get_products(db)
    return templates.TemplateResponse("quotes/form.html", {"request": request, "customers": customers, "products": products})

@router.post("/quotes/new")
async def create_quote(request: Request, db: Session = Depends(get_db)):
    form_data = await request.form()
    customer_id = int(form_data["customer_id"])
    end_user_id_str = form_data.get("end_user_id", "")
    end_user_id = int(end_user_id_str) if end_user_id_str else None
    valid_until_str = form_data.get("valid_until", "")
    valid_until = date.fromisoformat(valid_until_str) if valid_until_str else None
    notes = form_data.get("notes", "")
    product_ids = form_data.getlist("product_id[]")
    quantities = form_data.getlist("quantity[]")
    discount_rates = form_data.getlist("discount_rate[]")
    items = [
        {"product_id": int(pid), "quantity": int(qty), "discount_rate": float(dr) / 100.0}
        for pid, qty, dr in zip(product_ids, quantities, discount_rates)
        if pid and qty
    ]
    staff = request.state.staff
    crud.create_quote(
        db, customer_id=customer_id, end_user_id=end_user_id,
        valid_until=valid_until, notes=notes, items=items,
        created_by_id=staff['id']
    )
    return RedirectResponse("/quotes", status_code=303)

@router.get("/quotes/{quote_id}", response_class=HTMLResponse)
def detail_quote(quote_id: int, request: Request, db: Session = Depends(get_db)):
    quote = crud.get_quote(db, quote_id)
    staff = request.state.staff
    approval_ctx = _get_approval_context(quote, staff)
    return templates.TemplateResponse("quotes/detail.html", {
        "request": request,
        "quote": quote,
        "company": company_info,
        "approval_ctx": approval_ctx,
    })

@router.post("/quotes/{quote_id}/status")
def change_status(quote_id: int, status: str = Form(...), db: Session = Depends(get_db)):
    crud.update_quote_status(db, quote_id, status)
    return RedirectResponse(f"/quotes/{quote_id}", status_code=303)

@router.post("/quotes/{quote_id}/accept")
def accept_quote(
    quote_id: int,
    request: Request,
    approval_comment: str = Form(""),
    db: Session = Depends(get_db)
):
    staff = request.state.staff
    quote = crud.get_quote(db, quote_id)
    if not quote:
        return RedirectResponse("/quotes", status_code=303)

    ctx = _get_approval_context(quote, staff)
    if not ctx["can_approve"]:
        return RedirectResponse(f"/quotes/{quote_id}?error=no_permission", status_code=303)

    conn = _raw()
    try:
        doc_id = quote.approval_doc_id
        doc = conn.execute("SELECT * FROM documents WHERE id=?", (doc_id,)).fetchone()
        flow = conn.execute(
            "SELECT * FROM approval_flows WHERE document_type_id=? AND is_active=1 LIMIT 1",
            (doc['document_type_id'],)
        ).fetchone()
        steps = conn.execute(
            "SELECT * FROM approval_steps WHERE flow_id=? ORDER BY step_order",
            (flow['id'],)
        ).fetchall()
        current_step = doc['current_step']

        # 承認ログ記録
        conn.execute("""
            INSERT INTO approval_logs (document_id, step_order, approver_id, action, comment)
            VALUES (?,?,?,?,?)
        """, (doc_id, current_step, staff['id'], 'approved', approval_comment or None))

        next_steps = [s for s in steps if s['step_order'] > current_step]
        if next_steps:
            # 次のステップへ
            conn.execute(
                "UPDATE documents SET current_step=?, updated_at=? WHERE id=?",
                (next_steps[0]['step_order'], _now(), doc_id)
            )
            if next_steps[0]['approver_id']:
                conn.execute(
                    "INSERT INTO notifications (document_id, recipient_id, type) VALUES (?,?,?)",
                    (doc_id, next_steps[0]['approver_id'], 'approval_request')
                )
            conn.commit()
            # まだ全ステップ未完了 → 見積はステータス変更しない
        else:
            # 全ステップ完了 → 最終承認
            conn.execute(
                "UPDATE documents SET status='approved', updated_at=? WHERE id=?",
                (_now(), doc_id)
            )
            conn.execute(
                "INSERT INTO notifications (document_id, recipient_id, type) VALUES (?,?,?)",
                (doc_id, doc['uploaded_by'], 'approved')
            )
            conn.commit()
            # 見積ステータスを承認済みに
            quote.status = 'accepted'
            quote.approved_by_id = staff['id']
            quote.approved_at = _dt.now()
            quote.approval_comment = approval_comment or None
            db.commit()
    finally:
        conn.close()

    return RedirectResponse(f"/quotes/{quote_id}", status_code=303)

@router.post("/quotes/{quote_id}/cancel_approval")
def cancel_approval(
    quote_id: int,
    request: Request,
    cancel_comment: str = Form(...),
    db: Session = Depends(get_db)
):
    staff = request.state.staff
    quote = crud.get_quote(db, quote_id)
    if not quote:
        return RedirectResponse("/quotes", status_code=303)

    ctx = _get_approval_context(quote, staff)
    if not ctx["can_cancel"]:
        return RedirectResponse(f"/quotes/{quote_id}?error=no_permission", status_code=303)

    conn = _raw()
    try:
        doc_id = quote.approval_doc_id
        # ドキュメントを差し戻し状態に戻す
        conn.execute(
            "UPDATE documents SET status='revising', current_step=0, updated_at=? WHERE id=?",
            (_now(), doc_id)
        )
        # 取消ログ記録
        conn.execute("""
            INSERT INTO approval_logs (document_id, step_order, approver_id, action, comment)
            VALUES (?,0,?,'cancelled',?)
        """, (doc_id, staff['id'], f"承認取消: {cancel_comment}"))
        # 見積作成者に通知
        if quote.created_by_id:
            conn.execute(
                "INSERT INTO notifications (document_id, recipient_id, type) VALUES (?,?,?)",
                (doc_id, quote.created_by_id, 'rejected')
            )
        conn.commit()
    finally:
        conn.close()

    # 見積ステータスを draft に戻す
    quote.status = 'draft'
    quote.cancelled_by_id = staff['id']
    quote.cancel_comment = cancel_comment
    quote.cancelled_at = _dt.now()
    db.commit()

    return RedirectResponse(f"/quotes/{quote_id}", status_code=303)

@router.post("/quotes/{quote_id}/delete")
def delete_quote(quote_id: int, db: Session = Depends(get_db)):
    crud.delete_quote(db, quote_id)
    return RedirectResponse("/quotes", status_code=303)
