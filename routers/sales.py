from utils import now_jst
from datetime import date, datetime
from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from database import get_db
import models
import company_config

router = APIRouter()
from templates_config import templates

company_info = {
    "name": company_config.COMPANY_NAME,
    "postal": company_config.COMPANY_POSTAL,
    "address": company_config.COMPANY_ADDRESS,
    "tel": company_config.COMPANY_TEL,
    "fax": company_config.COMPANY_FAX,
    "invoice_no": company_config.COMPANY_INVOICE_NO,
}

from decimal import Decimal, ROUND_DOWN
TAX_RATE = Decimal("0.10")  # [I6] Decimal型で精度保証


def _gen_sale_number(db):
    # [I3] MAX(id)+1 方式
    today = now_jst().strftime("%Y%m%d")
    prefix = f"SA-{today}-"
    max_id = db.query(models.Sale.id).order_by(models.Sale.id.desc()).first()
    seq = (max_id[0] + 1) if max_id else 1
    return f"{prefix}{seq:05d}"


def _gen_invoice_number(db):
    # [I3] MAX(id)+1 方式
    today = now_jst().strftime("%Y%m%d")
    prefix = f"INV-{today}-"
    max_id = db.query(models.Invoice.id).order_by(models.Invoice.id.desc()).first()
    seq = (max_id[0] + 1) if max_id else 1
    return f"{prefix}{seq:05d}"


# ============================================================
# 売上一覧
# ============================================================
@router.get("/sales", response_class=HTMLResponse)
def list_sales(request: Request, status: str = "", customer_id: str = "",
               date_from: str = "", date_to: str = "", page: int = 1,
               db: Session = Depends(get_db)):
    # [I4] ページネーション適用
    q = db.query(models.Sale)
    if status:
        q = q.filter(models.Sale.status == status)
    if customer_id:
        q = q.filter(models.Sale.customer_id == int(customer_id))
    if date_from:
        q = q.filter(models.Sale.sale_date >= date.fromisoformat(date_from))
    if date_to:
        q = q.filter(models.Sale.sale_date <= date.fromisoformat(date_to))
    import crud as _crud
    pager = _crud.paginate(q.order_by(models.Sale.id.desc()), page=page, per_page=50)
    customers = db.query(models.Customer).order_by(models.Customer.name).all()
    total = sum(s.total_amount for s in pager.items)
    return templates.TemplateResponse(request, "sales/list.html", {
        "sales": pager.items, "pager": pager,
        "customers": customers,
        "status": status, "customer_id": customer_id,
        "date_from": date_from, "date_to": date_to, "total": total,
    })


# ============================================================
# 売上新規作成（出荷または見積から）
# ============================================================
@router.get("/sales/new", response_class=HTMLResponse)
def new_sale_form(request: Request, shipment_id: str = "", quote_id: str = "",
                  db: Session = Depends(get_db)):
    shipment = None
    quote = None
    if shipment_id:
        shipment = db.query(models.Shipment).filter(
            models.Shipment.id == int(shipment_id)
        ).first()
    if quote_id:
        quote = db.query(models.Quote).filter(
            models.Quote.id == int(quote_id)
        ).first()
    customers = db.query(models.Customer).order_by(models.Customer.name).all()
    products = db.query(models.Product).order_by(models.Product.name).all()
    today = date.today().isoformat()
    return templates.TemplateResponse(request, "sales/form.html", {
        "shipment": shipment, "quote": quote,
        "customers": customers, "products": products,
        "today": today, "tax_rate": int(TAX_RATE * 100),
    })


