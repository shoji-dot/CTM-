"""
routers/returns.py - 返品管理
"""
from datetime import date
from fastapi import APIRouter, Depends, Form, Request, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session, joinedload

from database import get_db
from models import Return, Sale, Customer, Product
from templates_config import templates
import crud

router = APIRouter(prefix="/returns", tags=["returns"])

STATUS_LABELS = {
    "returned":  "返品済",
    "restocked": "在庫戻し済",
    "disposed":  "廃棄",
}

REASON_LABELS = {
    "defect":    "不良品",
    "wrong":     "誤納品",
    "cancel":    "注文キャンセル",
    "other":     "その他",
}


def _gen_return_number(db: Session) -> str:
    from utils import now_jst
    prefix = f"RET-{now_jst().strftime('%Y%m')}-"
    row = db.query(Return).filter(
        Return.return_number.like(f"{prefix}%")
    ).order_by(Return.id.desc()).first()
    seq = int(row.return_number.split("-")[-1]) + 1 if row else 1
    return f"{prefix}{seq:04d}"


# ── 一覧 ──────────────────────────────────────────────────
@router.get("/", response_class=HTMLResponse)
def list_returns(
    request: Request, db: Session = Depends(get_db),
    status: str = "", customer: str = "", page: int = 1,
):
    q = db.query(Return).options(
        joinedload(Return.customer),
        joinedload(Return.product),
        joinedload(Return.sale),
    )
    if status:
        q = q.filter(Return.status == status)
    if customer:
        q = q.join(Return.customer).filter(Customer.name.contains(customer))
    q = q.order_by(Return.id.desc())
    pagination = crud.paginate(q, page=page, per_page=50)
    return templates.TemplateResponse(request, "returns/list.html", {
        "returns": pagination.items,
        "pagination": pagination,
        "status": status,
        "customer": customer,
        "status_labels": STATUS_LABELS,
    })


# ── 新規登録フォーム ──────────────────────────────────────
@router.get("/new", response_class=HTMLResponse)
def new_return_form(
    request: Request, db: Session = Depends(get_db),
    sale_id: str = "",
):
    sale = None
    if sale_id:
        sale = db.query(Sale).options(
            joinedload(Sale.customer),
            joinedload(Sale.product),
        ).filter(Sale.id == int(sale_id)).first()
    customers = db.query(Customer).order_by(Customer.name).all()
    products  = db.query(Product).order_by(Product.name).all()
    return templates.TemplateResponse(request, "returns/form.html", {
        "sale": sale,
        "customers": customers,
        "products": products,
        "reason_labels": REASON_LABELS,
        "today": date.today().isoformat(),
    })


# ── 登録POST ─────────────────────────────────────────────
@router.post("/new")
async def create_return(
    request: Request,
    db: Session = Depends(get_db),
    sale_id: str       = Form(""),
    customer_id: int   = Form(...),
    product_id: int    = Form(...),
    quantity: int      = Form(...),
    return_date: str   = Form(...),
    reason: str        = Form(""),
    restock: str       = Form(""),
    notes: str         = Form(""),
):
    staff = getattr(request.state, "staff", None)
    ret = Return(
        return_number=_gen_return_number(db),
        sale_id=int(sale_id) if sale_id else None,
        customer_id=customer_id,
        product_id=product_id,
        quantity=quantity,
        return_date=date.fromisoformat(return_date),
        reason=reason or None,
        restock=bool(restock),
        status="restocked" if restock else "returned",
        notes=notes or None,
        staff_name=staff["name"] if staff else None,
    )
    db.add(ret)

    # 在庫戻し
    if restock:
        crud.move_inventory(
            db, product_id, "in", quantity,
            reason="返品入庫",
            note=f"返品番号: {ret.return_number} / {reason or ''}",
            staff_name=staff["name"] if staff else None,
        )

    db.commit()
    return RedirectResponse(f"/returns/{ret.id}", status_code=303)


# ── 詳細 ─────────────────────────────────────────────────
@router.get("/{return_id}", response_class=HTMLResponse)
def return_detail(return_id: int, request: Request, db: Session = Depends(get_db)):
    ret = db.query(Return).options(
        joinedload(Return.customer),
        joinedload(Return.product),
        joinedload(Return.sale),
    ).filter(Return.id == return_id).first()
    if not ret:
        raise HTTPException(404)
    return templates.TemplateResponse(request, "returns/detail.html", {
        "ret": ret,
        "status_labels": STATUS_LABELS,
        "reason_labels": REASON_LABELS,
    })
