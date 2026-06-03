import csv
import io
from fastapi import APIRouter, Depends, Request, Form, File, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, Response
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
        "request": request, "products": products, "search": search, "category": category
    })


@router.get("/products/new", response_class=HTMLResponse)
def new_product_form(request: Request):
    return templates.TemplateResponse("products/form.html", {"request": request, "product": None})


@router.get("/products/csv-template")
def csv_template_dl():
    headers = ["name","category","sku","unit_price","unit","stock_alert_threshold","maker","jan_code","approval_number","notes"]
    sample = ["サンプル商品","medical","SKU-001","10000","個","10","メーカー名","","",""]
    content = ",".join(headers) + "\n" + ",".join(sample) + "\n"
    return Response(
        content=content.encode("utf-8-sig"),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=products_template.csv"}
    )


@router.post("/products/csv-import")
async def csv_import(file: UploadFile = File(...), db: Session = Depends(get_db)):
    try:
        content = await file.read()
        text = None
        for enc in ("utf-8-sig", "utf-8", "cp932"):
            try:
                text = content.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        if text is None:
            return JSONResponse({"error": "文字コードの読み取りに失敗しました"}, status_code=400)
        reader = csv.DictReader(io.StringIO(text))
        required = {"name", "unit_price"}
        if not required.issubset(set(reader.fieldnames or [])):
            return JSONResponse({"error": f"必須列が不足しています: {required}"}, status_code=400)
        created = 0
        errors = []
        for i, row in enumerate(reader, start=2):
            try:
                name = row.get("name", "").strip()
                if not name:
                    errors.append(f"{i}行目: 商品名が空")
                    continue
                price_str = row.get("unit_price", "0").strip().replace(",", "")
                crud.create_product(db, {
                    "name": name,
                    "category": row.get("category", "medical").strip() or "medical",
                    "sku": row.get("sku", "").strip() or None,
                    "unit_price": float(price_str) if price_str else 0,
                    "unit": row.get("unit", "").strip(),
                    "stock_alert_threshold": int(row.get("stock_alert_threshold", 10) or 10),
                    "maker": row.get("maker", "").strip() or None,
                    "jan_code": row.get("jan_code", "").strip() or None,
                    "approval_number": row.get("approval_number", "").strip() or None,
                    "notes": row.get("notes", "").strip(),
                })
                created += 1
            except Exception as e:
                errors.append(f"{i}行目: {e}")
        msg = f"{created}件登録しました。"
        if errors:
            msg += " エラー: " + " / ".join(errors[:5])
        return RedirectResponse(f"/products?csv_msg={msg}", status_code=303)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@router.post("/products/new")
def create_product(
    name: str = Form(...), category: str = Form("medical"), sku: str = Form(""),
    unit_price: float = Form(...), unit: str = Form(""), stock_alert_threshold: int = Form(10),
    alert_enabled: str = Form("on"),
    tracking_type: str = Form("none"), maker: str = Form(""), jan_code: str = Form(""),
    approval_number: str = Form(""), device_class: str = Form(""), sales_role: str = Form(""),
    model_spec: str = Form(""), sterility: str = Form(""), notes: str = Form(""),
    db: Session = Depends(get_db)
):
    crud.create_product(db, {
        "name": name, "category": category, "sku": sku or None, "unit_price": unit_price,
        "unit": unit, "stock_alert_threshold": stock_alert_threshold,
        "alert_enabled": alert_enabled == "on",
        "tracking_type": tracking_type,
        "maker": maker or None, "jan_code": jan_code or None, "approval_number": approval_number or None,
        "device_class": device_class or None, "sales_role": sales_role or None,
        "model_spec": model_spec or None, "sterility": sterility or None, "notes": notes
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
    product_id: int, name: str = Form(...), category: str = Form("medical"), sku: str = Form(""),
    unit_price: float = Form(...), unit: str = Form(""), stock_alert_threshold: int = Form(10),
    alert_enabled: str = Form("on"),
    tracking_type: str = Form("none"), maker: str = Form(""), jan_code: str = Form(""),
    approval_number: str = Form(""), device_class: str = Form(""), sales_role: str = Form(""),
    model_spec: str = Form(""), sterility: str = Form(""), notes: str = Form(""),
    db: Session = Depends(get_db)
):
    crud.update_product(db, product_id, {
        "name": name, "category": category, "sku": sku or None, "unit_price": unit_price,
        "unit": unit, "stock_alert_threshold": stock_alert_threshold,
        "alert_enabled": alert_enabled == "on",
        "tracking_type": tracking_type,
        "maker": maker or None, "jan_code": jan_code or None, "approval_number": approval_number or None,
        "device_class": device_class or None, "sales_role": sales_role or None,
        "model_spec": model_spec or None, "sterility": sterility or None, "notes": notes
    })
    return RedirectResponse(f"/products/{product_id}", status_code=303)


@router.post("/products/{product_id}/duplicate")
def duplicate_product(product_id: int, db: Session = Depends(get_db)):
    new_product = crud.duplicate_product(db, product_id)
    return RedirectResponse(f"/products/{new_product.id}/edit", status_code=303)
