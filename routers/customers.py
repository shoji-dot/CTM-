import io
import csv
from fastapi import APIRouter, Depends, Request, Form, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse, JSONResponse
from sqlalchemy.orm import Session
from database import get_db
from models import Staff, Customer
import crud

router = APIRouter()
from templates_config import templates


@router.get("/customers", response_class=HTMLResponse)
def list_customers(request: Request, search: str = "", category: str = "",
                   page: int = 1, db: Session = Depends(get_db)):
    # [I4] ページネーション適用
    from sqlalchemy.orm import Session as _S
    q = db.query(crud.Customer)
    if search: q = q.filter(crud.Customer.name.contains(search))
    if category: q = q.filter(crud.Customer.category == category)
    q = q.order_by(crud.Customer.id.desc())
    pager = crud.paginate(q, page=page, per_page=50)
    return templates.TemplateResponse(request, "customers/list.html", {
        "customers": pager.items, "pagination": pager,
        "search": search, "category": category
    })


@router.get("/customers/new", response_class=HTMLResponse)
def new_customer_form(request: Request, db: Session = Depends(get_db)):
    staffs = db.query(Staff).filter(Staff.is_active == True).order_by(Staff.name).all()
    return templates.TemplateResponse(request, "customers/form.html", {
        "customer": None, "staffs": staffs
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
    return templates.TemplateResponse(request, "customers/import.html", {"results": None})


VALID_CATEGORIES = {"hospital", "clinic", "doctor", "dealer", "manufacturer"}
_CAT_LABELS = {"hospital":"病院","clinic":"クリニック","doctor":"医師","dealer":"ディーラー","manufacturer":"メーカー"}

@router.get("/api/customers", response_class=JSONResponse)
def api_search_customers(q: str = "", limit: int = 15, db: Session = Depends(get_db)):
    query = db.query(Customer)
    if q:
        query = query.filter(Customer.name.contains(q))
    items = query.order_by(Customer.name).limit(limit).all()
    return JSONResponse([{"id": c.id, "name": c.name, "cat_label": _CAT_LABELS.get(c.category, "")} for c in items])

@router.get("/customers/template")
def download_template():
    content = "name,category,phone,email,address,trading_terms,notes\n"
    content += "医療法人サンプル,hospital,03-0000-0000,sample@example.com,東京都〇〇区1-1-1,月末締め翌月末払い,備考\n"
    content += "クリニックサンプル,clinic,06-0000-0000,sample2@example.com,大阪府〇〇市1-1-1,月末締め,\n"
    content += "メーカーサンプル,manufacturer,052-000-0000,sample3@example.com,愛知県〇〇市1-1-1,,\n"
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
            if category not in VALID_CATEGORIES:
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

    return templates.TemplateResponse(request, "customers/import.html", {"results": results})


@router.get("/customers/{customer_id}", response_class=HTMLResponse)
def detail_customer(customer_id: int, request: Request, db: Session = Depends(get_db)):
    customer = crud.get_customer(db, customer_id)
    return templates.TemplateResponse(request, "customers/detail.html", {
        "customer": customer
    })


@router.get("/customers/{customer_id}/edit", response_class=HTMLResponse)
def edit_customer_form(customer_id: int, request: Request, db: Session = Depends(get_db)):
    customer = crud.get_customer(db, customer_id)
    staffs = db.query(Staff).filter(Staff.is_active == True).order_by(Staff.name).all()
    return templates.TemplateResponse(request, "customers/form.html", {
        "customer": customer, "staffs": staffs
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


@router.post("/customers/bulk-delete")
async def bulk_delete_customers(request: Request, db: Session = Depends(get_db)):
    from fastapi import HTTPException
    from fastapi.responses import JSONResponse as _JSONResponse
    staff = request.state.staff
    if not staff or staff.get("role") not in ("admin", "manager"):
        return _JSONResponse({"error": "権限がありません"}, status_code=403)
    body = await request.json()
    ids = body.get("ids", [])
    deleted = 0
    errors = []
    for cid in ids:
        try:
            crud.delete_customer(db, int(cid))
            deleted += 1
        except HTTPException as e:
            errors.append(f"ID {cid}: {e.detail}")
        except Exception as e:
            errors.append(f"ID {cid}: {str(e)}")
    return _JSONResponse({"deleted": deleted, "errors": errors})


@router.post("/customers/{customer_id}/delete")
def delete_customer(customer_id: int, request: Request, db: Session = Depends(get_db)):
    from fastapi import HTTPException
    from urllib.parse import quote as urlquote
    staff = request.state.staff
    if not staff or staff.get("role") not in ("admin", "manager"):
        return RedirectResponse("/customers?error=権限がありません（管理者以上が必要です）", status_code=303)
    try:
        crud.delete_customer(db, customer_id)
    except HTTPException as e:
        msg = urlquote(e.detail)
        return RedirectResponse(f"/customers?error={msg}", status_code=303)
    return RedirectResponse("/customers", status_code=303)
