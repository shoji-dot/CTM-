from datetime import date
from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from database import get_db
import crud

router = APIRouter()
templates = Jinja2Templates(directory="templates")


@router.get("/quotes", response_class=HTMLResponse)
def list_quotes(request: Request, status: str = "", db: Session = Depends(get_db)):
    quotes = crud.get_quotes(db, status=status)
    return templates.TemplateResponse("quotes/list.html", {
        "request": request, "quotes": quotes, "status": status
    })


@router.get("/quotes/new", response_class=HTMLResponse)
def new_quote_form(
    request: Request,
    db: Session = Depends(get_db),
    repair_id: str = "",
    customer_id: str = "",
    end_user_id: str = "",
    product_id: str = "",
    amount: str = "",
    repair_number: str = "",
):
    customers = crud.get_customers(db)
    products = crud.get_products(db)
    # 修理案件からの引き渡しデータ
    prefill = {
        "repair_id": repair_id,
        "customer_id": int(customer_id) if customer_id else None,
        "end_user_id": int(end_user_id) if end_user_id else None,
        "product_id": int(product_id) if product_id else None,
        "amount": float(amount) if amount else None,
        "repair_number": repair_number,
    }
    return templates.TemplateResponse("quotes/form.html", {
        "request": request, "customers": customers, "products": products, "prefill": prefill,
    })


@router.post("/quotes/new")
async def create_quote(request: Request, db: Session = Depends(get_db)):
    form_data = await request.form()
    customer_id = int(form_data["customer_id"])
    valid_until_str = form_data.get("valid_until", "")
    valid_until = date.fromisoformat(valid_until_str) if valid_until_str else None
    notes = form_data.get("notes", "")
    repair_id = form_data.get("repair_id", "")

    product_ids = form_data.getlist("product_id[]")
    quantities = form_data.getlist("quantity[]")
    unit_prices = form_data.getlist("unit_price[]")

    items = []
    for i, (pid, qty) in enumerate(zip(product_ids, quantities)):
        if pid and qty:
            item = {"product_id": int(pid), "quantity": int(qty)}
            if i < len(unit_prices) and unit_prices[i]:
                item["unit_price"] = float(unit_prices[i])
            items.append(item)

    staff = getattr(request.state, "staff", None)
    created_by_id = staff["id"] if staff else None
    q = crud.create_quote(db, customer_id=customer_id, valid_until=valid_until, notes=notes, items=items, created_by_id=created_by_id)

    # 修理案件と紐付け
    if repair_id:
        from models import Repair
        repair = db.query(Repair).filter(Repair.id == int(repair_id)).first()
        if repair:
            repair.quote_id = q.id
            db.commit()
        return RedirectResponse(f"/repairs/{repair_id}", status_code=303)

    return RedirectResponse("/quotes", status_code=303)


@router.get("/quotes/{quote_id}", response_class=HTMLResponse)
def detail_quote(quote_id: int, request: Request, db: Session = Depends(get_db)):
    quote = crud.get_quote(db, quote_id)
    return templates.TemplateResponse("quotes/detail.html", {"request": request, "quote": quote})


@router.post("/quotes/{quote_id}/status")
def change_status(quote_id: int, status: str = Form(...), db: Session = Depends(get_db)):
    crud.update_quote_status(db, quote_id, status)
    return RedirectResponse(f"/quotes/{quote_id}", status_code=303)


@router.post("/quotes/{quote_id}/accept")
def accept_quote(quote_id: int, db: Session = Depends(get_db)):
    crud.accept_quote(db, quote_id)
    return RedirectResponse(f"/quotes/{quote_id}", status_code=303)


@router.post("/quotes/{quote_id}/delete")
def delete_quote(quote_id: int, db: Session = Depends(get_db)):
    crud.delete_quote(db, quote_id)
    return RedirectResponse("/quotes", status_code=303)
