from datetime import date, datetime as _dt
from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import text as _sa_text
from database import get_db
import crud
import company_config

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

def _now():
    return _dt.now().strftime('%Y-%m-%d %H:%M:%S')

def _row(row):
    return dict(row._mapping) if row else None

def _rows(rows):
    return [_row(r) for r in rows]

def _get_approval_context(quote, staff: dict, db: Session) -> dict:
    """見積の承認フロー状態と権限を返す"""
    ctx = {"can_approve": False, "can_cancel": False, "doc": None, "step": None}
    if not getattr(quote, 'approval_doc_id', None):
        return ctx
    doc = _row(db.execute(
        _sa_text("SELECT * FROM documents WHERE id=:i"),
        {"i": quote.approval_doc_id}
    ).fetchone())
    if not doc:
        return ctx
    ctx["doc"] = doc
    if doc['status'] == 'in_review':
        flow = db.execute(
            _sa_text("SELECT id FROM approval_flows WHERE document_type_id=:t AND is_active=1 LIMIT 1"),
            {"t": doc['document_type_id']}
        ).fetchone()
        if flow:
            step = _row(db.execute(
                _sa_text("SELECT * FROM approval_steps WHERE flow_id=:f AND step_order=:s"),
                {"f": flow[0], "s": doc['current_step']}
            ).fetchone())
            if step:
                ctx["step"] = step
                ctx["can_approve"] = (
                    step['approver_id'] == staff['id'] or
                    step['approver_role'] == staff.get('role')
                )
    if quote.status == 'accepted':
        ctx["can_cancel"] = (
            staff.get('role') == 'admin' or
            quote.approved_by_id == staff['id']
        )
    return ctx


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
    approval_ctx = _get_approval_context(quote, staff, db)
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

    ctx = _get_approval_context(quote, staff, db)
    if not ctx["can_approve"]:
        return RedirectResponse(f"/quotes/{quote_id}?error=no_permission", status_code=303)

    doc_id = quote.approval_doc_id
    doc = _row(db.execute(_sa_text("SELECT * FROM documents WHERE id=:i"), {"i": doc_id}).fetchone())
    flow = db.execute(
        _sa_text("SELECT id FROM approval_flows WHERE document_type_id=:t AND is_active=1 LIMIT 1"),
        {"t": doc['document_type_id']}
    ).fetchone()
    steps = _rows(db.execute(
        _sa_text("SELECT * FROM approval_steps WHERE flow_id=:f ORDER BY step_order"),
        {"f": flow[0]}
    ).fetchall())
    current_step = doc['current_step']

    db.execute(
        _sa_text("""
            INSERT INTO approval_logs (document_id, step_order, approver_id, action, comment)
            VALUES (:d,:s,:a,'approved',:c)
        """),
        {"d": doc_id, "s": current_step, "a": staff['id'], "c": approval_comment or None}
    )

    next_steps = [s for s in steps if s['step_order'] > current_step]
    if next_steps:
        db.execute(
            _sa_text("UPDATE documents SET current_step=:ns, updated_at=:t WHERE id=:i"),
            {"ns": next_steps[0]['step_order'], "t": _now(), "i": doc_id}
        )
        if next_steps[0]['approver_id']:
            db.execute(
                _sa_text("INSERT INTO notifications (document_id, recipient_id, type) VALUES (:d,:r,'approval_request')"),
                {"d": doc_id, "r": next_steps[0]['approver_id']}
            )
    else:
        db.execute(
            _sa_text("UPDATE documents SET status='approved', updated_at=:t WHERE id=:i"),
            {"t": _now(), "i": doc_id}
        )
        db.execute(
            _sa_text("INSERT INTO notifications (document_id, recipient_id, type) VALUES (:d,:r,'approved')"),
            {"d": doc_id, "r": doc['uploaded_by']}
        )
        quote.status = 'accepted'
        quote.approved_by_id = staff['id']
        quote.approved_at = _dt.now()
        quote.approval_comment = approval_comment or None

    db.commit()
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

    ctx = _get_approval_context(quote, staff, db)
    if not ctx["can_cancel"]:
        return RedirectResponse(f"/quotes/{quote_id}?error=no_permission", status_code=303)

    doc_id = quote.approval_doc_id
    db.execute(
        _sa_text("UPDATE documents SET status='revising', current_step=0, updated_at=:t WHERE id=:i"),
        {"t": _now(), "i": doc_id}
    )
    db.execute(
        _sa_text("""
            INSERT INTO approval_logs (document_id, step_order, approver_id, action, comment)
            VALUES (:d,0,:a,'cancelled',:c)
        """),
        {"d": doc_id, "a": staff['id'], "c": f"承認取消: {cancel_comment}"}
    )
    if quote.created_by_id:
        db.execute(
            _sa_text("INSERT INTO notifications (document_id, recipient_id, type) VALUES (:d,:r,'rejected')"),
            {"d": doc_id, "r": quote.created_by_id}
        )

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
