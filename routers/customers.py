import io
import csv
from fastapi import APIRouter, Depends, Request, Form, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
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
    category: str = Form("hospital"),
    phone: str = Form(""),
    email: str = Form(""),
    address: str = Form(""),
    trading_terms: str = Form(""),
    notes: str = Form(""),
    staff_id: str = Form(""),
    db: Session = Depends(get_db)
):
    crud.create_customer(db, {
        "name": name, "category": category,
        "phone": phone, "email": email, "address": address,
        "trading_terms": trading_terms or None,
        "notes": notes,
        "staff_id": int(staff_id) if staff_id else None
    })
    return RedirectResponse("/customers", status_code=303)


@router.get("/customers/import", response_class=HTMLResponse)
def import_form(request: Request):
    return templates.TemplateResponse("customers/import.html", {"request": request, "results": None})


@router.get("/customers/template")
def download_template():
    content = "name,category,phone,email,address,trading_terms,notes\n"
    content += "医療法人サンプル,hospital,03-0000-0000,sample@example.com,東京都〇〇区1-1-1,月末締め翌月末払い,備考\n"
    content += "取引先サンプル,supplier,06-0000-0000,sample2@example.com,大阪府〇〇市1-1-1,,備考\n"
    return StreamingResponse(
        io.BytesIO(content.encode("utf-8-sig")),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=customers_template.csv"}
    )


@router.post("/customers/import", response_class=HTMLResponse)
async def import_customers(request: Request, file: UploadFile = File(...), db: Session = Depends(get_db)):
    results = {"success": 0, "skip": 0, "errors": []}
    try:
        content = await file.read()
        try:
            text = content.decode("utf-8-sig")
        except Exception:
            text = content.decode("shift_jis", errors="replace")

        reader = csv.DictReader(io.StringIO(text))
        for i, row in enumerate(reader, start=2):
            name = row.get("name", "").strip()
            if not name:
                results["skip"] += 1
                continue
            category = row.get("category", "hospital").strip()
            if category not in ("hospital", "supplier"):
                category = "hospital"
            try:
                crud.create_customer(db, {
                    "name": name, "category": category,
                    "phone": row.get("phone", "").strip() or None,
                    "email": row.get("email", "").strip() or None,
                    "address": row.get("address", "").strip() or None,
                    "trading_terms": row.get("trading_terms", "").strip() or None,
                    "notes": row.get("notes", "").strip() or None,
                })
                results["success"] += 1
            except Exception as e:
                results["errors"].append(f"{i}行目：{name} - {str(e)[:50]}")
    except Exception as e:
        results["errors"].append(f"ファイル読込エラー：{str(e)}")

    return templates.TemplateResponse("customers/import.html", {"request": request, "results": results})


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
    category: str = Form("hospital"),
    phone: str = Form(""),
    email: str = Form(""),
    address: str = Form(""),
    trading_terms: str = Form(""),
    notes: str = Form(""),
    staff_id: str = Form(""),
    db: Session = Depends(get_db)
):
    crud.update_customer(db, customer_id, {
        "name": name, "category": category,
        "phone": phone, "email": email, "address": address,
        "trading_terms": trading_terms or None,
        "notes": notes,
        "staff_id": int(staff_id) if staff_id else None
    })
    return RedirectResponse(f"/customers/{customer_id}", status_code=303)


@router.post("/customers/{customer_id}/delete")
def delete_customer(customer_id: int, db: Session = Depends(get_db)):
    crud.delete_customer(db, customer_id)
    return RedirectResponse("/customers", status_code=303)
