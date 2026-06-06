from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import text
from database import get_db

from templates_config import templates as TEMPLATES
router = APIRouter(prefix="/notifications", tags=["notifications"])

NOTIF_TYPES = {
    "approval_request": "承認依頼",
    "approval_reject":  "差し戻し",
    "comment":          "コメント",
    "material_update":  "資料更新",
    "task":             "タスク",
}


def _row(row):
    return dict(row._mapping)

def _rows(rows):
    return [_row(r) for r in rows]

def _staff_id(request: Request) -> int:
    staff = getattr(request.state, "staff", None)
    if staff is None:
        raise HTTPException(status_code=401)
    return staff["id"]


def create_notification(
    db: Session,
    recipient_id: int,
    notif_type: str,
    message: str,
    resource_type: str = "",
    resource_id: int | None = None,
    link: str = "",
):
    db.execute(
        text("""
            INSERT INTO notifications
                (recipient_id, type, message, link, resource_type, resource_id)
            VALUES (:r,:t,:m,:l,:rt,:ri)
        """),
        {"r": recipient_id, "t": notif_type, "m": message,
         "l": link, "rt": resource_type, "ri": resource_id},
    )


@router.get("/", response_class=HTMLResponse)
async def notification_list(
    request: Request,
    unread_only: int = 0,
    db: Session = Depends(get_db)
):
    staff_id = _staff_id(request)
    sql = "SELECT * FROM notifications WHERE recipient_id=:s"
    params: dict = {"s": staff_id}
    if unread_only:
        sql += " AND is_sent=FALSE"
    sql += " ORDER BY created_at DESC LIMIT 100"

    notifs = _rows(db.execute(text(sql), params).fetchall())
    unread_count = db.execute(
        text("SELECT COUNT(*) FROM notifications WHERE recipient_id=:s AND is_sent=FALSE"),
        {"s": staff_id},
    ).scalar()

    return TEMPLATES.TemplateResponse(request, "notifications/list.html", {
        "notifs": notifs,
            "unread_count": unread_count,
            "unread_only": unread_only,
            "notif_labels": NOTIF_TYPES,
        },
    )


@router.get("/recent")
async def recent_notifications(request: Request, db: Session = Depends(get_db)):
    staff_id = _staff_id(request)
    rows = _rows(db.execute(
        text("""
            SELECT id, type, message, link, is_sent, created_at
            FROM notifications WHERE recipient_id=:s
            ORDER BY created_at DESC LIMIT 5
        """),
        {"s": staff_id},
    ).fetchall())
    unread = db.execute(
        text("SELECT COUNT(*) FROM notifications WHERE recipient_id=:s AND is_sent=FALSE"),
        {"s": staff_id},
    ).scalar()
    return JSONResponse({"notifications": rows, "unread_count": unread
    })


@router.post("/{notif_id}/read")
async def mark_read(request: Request, notif_id: int, db: Session = Depends(get_db)):
    staff_id = _staff_id(request)
    db.execute(
        text("UPDATE notifications SET is_sent=TRUE WHERE id=:i AND recipient_id=:s"),
        {"i": notif_id, "s": staff_id},
    )
    db.commit()
    return JSONResponse({"status": "ok"})


@router.post("/read-all")
async def mark_all_read(request: Request, db: Session = Depends(get_db)):
    staff_id = _staff_id(request)
    db.execute(
        text("UPDATE notifications SET is_sent=TRUE WHERE recipient_id=:s AND is_sent=FALSE"),
        {"s": staff_id},
    )
    db.commit()
    return JSONResponse({"status": "ok"})
