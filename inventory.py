from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from database import get_db
import crud

router = APIRouter()
templates = Jinja2Templates(directory="templates")


@router.get("/inventory", response_class=HTMLResponse)
def list_inventory(request: Request, db: Session = Depends(get_db)):
    inventory = crud.get_inventory_list(db)
    alerts = crud.get_alerts(db)
    alert_ids = {a.product_id for a in alerts}
    return templates.TemplateResponse("inventory/list.html", {
        "request": request, "inventory": inventory, "alert_ids": alert_ids
    })


@router.get("/inventory/history", response_class=HTMLResponse)
def history(request: Request, db: Session = Depends(get_db)):
    histories = crud.get_inventory_history(db)
    products = crud.get_products(db)
    return templates.TemplateResponse("inventory/history.html", {
        "request": request, "histories": histories, "products": products
    })


@router.post("/inventory/move")
def move_inventory(
    product_id: int = Form(...),
    movement_type: str = Form(...),
    quantity: int = Form(...),
    reason: str = Form(""),
    note: str = Form(""),
    db: Session = Depends(get_db)
):
    crud.move_inventory(db, product_id, movement_type, quantity, reason=reason, note=note)
    return RedirectResponse("/inventory", status_code=303)
