"""
customer_memo_router.py
顧客メモ機能: 病院名・医師名・メモ・検索
"""
import os
from fastapi import APIRouter, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
import sqlite3

TEMPLATES = Jinja2Templates(directory="templates")
router    = APIRouter(prefix="/customer-memos", tags=["customer_memos"])
DB_PATH   = os.path.join(os.path.dirname(__file__), "sales_app.db")


def get_db():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def _staff_id(request: Request) -> int:
    staff = getattr(request.state, "staff", None)
    if staff is None:
        raise HTTPException(status_code=401)
    return staff["id"]


@router.get("/", response_class=HTMLResponse)
async def memo_list(request: Request, q: str = ""):
    staff_id = _staff_id(request)
    con = get_db()

    sql = """
        SELECT cm.*, s.name AS staff_name
        FROM customer_memos cm
        LEFT JOIN staffs s ON cm.staff_id = s.id
        WHERE 1=1
    """
    params: list = []
    if q:
        sql += " AND (cm.hospital LIKE ? OR cm.doctor_name LIKE ? OR cm.memo LIKE ?)"
        like = f"%{q}%"
        params += [like, like, like]

    sql += " ORDER BY cm.updated_at DESC"
    memos = con.execute(sql, params).fetchall()
    con.close()

    return TEMPLATES.TemplateResponse(
        "customer_memos/list.html",
        {"request": request, "memos": memos, "q": q},
    )


@router.post("/")
async def create_memo(
    request: Request,
    hospital: str    = Form(...),
    doctor_name: str = Form(""),
    memo: str        = Form(""),
):
    staff_id = _staff_id(request)
    con = get_db()
    con.execute(
        "INSERT INTO customer_memos (hospital, doctor_name, memo, staff_id) VALUES (?,?,?,?)",
        (hospital, doctor_name, memo, staff_id),
    )
    con.commit()
    con.close()
    return JSONResponse({"status": "ok"})


@router.put("/{memo_id}")
async def update_memo(
    request: Request,
    memo_id: int,
    hospital: str    = Form(...),
    doctor_name: str = Form(""),
    memo: str        = Form(""),
):
    staff_id = _staff_id(request)
    con = get_db()
    con.execute(
        """
        UPDATE customer_memos
        SET hospital=?, doctor_name=?, memo=?,
            updated_at=datetime('now','localtime')
        WHERE id=?
        """,
        (hospital, doctor_name, memo, memo_id),
    )
    con.commit()
    con.close()
    return JSONResponse({"status": "ok"})


@router.delete("/{memo_id}")
async def delete_memo(request: Request, memo_id: int):
    _staff_id(request)
    con = get_db()
    con.execute("DELETE FROM customer_memos WHERE id=?", (memo_id,))
    con.commit()
    con.close()
    return JSONResponse({"status": "ok"})


@router.get("/json")
async def memo_list_json(request: Request, q: str = ""):
    """ダッシュボード埋め込み用 JSON API"""
    staff_id = _staff_id(request)
    con = get_db()
    sql = "SELECT * FROM customer_memos WHERE 1=1"
    params: list = []
    if q:
        sql += " AND (hospital LIKE ? OR doctor_name LIKE ? OR memo LIKE ?)"
        like = f"%{q}%"
        params += [like, like, like]
    sql += " ORDER BY updated_at DESC LIMIT 20"
    rows = [dict(r) for r in con.execute(sql, params).fetchall()]
    con.close()
    return JSONResponse(rows)
