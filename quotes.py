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
def new_quote_form(request: Request, db: Session = Depends(get_db)):
    customers = crud.get_customers(db)
    products = crud.get_products(db)
    return templates.TemplateResponse("quotes/form.html", {
        "request": request, "customers": customers, "products": products
    })


@router.post("/quotes/new")
async def create_quote(request: Request, db: Session = Depends(get_db)):
    form_data = await request.form()
    customer_id = int(form_data["customer_id"])
    valid_until_str = form_data.get("valid_until", "")
    valid_until = date.fromisoformat(valid_until_str) if valid_until_str else None
    notes = form_data.get("notes", "")

    product_ids = form_data.getlist("product_id[]")
    quantities = form_data.getlist("quantity[]")

    items = []
    for pid, qty in zip(product_ids, quantities):
        if pid and qty:
            items.append({"product_id": int(pid), "quantity": int(qty)})

    crud.create_quote(db, customer_id=customer_id, valid_until=valid_until, notes=notes, items=items)
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
