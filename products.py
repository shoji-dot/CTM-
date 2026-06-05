from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from database import get_db
import crud

router = APIRouter()
templates = Jinja2Templates(directory="templates")


@router.get("/products", response_class=HTMLResponse)
def list_products(request: Request, search: str = "", category: str = "", db: Session = Depends(get_db)):
    products = crud.get_products(db, search=search, category=category)
    return templates.TemplateResponse("products/list.html", {
        "request": request, "products": products,
        "search": search, "category": category
    })


@router.get("/products/new", response_class=HTMLResponse)
def new_product_form(request: Request):
    return templates.TemplateResponse("products/form.html", {"request": request, "product": None})


@router.post("/products/new")
def create_product(
    name: str = Form(...),
    category: str = Form("medical"),
    sku: str = Form(""),
    unit_price: float = Form(...),
    unit: str = Form(""),
    stock_alert_threshold: int = Form(10),
    notes: str = Form(""),
    db: Session = Depends(get_db)
):
    crud.create_product(db, {
        "name": name, "category": category, "sku": sku or None,
        "unit_price": unit_price, "unit": unit,
        "stock_alert_threshold": stock_alert_threshold, "notes": notes
    })
    return RedirectResponse("/products", status_code=303)


@router.get("/products/{product_id}", response_class=HTMLResponse)
def detail_product(product_id: int, request: Request, db: Session = Depends(get_db)):
    product = crud.get_product(db, product_id)
    histories = crud.get_inventory_history(db, product_id=product_id)
    return templates.TemplateResponse("products/detail.html", {
        "request": request, "product": product, "histories": histories
    })


@router.get("/products/{product_id}/edit", response_class=HTMLResponse)
def edit_product_form(product_id: int, request: Request, db: Session = Depends(get_db)):
    product = crud.get_product(db, product_id)
    return templates.TemplateResponse("products/form.html", {"request": request, "product": product})


@router.post("/products/{product_id}/edit")
def update_product(
    product_id: int,
    name: str = Form(...),
    category: str = Form("medical"),
    sku: str = Form(""),
    unit_price: float = Form(...),
    unit: str = Form(""),
    stock_alert_threshold: int = Form(10),
    notes: str = Form(""),
    db: Session = Depends(get_db)
):
    crud.update_product(db, product_id, {
        "name": name, "category": category, "sku": sku or None,
        "unit_price": unit_price, "unit": unit,
        "stock_alert_threshold": stock_alert_threshold, "notes": notes
    })
    return RedirectResponse(f"/products/{product_id}", status_code=303)


@router.post("/products/{product_id}/duplicate")
def duplicate_product(product_id: int, db: Session = Depends(get_db)):
    new_product = crud.duplicate_product(db, product_id)
    return RedirectResponse(f"/products/{new_product.id}/edit", status_code=303)


@router.post("/products/{product_id}/delete")
def delete_product(product_id: int, request: Request, db: Session = Depends(get_db)):
    # [I10] 削除エラーをクエリパラメータ経由で表示
    from fastapi import HTTPException
    from urllib.parse import quote as urlquote
    try:
        crud.delete_product(db, product_id)
    except HTTPException as e:
        msg = urlquote(e.detail)
        return RedirectResponse(f"/products?error={msg}", status_code=303)
    return RedirectResponse("/products", status_code=303)
