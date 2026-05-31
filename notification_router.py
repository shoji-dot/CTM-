import os
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
import sqlite3

TEMPLATES = Jinja2Templates(directory="templates")
router    = APIRouter(prefix="/notifications", tags=["notifications"])
DB_PATH   = os.path.join(os.path.dirname(__file__), "sales_app.db")

NOTIF_TYPES = {
    "approval_request": "承認依頼",
    "approval_reject":  "差し戻し",
    "comment":          "コメント",
    "material_update":  "資料更新",
    "task":             "タスク",
}


def get_db():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def _staff_id(request: Request) -> int:
    staff = getattr(request.state, "staff", None)
    if staff is None:
        raise HTTPException(status_code=401)
    return staff["id"]


def create_notification(
    con: sqlite3.Connection,
    recipient_id: int,
    notif_type: str,
    message: str,
    resource_type: str = "",
    resource_id: int | None = None,
    link: str = "",
):
    con.execute(
        """
        INSERT INTO notifications
            (recipient_id, type, message, link, resource_type, resource_id)
        VALUES (?,?,?,?,?,?)
        """,
        (recipient_id, notif_type, message, link, resource_type, resource_id),
    )


@router.get("/", response_class=HTMLResponse)
async def notification_list(request: Request, unread_only: int = 0):
    staff_id = _staff_id(request)
    con = get_db()

    sql = "SELECT * FROM notifications WHERE recipient_id=?"
    params: list = [staff_id]
    if unread_only:
        sql += " AND is_sent=0"
    sql += " ORDER BY created_at DESC LIMIT 100"

    notifs = con.execute(sql, params).fetchall()
    unread_count = con.execute(
        "SELECT COUNT(*) FROM notifications WHERE recipient_id=? AND is_sent=0",
        (staff_id,),
    ).fetchone()[0]
    con.close()

    return TEMPLATES.TemplateResponse(
        "notifications/list.html",
        {
            "request": request,
            "notifs": notifs,
            "unread_count": unread_count,
            "unread_only": unread_only,
            "notif_labels": NOTIF_TYPES,
        },
    )


@router.get("/recent")
async def recent_notifications(request: Request):
    staff_id = _staff_id(request)
    con = get_db()
    rows = con.execute(
        """
        SELECT id, type, message, link, is_sent, created_at
        FROM notifications WHERE recipient_id=?
        ORDER BY created_at DESC LIMIT 5
        """,
        (staff_id,),
    ).fetchall()
    unread = con.execute(
        "SELECT COUNT(*) FROM notifications WHERE recipient_id=? AND is_sent=0",
        (staff_id,),
    ).fetchone()[0]
    con.close()
    return JSONResponse({
        "notifications": [dict(r) for r in rows],
        "unread_count": unread,
    })


@router.post("/{notif_id}/read")
async def mark_read(request: Request, notif_id: int):
    staff_id = _staff_id(request)
    con = get_db()
    con.execute(
        "UPDATE notifications SET is_sent=1 WHERE id=? AND recipient_id=?",
        (notif_id, staff_id),
    )
    con.commit()
    con.close()
    return JSONResponse({"status": "ok"})


@router.post("/read-all")
async def mark_all_read(request: Request):
    staff_id = _staff_id(request)
    con = get_db()
    con.execute(
        "UPDATE notifications SET is_sent=1 WHERE recipient_id=? AND is_sent=0",
        (staff_id,),
    )
    con.commit()
    con.close()
    return JSONResponse({"status": "ok"})