@router.post("/sales/new")
async def create_sale(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    staff = request.state.staff

    # [I2] 入力バリデーション
    from fastapi import HTTPException
    try:
        product_id = int(form["product_id"])
        quantity = int(form.get("quantity", 1))
        unit_price = Decimal(str(form["unit_price"]))
    except (ValueError, KeyError) as e:
        raise HTTPException(422, f"入力値が不正です: {e}")
    if quantity <= 0:
        raise HTTPException(422, "数量は1以上を入力してください")
    if unit_price <= 0:
        raise HTTPException(422, "単価は0より大きい値を入力してください")
    subtotal = unit_price * quantity
    # [I6] 消費税は切り捨て（1円未満切捨）でDecimalのまま計算
    tax_amount = (subtotal * TAX_RATE).quantize(Decimal("1"), rounding=ROUND_DOWN)
    total_amount = subtotal + tax_amount
    # float変換はDB保存直前のみ
    subtotal = float(subtotal)
    tax_amount = float(tax_amount)
    total_amount = float(total_amount)

    shipment_id = int(form["shipment_id"]) if form.get("shipment_id") else None
    quote_id = int(form["quote_id"]) if form.get("quote_id") else None

    sale = models.Sale(
        sale_number=_gen_sale_number(db),
        shipment_id=shipment_id,
        quote_id=quote_id,
        customer_id=int(form["customer_id"]),
        product_id=product_id,
        quantity=quantity,
        unit_price=unit_price,
        subtotal=subtotal,
        tax_rate=TAX_RATE,
        tax_amount=tax_amount,
        total_amount=total_amount,
        sale_date=date.fromisoformat(form["sale_date"]),
        notes=form.get("notes") or None,
        staff_name=staff["name"],
        status="confirmed",
    )
    db.add(sale)

    # 出荷ステータスを completed に更新
    if shipment_id:
        shipment = db.query(models.Shipment).filter(
            models.Shipment.id == shipment_id
        ).first()
        if shipment:
            shipment.status = "completed"

    db.commit()
    return RedirectResponse("/sales", status_code=303)


# ============================================================
# 売上詳細
# ============================================================
@router.get("/sales/{sale_id}", response_class=HTMLResponse)
def detail_sale(sale_id: int, request: Request, db: Session = Depends(get_db)):
    sale = db.query(models.Sale).filter(models.Sale.id == sale_id).first()
    return templates.TemplateResponse(request, "sales/detail.html", {
        "sale": sale, "company": company_info,
    })


@router.post("/sales/{sale_id}/delete")
def delete_sale(sale_id: int, request: Request, db: Session = Depends(get_db)):
    # [C4] 管理者のみ売上削除可能
    current = request.state.staff
    if current.get("role") != "admin":
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=403, content={"detail": "管理者権限が必要です"})
    sale = db.query(models.Sale).filter(models.Sale.id == sale_id).first()
    if sale and sale.status == "confirmed":
        # 関連InvoiceItemを先に取得（影響するInvoice IDを記録）
        invoice_items = db.query(models.InvoiceItem).filter(models.InvoiceItem.sale_id == sale_id).all()
        affected_invoice_ids = {item.invoice_id for item in invoice_items}
        for item in invoice_items:
            db.delete(item)

        db.delete(sale)
        db.flush()

        # 影響を受けたInvoiceの合計を再計算
        for invoice_id in affected_invoice_ids:
            invoice = db.query(models.Invoice).filter(models.Invoice.id == invoice_id).first()
            if invoice:
                remaining_items = db.query(models.InvoiceItem).filter(
                    models.InvoiceItem.invoice_id == invoice_id
                ).all()
                remaining_sales = [
                    db.query(models.Sale).filter(models.Sale.id == item.sale_id).first()
                    for item in remaining_items
                ]
                remaining_sales = [s for s in remaining_sales if s]
                invoice.subtotal = sum(s.subtotal for s in remaining_sales)
                invoice.tax_amount = sum(s.tax_amount for s in remaining_sales)
                invoice.total_amount = invoice.subtotal + invoice.tax_amount

        db.commit()
    return RedirectResponse("/sales", status_code=303)


