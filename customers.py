from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from database import get_db
from models import Staff
import crud

router = APIRouter()
templates = Jinja2Templates(directory="templates")


@router.get("/customers", response_class=HTMLResponse)
def list_customers(request: Request, search: str = "", category: str = "", db: Session = Depends(get_db)):
    customers = crud.get_customers(db, search=search, category=category)
    return templates.TemplateResponse("customers/list.html", {
        "request": request, "customers": customers,
        "search": search, "category": category
    })


@router.get("/customers/new", response_class=HTMLResponse)
def new_customer_form(request: Request, db: Session = Depends(get_db)):
    staffs = db.query(Staff).filter(Staff.is_active == True).order_by(Staff.name).all()
    return templates.TemplateResponse("customers/form.html", {
        "request": request, "customer": None, "staffs": staffs
    })


@router.post("/customers/new")
def create_customer(
    request: Request,
    name: str = Form(...),
    category: str = Form("medical"),
    contact_name: str = Form(""),
    phone: str = Form(""),
    email: str = Form(""),
    address: str = Form(""),
    notes: str = Form(""),
    staff_id: str = Form(""),
    db: Session = Depends(get_db)
):
    crud.create_customer(db, {
        "name": name, "category": category, "contact_name": contact_name,
        "phone": phone, "email": email, "address": address, "notes": notes,
        "staff_id": int(staff_id) if staff_id else None
    })
    return RedirectResponse("/customers", status_code=303)


@router.get("/customers/{customer_id}", response_class=HTMLResponse)
def detail_customer(customer_id: int, request: Request, db: Session = Depends(get_db)):
    customer = crud.get_customer(db, customer_id)
    return templates.TemplateResponse("customers/detail.html", {
        "request": request, "customer": customer
    })


@router.get("/customers/{customer_id}/edit", response_class=HTMLResponse)
def edit_customer_form(customer_id: int, request: Request, db: Session = Depends(get_db)):
    customer = crud.get_customer(db, customer_id)
    staffs = db.query(Staff).filter(Staff.is_active == True).order_by(Staff.name).all()
    return templates.TemplateResponse("customers/form.html", {
        "request": request, "customer": customer, "staffs": staffs
    })


@router.post("/customers/{customer_id}/edit")
def update_customer(
    customer_id: int,
    name: str = Form(...),
    category: str = Form("medical"),
    contact_name: str = Form(""),
    phone: str = Form(""),
    email: str = Form(""),
    address: str = Form(""),
    notes: str = Form(""),
    staff_id: str = Form(""),
    db: Session = Depends(get_db)
):
    crud.update_customer(db, customer_id, {
        "name": name, "category": category, "contact_name": contact_name,
        "phone": phone, "email": email, "address": address, "notes": notes,
        "staff_id": int(staff_id) if staff_id else None
    })
    return RedirectResponse(f"/customers/{customer_id}", status_code=303)


@router.post("/customers/{customer_id}/delete")
def delete_customer(customer_id: int, db: Session = Depends(get_db)):
    crud.delete_customer(db, customer_id)
    return RedirectResponse("/customers", status_code=303)