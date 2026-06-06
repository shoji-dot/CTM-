"""
customer_memo_router.py
顧客メモ機能: 病院名・医師名・メモ・検索
"""
from datetime import datetime
from fastapi import APIRouter, Request, Form, HTTPException, Depends
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import text
from database import get_db

from templates_config import templates as TEMPLATES
router = APIRouter(prefix="/customer-memos", tags=["customer_memos"])


def _row(row):
    return dict(row._mapping)

def _rows(rows):
    return [_row(r) for r in rows]

def _staff_id(request: Request) -> int:
    staff = getattr(request.state, "staff", None)
    if staff is None:
        raise HTTPException(status_code=401)
    return staff["id"]


@router.get("/", response_class=HTMLResponse)
async def memo_list(request: Request, q: str = "", db: Session = Depends(get_db)):
    _staff_id(request)
    sql = """
        SELECT cm.*, s.name AS staff_name
        FROM customer_memos cm
        LEFT JOIN staffs s ON cm.staff_id = s.id
        WHERE 1=1
    """
    params: dict = {}
    if q:
        sql += " AND (cm.hospital LIKE :q1 OR cm.doctor_name LIKE :q2 OR cm.memo LIKE :q3)"
        like = f"%{q}%"
        params = {"q1": like, "q2": like, "q3": like}
    sql += " ORDER BY cm.updated_at DESC"
    memos = _rows(db.execute(text(sql), params).fetchall())
    return TEMPLATES.TemplateResponse(request, "customer_memos/list.html", {"memos": memos, "q": q},
    )


@router.post("/")
async def create_memo(
    request: Request,
    hospital: str    = Form(...),
    doctor_name: str = Form(""),
    memo: str        = Form(""),
    db: Session = Depends(get_db),
):
    staff_id = _staff_id(request)
    db.execute(
        text("INSERT INTO customer_memos (hospital, doctor_name, memo, staff_id) VALUES (:h,:d,:m,:s)"),
        {"h": hospital, "d": doctor_name, "m": memo, "s": staff_id},
    )
    db.commit()
    return JSONResponse({"status": "ok"})


@router.put("/{memo_id}")
async def update_memo(
    request: Request,
    memo_id: int,
    hospital: str    = Form(...),
    doctor_name: str = Form(""),
    memo: str        = Form(""),
    db: Session = Depends(get_db),
):
    _staff_id(request)
    db.execute(
        text("""
            UPDATE customer_memos
            SET hospital=:h, doctor_name=:d, memo=:m, updated_at=:t
            WHERE id=:i
        """),
        {"h": hospital, "d": doctor_name, "m": memo,
         "t": datetime.now().strftime('%Y-%m-%d %H:%M:%S'), "i": memo_id},
    )
    db.commit()
    return JSONResponse({"status": "ok"})


@router.delete("/{memo_id}")
async def delete_memo(request: Request, memo_id: int, db: Session = Depends(get_db)):
    _staff_id(request)
    db.execute(text("DELETE FROM customer_memos WHERE id=:i"), {"i": memo_id})
    db.commit()
    return JSONResponse({"status": "ok"})


@router.get("/json")
async def memo_list_json(request: Request, q: str = "", db: Session = Depends(get_db)):
    """ダッシュボード埋め込み用 JSON API"""
    _staff_id(request)
    sql = "SELECT * FROM customer_memos WHERE 1=1"
    params: dict = {}
    if q:
        sql += " AND (hospital LIKE :q1 OR doctor_name LIKE :q2 OR memo LIKE :q3)"
        like = f"%{q}%"
        params = {"q1": like, "q2": like, "q3": like}
 