# ============================================================
# 請求書一覧
# ============================================================
@router.get("/invoices", response_class=HTMLResponse)
def list_invoices(request: Request, status: str = "", customer_id: str = "",
                  db: Session = Depends(get_db)):
    q = db.query(models.Invoice)
    if status:
        q = q.filter(models.Invoice.status == status)
    if customer_id:
        q = q.filter(models.Invoice.customer_id == int(customer_id))
    invoices = q.order_by(models.Invoice.id.desc()).all()
    customers = db.query(models.Customer).order_by(models.Customer.name).all()
    return templates.TemplateResponse(request, "sales/invoices.html", {
        "invoices": invoices,
        "customers": customers, "status": status, "customer_id": customer_id,
    })


# ============================================================
# 請求書新規作成
# ============================================================
@router.get("/invoices/new", response_class=HTMLResponse)
def new_invoice_form(request: Request, customer_id: str = "", db: Session = Depends(get_db)):
    customers = db.query(models.Customer).order_by(models.Customer.name).all()
    # 未請求の売上を取得
    q = db.query(models.Sale).filter(models.Sale.status == "confirmed")
    if customer_id:
        q = q.filter(models.Sale.customer_id == int(customer_id))
    pending_sales = q.order_by(models.Sale.sale_date).all()
    today = date.today().isoformat()
    return templates.TemplateResponse(request, "sales/invoice_form.html", {
        "customers": customers,
        "pending_sales": pending_sales, "today": today,
        "selected_customer_id": int(customer_id) if customer_id else None,
    })


