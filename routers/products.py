import csv
import io
from fastapi import APIRouter, Depends, Request, Form, File, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, Response
from sqlalchemy.orm import Session
from database import get_db
import crud

router = APIRouter()
from templates_config import templates


@router.get("/products", response_class=HTMLResponse)
def list_products(request: Request, search: str = "", maker: str = "", category: str = "", page: int = 1, db: Session = Depends(get_db)):
    pager = crud.paginate(
        crud.get_products_query(db, search=search, maker=maker, category=category),
        page=page,
    )
    return templates.TemplateResponse("products/list.html", {
        "request": request, "products": pager.items, "pager": pager,
        "search": search, "maker": maker, "category": category
    })


@router.get("/products/new", response_class=HTMLResponse)
def new_product_form(request: Request):
    return templates.TemplateResponse("products/form.html", {"request": request, "product": None})


@router.get("/products/csv-template")
def csv_template_dl():
    headers = [
        "商品名","カテゴリ","商品コード(SKU)","単価(円)","単位",
        "管理番号種別","在庫アラート閾値","在庫アラート有効",
        "メーカー名","JANコード","承認番号","クラス分類","販売区分",
        "型式・仕様","滅菌状態","備考"
    ]
    sample = [
        "サンプル商品","医療機器","SKU-001","10000","個",
        "なし","10","有効",
        "メーカー名","","","クラスⅡ","代理店",
        "","未設定",""
    ]
    note = [
        "※商品名・単価は必須",
        "医療機器 または 生ハム",
        "","","",
        "なし / シリアル番号 / ロット番号","","有効 または 無効",
        "","","",
        "未設定 / 雑品 / クラスⅠ / クラスⅡ / クラスⅢ / クラスⅣ",
        "未設定 / メーカー / 代理店",
        "","未設定 / 滅菌済み / 未滅菌",""
    ]
    lines = [
        ",".join(headers),
        ",".join(sample),
        ",".join(note),
    ]
    content = "\n".join(lines) + "\n"
    return Response(
        content=content.encode("utf-8-sig"),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=products_template.csv"}
    )


@router.post("/products/csv-import")
async def csv_import(file: UploadFile = File(...), db: Session = Depends(get_db)):
    # 日本語列名 → 内部キー のマッピング
    COL = {
        "商品名": "name", "カテゴリ": "category", "商品コード(SKU)": "sku",
        "単価(円)": "unit_price", "単位": "unit",
        "管理番号種別": "tracking_type", "在庫アラート閾値": "stock_alert_threshold",
        "在庫アラート有効": "alert_enabled", "メーカー名": "maker",
        "JANコード": "jan_code", "承認番号": "approval_number",
        "クラス分類": "device_class", "販売区分": "sales_role",
        "型式・仕様": "model_spec", "滅菌状態": "sterility", "備考": "notes",
        # 英語列名も引き続き受け付ける（後方互換）
        "name": "name", "category": "category", "sku": "sku",
        "unit_price": "unit_price", "unit": "unit",
        "tracking_type": "tracking_type", "stock_alert_threshold": "stock_alert_threshold",
        "alert_enabled": "alert_enabled", "maker": "maker",
        "jan_code": "jan_code", "approval_number": "approval_number",
        "device_class": "device_class", "sales_role": "sales_role",
        "model_spec": "model_spec", "sterility": "sterility", "notes": "notes",
    }
    # 日本語値 → 内部コード
    CATEGORY_MAP  = {"医療機器": "medical", "生ハム": "ham", "medical": "medical", "ham": "ham"}
    TRACKING_MAP  = {"なし": "none", "シリアル番号": "serial", "ロット番号": "lot",
                     "none": "none", "serial": "serial", "lot": "lot"}
    CLASS_MAP     = {"未設定": "", "雑品": "misc", "クラスⅠ": "1", "クラスⅡ": "2",
                     "クラスⅢ": "3", "クラスⅣ": "4",
                     "misc": "misc", "1": "1", "2": "2", "3": "3", "4": "4"}
    ROLE_MAP      = {"未設定": "", "メーカー": "maker", "代理店": "distributor",
                     "maker": "maker", "distributor": "distributor"}
    STERILITY_MAP = {"未設定": "", "滅菌済み": "sterile", "未滅菌": "non_sterile",
                     "sterile": "sterile", "non_sterile": "non_sterile"}

    def g(row_norm, key, default=""):
        return row_norm.get(key, default) or default

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
        fieldnames = reader.fieldnames or []

        # 列名を内部キーに正規化
        def normalize_row(row):
            return {COL[k]: v.strip() for k, v in row.items() if k in COL}

        # 必須列チェック（日英どちらでも可）
        mapped_fields = {COL[f] for f in fieldnames if f in COL}
        if not {"name", "unit_price"}.issubset(mapped_fields):
            return JSONResponse({"error": "必須列「商品名」「単価(円)」が不足しています"}, status_code=400)

        created = 0
        errors = []
        for i, raw_row in enumerate(reader, start=2):
            # 注釈行スキップ（1列目が「※」で始まる）
            first_val = list(raw_row.values())[0] if raw_row else ""
            if first_val.startswith("※"):
                continue
            try:
                row = normalize_row(raw_row)
                name = g(row, "name")
                if not name:
                    errors.append(f"{i}行目: 商品名が空")
                    continue
                price_str = g(row, "unit_price", "0").replace(",", "")
                alert_raw = g(row, "alert_enabled", "有効").lower()
                alert_enabled = alert_raw not in ("無効", "false", "0", "off")
                crud.create_product(db, {
                    "name": name,
                    "category": CATEGORY_MAP.get(g(row, "category", "医療機器"), "medical"),
                    "sku": g(row, "sku") or None,
                    "unit_price": float(price_str) if price_str else 0,
                    "unit": g(row, "unit"),
                    "tracking_type": TRACKING_MAP.get(g(row, "tracking_type", "なし"), "none"),
                    "stock_alert_threshold": int(g(row, "stock_alert_threshold", "10") or 10),
                    "alert_enabled": alert_enabled,
                    "maker": g(row, "maker") or None,
                    "jan_code": g(row, "jan_code") or None,
                    "approval_number": g(row, "approval_number") or None,
                    "device_class": CLASS_MAP.get(g(row, "device_class", ""), "") or None,
                    "sales_role": g(row, "sales_role") or None,
                })
                success_count += 1
            except Exception as e:
                errors.append(f"{i}\u884c\u76ee: {e}")

        if errors:
            return templates.TemplateResponse("products/bulk_import.html", {
                "request": request,
                "errors": errors,
                "success_count": success_count,
            })
        return RedirectResponse("/products", status_code=303)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


    return templates.TemplateResponse("products/bulk_import.html", {
        "request": request,
        "errors": [],
        "success_count": 0,
    })


