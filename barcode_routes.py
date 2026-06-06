from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy.orm import Session
from datetime import date, datetime

from database import get_db
import models

router = APIRouter(prefix="/barcode", tags=["barcode"])
from templates_config import templates


def get_current_staff(request: Request):
    return request.state.staff


@router.get("/receive", response_class=HTMLResponse)
def barcode_receive_page(request: Request, db: Session = Depends(get_db)):
    staff = get_current_staff(request)
    return templates.TemplateResponse(request, "barcode_receive.html", {
        "current_user": staff,
        "today": date.today().isoformat()
    })


@router.get("/ship", response_class=HTMLResponse)
def barcode_ship_page(request: Request, db: Session = Depends(get_db)):
    staff = get_current_staff(request)
    customers = db.query(models.Customer).order_by(models.Customer.name).all()
    return templates.TemplateResponse(request, "barcode_ship.html", {
        "current_user": staff,
        "customers": customers,
        "today": date.today().isoformat()
    })


def parse_gs1_128(raw: str) -> dict:
    """GS1-128バーコードをパースしてGTIN・ロット番号等を抽出する"""
    result = {"gtin": None, "lot": None, "serial": None, "candidates": []}
    # FNC1文字 (0x1D) またはカッコ形式の両方に対応
    # 例: \x1d0104580799900201\x1d1012501
    # 例: (01)04580799900201(10)12501
    text = raw.replace('\x1d', '').replace('\x1e', '')
    # カッコ形式を正規化
    import re
    bracket = re.sub(r'\((\d{2})\)', r'\1', text)  # (01) → 01
    # AIパース（固定長AI）
    ai_lengths = {'00': 18, '01': 14, '02': 14, '10': None, '11': 6, '17': 6,
                  '20': 2, '21': None, '30': None}
    pos = 0
    while pos < len(bracket):
        ai = bracket[pos:pos+2]
        if ai in ai_lengths:
            length = ai_lengths[ai]
            pos += 2
            if length:
                val = bracket[pos:pos+length]
                pos += length
            else:
                # 可変長: 次のAIか末尾まで
                end = len(bracket)
                for next_ai in ai_lengths:
                    idx = bracket.find(next_ai, pos)
                    if idx > pos:
                        end = min(end, idx)
                val = bracket[pos:end]
                pos = end
            if ai == '01':
                result['gtin'] = val
            elif ai == '10':
                result['lot'] = val
            elif ai == '21':
                result['serial'] = val
            result['candidates'].append(val)
        else:
            pos += 1
    return result


@router.get("/api/search")
def barcode_search(code: str, request: Request, db: Session = Depends(get_db)):
    code = code.strip()

    # GS1-128かどうか判定（FNC1文字含む or 数字+長い文字列）
    search_codes = [code]
    if '\x1d' in code or '\x1e' in code or (len(code) > 15 and code[:2].isdigit()):
        parsed = parse_gs1_128(code)
        for v in [parsed['gtin'], parsed['lot'], parsed['serial']] + parsed['candidates']:
            if v and v not in search_codes:
                search_codes.append(v)

    # SKUで検索（複数候補を順に試す）
    product = None
    for c in search_codes:
        product = db.query(models.Product).filter(models.Product.sku == c).first()
        if product:
            break

    # 見つからなければシリアル番号・ロット番号で検索
    if not product:
        for c in search_codes:
            history = db.query(models.InventoryHistory).filter(
                (models.InventoryHistory.serial_number == c) |
                (models.InventoryHistory.lot_number == c)
            ).first()
            if history:
                product = db.query(models.Product).filter(
                    models.Product.id == history.product_id
                ).first()
                if product:
                    break

    if not product:
        return JSONResponse({"found": False})

    inventory = db.query(models.Inventory).filter(
        models.Inventory.product_id == product.id
    ).first()
    stock = inventory.current_stock if inventory else 0

    return JSONResponse({
        "found": True,
        "product": {
            "id": product.id,
            "name": product.name,
            "sku": product.sku or "",
            "maker": product.maker or "",
            "unit": product.unit or "個",
            "serial_type": product.tracking_type or "none",
            "alert_threshold": product.stock_alert_threshold or 0,
            "stock": stock,
        }
    })


@router.post("/api/receive")
async def barcode_receive(request: Request, db: Session = Depends(get_db)):
    staff = get_current_staff(request)
    try:
        body = await request.json()
        product_id   = int(body["product_id"])
        quantity     = int(body["quantity"])
        serial_no    = body.get("serial_no")
        lot_no       = body.get("lot_no")
        expiry_date  = body.get("expiry_date")
        supplier     = body.get("supplier")
        memo         = body.get("memo")

        product = db.query(models.Product).filter(
            models.Product.id == product_id
        ).first()
        if not product:
            return JSONResponse({"success": False, "error": "商品が見つかりません"}, status_code=404)

        # 在庫加算
        inventory = db.query(models.Inventory).filter(
            models.Inventory.product_id == product_id
        ).first()
        if inventory:
            inventory.current_stock += quantity
            inventory.updated_at = datetime.now()
        else:
            inventory = models.Inventory(
                product_id=product_id,
                current_stock=quantity
            )
            db.add(inventory)

        # 入出庫履歴
        history = models.InventoryHistory(
            product_id=product_id,
            movement_type="in",
            quantity=quantity,
            serial_number=serial_no,
            lot_number=lot_no,
            expiry_date=expiry_date,
            reason=supplier,
            note=memo,
            staff_name=staff["name"],
        )
        db.add(history)
        db.commit()
        return JSONResponse({"success": True})

    except Exception as e:
        db.rollback()
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@router.post("/api/ship")
async def barcode_ship(request: Request, db: Session = Depends(get_db)):
    staff = get_current_staff(request)
    try:
        body = await request.json()
        product_id  = int(body["product_id"])
        ship_type   = body.get("ship_type", "sale")
        quantity    = int(body["quantity"])
        serial_no   = body.get("serial_no")
        lot_no      = body.get("lot_no")
        customer_id = body.get("customer_id")
        memo        = body.get("memo")

        product = db.query(models.Product).filter(
            models.Product.id == product_id
        ).first()
        if not product:
            return JSONResponse({"success": False, "error": "商品が見つかりません"}, status_code=404)

        # 在庫減算（[I5] 不足時はValueError）
        try:
            import crud
            crud.move_inventory(
                db, product_id, "out", quantity,
                reason=f"バーコード出荷({ship_type})",
                note=memo or "",
                serial_number=serial_no,
                lot_number=lot_no,
                staff_name=staff["name"] if staff else None,
            )
        except ValueError as ve:
            return JSONResponse({"success": False, "error": str(ve)}, status_code=400)

        return JSONResponse({"success": True})

    except Exception as e:
        db.rollback()
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)