@router.post("/invoices/new")
async def create_invoice(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    staff = request.state.staff

    customer_id = int(form["customer_id"])
    sale_ids = [int(x) for x in form.getlist("sale_ids[]")]
    issue_date = date.fromisoformat(form["issue_date"])
    due_date_str = form.get("due_date", "")
    due_date = date.fromisoformat(due_date_str) if due_date_str else None

    sales = db.query(models.Sale).filter(models.Sale.id.in_(sale_ids)).all()
    # [I6] 請求書集計もDecimalで計算して端数なし
    subtotal = float(sum(Decimal(str(s.subtotal)) for s in sales))
    tax_amount = float(sum(Decimal(str(s.tax_amount)) for s in sales))
    total_amount = float(Decimal(str(subtotal)) + Decimal(str(tax_amount)))

    invoice = models.Invoice(
        invoice_number=_gen_invoice_number(db),
        customer_id=customer_id,
        issue_date=issue_date,
        due_date=due_date,
        subtotal=subtotal,
        tax_amount=tax_amount,
        total_amount=total_amount,
        notes=form.get("notes") or None,
        staff_name=staff["name"],
        status="unpaid",
    )
    db.add(invoice)
    db.flush()

    for sale in sales:
        item = models.InvoiceItem(
            invoice_id=invoice.id,
            sale_id=sale.id,
            amount=sale.total_amount,
        )
        db.add(item)
        sale.status = "invoiced"

    db.commit()
    return RedirectResponse(f"/invoices/{invoice.id}", status_code=303)


# ============================================================
# 請求書詳細
# ============================================================
@router.get("/invoices/{invoice_id}", response_class=HTMLResponse)
def detail_invoice(invoice_id: int, request: Request, db: Session = Depends(get_db)):
    invoice = db.query(models.Invoice).filter(models.Invoice.id == invoice_id).first()
    paid_total = sum(p.amount for p in invoice.payments)
    remaining = invoice.total_amount - paid_total
    today = date.today().isoformat()
    error_map = {
        "amount_zero": "入金額は1円以上で入力してください。",
        "amount_exceeded": "入金額が残高を超えています。",
        "invalid_amount": "入金額が不正です。",
    }
    error_key = request.query_params.get("error", "")
    error_msg = error_map.get(error_key, "")
    return templates.TemplateResponse(request, "sales/invoice_detail.html", {
        "invoice": invoice, "company": company_info,
        "paid_total": paid_total, "remaining": remaining, "today": today,
        "error_msg": error_msg,
    })


# ============================================================
# 入金・消込み登録
# ============================================================
@router.post("/invoices/{invoice_id}/payment")
async def add_payment(invoice_id: int, request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    staff = request.state.staff

    invoice = db.query(models.Invoice).filter(models.Invoice.id == invoice_id).first()

    try:
        amount = float(form["amount"])
    except (ValueError, TypeError):
        return RedirectResponse(f"/invoices/{invoice_id}?error=invalid_amount", status_code=303)

    # [I2] 入金額バリデーション
    if amount <= 0:
        return RedirectResponse(f"/invoices/{invoice_id}?error=amount_zero", status_code=303)
    paid_so_far = sum(p.amount for p in invoice.payments)
    remaining = float(invoice.total_amount) - paid_so_far
    if amount > remaining:
        return RedirectResponse(f"/invoices/{invoice_id}?error=amount_exceeded", status_code=303)

    payment = models.Payment(
        invoice_id=invoice_id,
        payment_date=date.fromisoformat(form["payment_date"]),
        amount=amount,
        method=form.get("method") or None,
        notes=form.get("notes") or None,
        staff_name=staff["name"],
    )
    db.add(payment)

    # 消込みステータス更新
    paid_total = paid_so_far + amount
    if paid_total >= float(invoice.total_amount):
        invoice.status = "paid"
    elif paid_total > 0:
        invoice.status = "partial"
    db.commit()
    return RedirectResponse(f"/invoices/{invoice_id}", status_code=303)


@router.post("/invoices/{invoice_id}/delete")
def delete_invoice(invoice_id: int, request: Request, db: Session = Depends(get_db)):
    # [C4] 管理者のみ請求書削除可能
    current = request.state.staff
    if current.get("role") != "admin":
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=403, content={"detail": "管理者権限が必要です"})
    invoice = db.query(models.Invoice).filter(models.Invoice.id == invoice_id).first()
    if invoice:
        # [C7] 紐づく Sale.status を "confirmed" に戻して再請求可能にする
        sale_ids = [item.sale_id for item in invoice.items]
        if sale_ids:
            db.query(models.Sale).filter(models.Sale.id.in_(sale_ids)).update(
                {"status": "confirmed"}, synchronize_session=False
            )
        db.delete(invoice)
        db.commit()
    return RedirectResponse("/invoices", status_code=303)


@router.get("/sales/export.csv")
def export_sales_csv(
    request: Request, db: Session = Depends(get_db),
    status: str = "", customer_id: str = "", date_from: str = "", date_to: str = "",
):
    import csv, io
    from fastapi.responses import StreamingResponse
    import models
    q = db.query(models.Sale)
    if status:
        q = q.filter(models.Sale.status == status)
    if customer_id:
        q = q.filter(models.Sale.customer_id == int(customer_id))
    if date_from:
        from datetime import date as _date
        q = q.filter(models.Sale.sale_date >= _date.fromisoformat(date_from))
    if date_to:
        from datetime import date as _date
        q = q.filter(models.Sale.sale_date <= _date.fromisoformat(date_to))
    rows = q.order_by(models.Sale.id.desc()).all()
    STATUS_MAP = {"confirmed":"確定","invoiced":"請求済","paid":"入金済"}
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["売上番号","売上日","取引先","商品","数量","単価","小計","消費税","合計","ステータス","担当者"])
    for s in rows:
        w.writerow([
            s.sale_number,
            str(s.sale_date),
            s.customer.name if s.customer else "",
            s.product.name if s.product else "",
            s.quantity,
            int(s.unit_price or 0),
            int(s.subtotal or 0),
            int(s.tax_amount or 0),
            int(s.total_amount or 0),
            STATUS_MAP.get(s.status, s.status),
            s.staff_name or "",
        ])
    return StreamingResponse(
        iter([("\ufeff" + buf.getvalue()).encode("utf-8-sig")]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=sales.csv"}
    )