@router.get("/products/{product_id}", response_class=HTMLResponse)
def show_product(product_id: int, request: Request, db: Session = Depends(get_db)):
    from fastapi import HTTPException
    product = crud.get_product(db, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="商品が見つかりません")
    return RedirectResponse(f"/products/{product_id}/edit", status_code=302)


@router.get("/products/{product_id}/edit", response_class=HTMLResponse)
def edit_product_form(product_id: int, request: Request, db: Session = Depends(get_db)):
    from fastapi import HTTPException
    product = crud.get_product(db, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="商品が見つかりません")
    return templates.TemplateResponse("products/form.html", {"request": request, "product": product})


@router.post("/products/{product_id}/edit")
def edit_product(
    product_id: int, request: Request, db: Session = Depends(get_db),
    name: str = Form(...), category: str = Form("medical"),
    sku: str = Form(""), unit_price: float = Form(...), unit: str = Form(""),
    tracking_type: str = Form("none"), stock_alert_threshold: int = Form(10),
    alert_enabled: str = Form(None), maker: str = Form(""),
    jan_code: str = Form(""), approval_number: str = Form(""),
    device_class: str = Form(""), sales_role: str = Form(""),
    model_spec: str = Form(""), sterility: str = Form(""), notes: str = Form(""),
):
    from fastapi import HTTPException
    product = crud.get_product(db, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="商品が見つかりません")
    crud.update_product(db, product_id, {
        "name": name, "category": category,
        "sku": sku or None, "unit_price": unit_price, "unit": unit,
        "tracking_type": tracking_type,
        "stock_alert_threshold": stock_alert_threshold,
        "alert_enabled": alert_enabled == "on",
        "maker": maker or None, "jan_code": jan_code or None,
        "approval_number": approval_number or None,
        "device_class": device_class or None, "sales_role": sales_role or None,
        "model_spec": model_spec or None, "sterility": sterility or None,
        "notes": notes or None,
    })
    return RedirectResponse("/products", status_code=303)


@router.post("/products/{product_id}/delete")
def delete_product(product_id: int, request: Request, db: Session = Depends(get_db)):
    # [I10] 整合性チェックはcrud側で実施、エラーはリダイレクトで返却
    from fastapi import HTTPException
    from urllib.parse import quote as urlquote
    staff = request.state.staff
    if not staff or staff.get("role") not in ("admin", "manager"):
        return RedirectResponse("/products?error=権限がありません", status_code=303)
    try:
        crud.delete_product(db, product_id)
    except HTTPException as e:
        msg = urlquote(e.detail)
        return RedirectResponse(f"/products?error={msg}", status_code=303)
    return RedirectResponse("/products", status_code=303)
