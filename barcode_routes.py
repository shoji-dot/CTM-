from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from datetime import date, datetime

from database import get_db
import models

router = APIRouter(prefix="/barcode", tags=["barcode"])
templates = Jinja2Templates(directory="templates")


def get_current_staff(request: Request):
    return request.state.staff


@router.get("/receive", response_class=HTMLResponse)
def barcode_receive_page(request: Request, db: Session = Depends(get_db)):
    staff = get_current_staff(request)
    return templates.TemplateResponse("barcode_receive.html", {
        "request": request,
        "current_user": staff,
        "today": date.today().isoformat(),
    })


@router.get("/ship", response_class=HTMLResponse)
def barcode_ship_page(request: Request, db: Session = Depends(get_db)):
    staff = get_current_staff(request)
    customers = db.query(models.Customer).order_by(models.Customer.name).all()
    return templates.TemplateResponse("barcode_ship.html", {
        "request": request,
        "current_user": staff,
        "customers": customers,
        "today": date.today().isoformat(),
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
        customer_id = int(body["customer_id"])
        end_user    = body.get("end_user")
        serial_no   = body.get("serial_no")
        lot_no      = body.get("lot_no")
        expiry_date = body.get("expiry_date")
        ship_date   = body.get("ship_date") or date.today().isoformat()
        return_date = body.get("return_date")
        memo        = body.get("memo")

        # 在庫確認
        inventory = db.query(models.Inventory).filter(
            models.Inventory.product_id == product_id
        ).first()
        stock = inventory.current_stock if inventory else 0
        if stock < quantity:
            return JSONResponse(
                {"success": False, "error": f"在庫不足です（現在庫: {stock}）"},
                status_code=400
            )

        # 在庫減算
        inventory.current_stock -= quantity
        inventory.updated_at = datetime.now()

        # 出荷番号生成
        now = datetime.now()
        shipment_number = f"SH{now.strftime('%Y%m%d%H%M%S')}"

        # 出荷レコード
        shipment = models.Shipment(
            shipment_number=shipment_number,
            shipment_type=ship_type,
            customer_id=customer_id,
            product_id=product_id,
            quantity=quantity,
            serial_number=serial_no,
            lot_number=lot_no,
            expiry_date=expiry_date,
            shipped_date=ship_date,
            return_due_date=return_date or None,
            notes=memo,
            staff_name=staff["name"],
            status="shipped",
        )
        db.add(shipment)

        # 入出庫履歴
        history = models.InventoryHistory(
            product_id=product_id,
            movement_type="out",
            quantity=quantity,
            serial_number=serial_no,
            lot_number=lot_no,
            expiry_date=expiry_date,
            note=memo,
            staff_name=staff["name"],
        )
        db.add(history)
        db.commit()
        return JSONResponse({"success": True, "shipment_id": shipment.id})

    except Exception as e:
        db.rollback()
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)