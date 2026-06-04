from fastapi import FastAPI, Request, Depends, Body
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from sqlalchemy.orm import Session
import sys, os, pathlib
sys.path.insert(0, os.path.dirname(__file__))

import models
from models import Base
from database import engine, get_db, SessionLocal
from routers import customers, products, inventory, quotes, shipments
from routers import staff as staff_router
import crud
import company_config
from auth import decode_session_token
from barcode_routes import router as barcode_router
from routers.sales import router as sales_router
from routers.demo import router as demo_router
from approval_router import router as approval_router
from task_router import router as task_router
from material_router import router as material_router
from customer_memo_router import router as memo_router
from notification_router import router as notif_router
from repair_router import router as repair_router
from update_checker import router as update_router
from sqlalchemy import text as _sa_text

models.Base.metadata.create_all(bind=engine)

# カラム追加マイグレーション（既存DB対応）
def _run_migrations():
    from sqlalchemy import text
    is_pg = "postgresql" in str(engine.url)
    id_col = "id SERIAL PRIMARY KEY" if is_pg else "id INTEGER PRIMARY KEY AUTOINCREMENT"
    with engine.connect() as conn:
        for stmt in [
            "ALTER TABLE products ADD COLUMN alert_enabled BOOLEAN NOT NULL DEFAULT TRUE",
            "ALTER TABLE staffs ADD COLUMN position VARCHAR(100)",
            "ALTER TABLE staffs ADD COLUMN approval_level INTEGER DEFAULT 0",
        ]:
            try:
                conn.execute(text(stmt))
                conn.commit()
            except Exception:
                pass  # カラムが既に存在する場合はスキップ

_run_migrations()

# デフォルトカテゴリの初期投入（空の場合のみ）
def _seed_material_categories():
    from models import MaterialCategory
    db = SessionLocal()
    try:
        if db.query(MaterialCategory).count() == 0:
            defaults = ["製品カタログ", "添付文書・IFU", "学術資料", "社内資料", "その他"]
            for i, name in enumerate(defaults):
                db.add(MaterialCategory(name=name, sort_order=i))
            db.commit()
    except Exception as e:
        db.rollback()
        print(f"[seed categories] {e}")
    finally:
        db.close()

_seed_material_categories()

# 管理者アカウントが存在しない場合のみ自動作成
def _create_default_admin():
    from models import Staff
    from auth import hash_password
    db = SessionLocal()
    try:
        if not db.query(Staff).filter(Staff.login_id == "284").first():
            db.add(Staff(
                name="管理者",
                login_id="284",
                password_hash=hash_password("284"),
                role="admin",
                department="管理部",
            ))
            db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()

_create_default_admin()

app = FastAPI(title="営業・在庫管理システム")

# ── 静的ファイル（ルーター登録より前にまとめてマウント）──
app.mount("/static", StaticFiles(directory="static"), name="static")

uploads_dir = pathlib.Path(__file__).parent / "uploads"
uploads_dir.mkdir(exist_ok=True)
app.mount("/uploads", StaticFiles(directory=str(uploads_dir)), name="uploads")

from starlette.middleware.sessions import SessionMiddleware
app.add_middleware(SessionMiddleware, secret_key="your-secret-key")
templates = Jinja2Templates(directory="templates")

company_info = {
    "name": company_config.COMPANY_NAME,
    "postal": company_config.COMPANY_POSTAL,
    "address": company_config.COMPANY_ADDRESS,
    "tel": company_config.COMPANY_TEL,
    "fax": company_config.COMPANY_FAX,
    "invoice_no": company_config.COMPANY_INVOICE_NO,
}

OPEN_PATHS = ["/login", "/static"]


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    path = request.url.path
    if any(path.startswith(p) for p in OPEN_PATHS):
        return await call_next(request)

    from datetime import datetime, timedelta
    from models import Staff

    token = request.cookies.get("session")
    staff_dict = None

    if token:
        staff_id = decode_session_token(token)
        if staff_id:
            db = SessionLocal()
            try:
                staff = db.query(Staff).filter(
                    Staff.id == staff_id,
                    Staff.is_active == True
                ).first()
                if staff:
                    staff_dict = {
                        "id": int(staff.id),
                        "name": str(staff.name),
                        "login_id": str(staff.login_id),
                        "role": str(staff.role),
                        "department": str(staff.department) if staff.department else None,
                        "email": str(staff.email) if staff.email else None,
                        "is_active": bool(staff.is_active),
                        "last_active_at": staff.last_active_at,
                    }
                    staff.last_active_at = datetime.utcnow() + timedelta(hours=9)
                    staff.last_active_page = path
                    db.commit()
            finally:
                db.close()

    if not staff_dict:
        return RedirectResponse("/login")

    request.state.staff = staff_dict
    return await call_next(request)


# ── ルーター登録 ──
app.include_router(staff_router.router)
app.include_router(customers.router)
app.include_router(products.router)
app.include_router(inventory.router)
app.include_router(quotes.router)
app.include_router(shipments.router)
app.include_router(sales_router)
app.include_router(barcode_router)
app.include_router(demo_router)
app.include_router(approval_router)
app.include_router(task_router)
app.include_router(material_router)
app.include_router(memo_router)
app.include_router(notif_router)
app.include_router(repair_router)
app.include_router(update_router)


@app.post("/api/announcements")
async def create_announcement(
    request: Request,
    body: dict = Body(...),
    db: Session = Depends(get_db)
):
    from fastapi import HTTPException
    current = request.state.staff
    result = db.execute(
        _sa_text("""
            INSERT INTO announcements (title, body, author_id, is_pinned)
            VALUES (:title,:body,:author,:pinned)
            RETURNING id
        """),
        {"title": body['title'], "body": body['body'],
         "author": current['id'], "pinned": body.get('is_pinned', 0)}
    )
    aid = result.scalar()
    db.commit()
    return {"id": aid}


@app.delete("/api/announcements/{announcement_id}")
async def delete_announcement(
    announcement_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    from fastapi import HTTPException
    current = request.state.staff
    row = db.execute(
        _sa_text("SELECT author_id FROM announcements WHERE id=:i"),
        {"i": announcement_id}
    ).fetchone()
    if not row:
        raise HTTPException(404, "Not found")
    if row[0] != current['id'] and current['role'] != 'admin':
        raise HTTPException(403, "権限がありません")
    db.execute(_sa_text("DELETE FROM announcements WHERE id=:i"), {"i": announcement_id})
    db.commit()
    return {"result": "ok"}


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db)):
    from datetime import datetime, timedelta
    from models import Staff

    alerts = crud.get_alerts(db)
    recent_quotes = crud.get_quotes(db)[:5]
    from models import DemoLoan
    import datetime as _dt
    today = _dt.date.today()
    overdue_loans = (
        db.query(DemoLoan)
        .filter(DemoLoan.due_date < today, DemoLoan.status == "on_loan")
        .all()
    )
    overdue_loans_count = len(overdue_loans)
    threshold = datetime.utcnow() + timedelta(hours=9) - timedelta(minutes=5)
    all_staffs = db.query(Staff).filter(Staff.is_active == True).all()
    online_staffs = [s for s in all_staffs if s.last_active_at and s.last_active_at >= threshold]
    now = datetime.utcnow() + timedelta(hours=9)

    all_staffs_data = [{
        "id": s.id, "name": s.name, "department": s.department,
        "last_active_at": s.last_active_at,
    } for s in all_staffs]
    online_staffs_data = [{
        "id": s.id, "name": s.name, "department": s.department,
        "last_active_at": s.last_active_at,
    } for s in online_staffs]

    current = request.state.staff

    my_tasks = [dict(r._mapping) for r in db.execute(_sa_text("""
        SELECT t.*, a.name as assignee_name
        FROM tasks t LEFT JOIN staffs a ON t.assignee_id=a.id
        WHERE t.assignee_id=:uid AND t.status IN ('todo','in_progress')
        ORDER BY CASE t.status WHEN 'in_progress' THEN 1 ELSE 2 END,
                 CASE t.priority WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END,
                 t.due_date ASC NULLS LAST
        LIMIT 5
    """), {"uid": current['id']}).fetchall()]

    my_task_count = db.execute(
        _sa_text("SELECT COUNT(*) FROM tasks WHERE assignee_id=:uid AND status NOT IN ('done','cancelled')"),
        {"uid": current['id']}
    ).scalar()

    my_approvals = [dict(r._mapping) for r in db.execute(_sa_text("""
        SELECT d.id, d.title, d.current_step, dt.name as type_name
        FROM documents d
        JOIN document_types dt ON d.document_type_id=dt.id
        JOIN approval_flows af ON af.document_type_id=d.document_type_id AND af.is_active=1
        JOIN approval_steps ast ON ast.flow_id=af.id AND ast.step_order=d.current_step
        WHERE d.status='in_review'
        AND (ast.approver_id=:uid OR ast.approver_role=(SELECT role FROM staffs WHERE id=:uid2))
        ORDER BY d.updated_at DESC
        LIMIT 5
    """), {"uid": current['id'], "uid2": current['id']}).fetchall()]

    my_approval_count = len(my_approvals)

    announcements = [dict(r._mapping) for r in db.execute(_sa_text("""
        SELECT a.*, s.name as author_name
        FROM announcements a JOIN staffs s ON a.author_id=s.id
        ORDER BY a.is_pinned DESC, a.created_at DESC
        LIMIT 10
    """)).fetchall()]

    from models import Favorite, Material, MaterialCategory as MatCat
    from sqlalchemy.orm import aliased
    _fav_rows = (
        db.query(Material, MatCat.name)
        .join(Favorite, Favorite.material_id == Material.id)
        .outerjoin(MatCat, MatCat.id == Material.category_id)
        .filter(Favorite.staff_id == current['id'], Material.is_active == True)
        .order_by(Favorite.created_at.desc())
        .limit(5)
        .all()
    )
    fav_materials = [
        {
            "id": m.id,
            "title": m.title,
            "file_type": m.file_type,
            "updated_at": str(m.updated_at),
            "category_name": cat_name,
        }
        for m, cat_name in _fav_rows
    ]

    recent_notifs = [dict(r._mapping) for r in db.execute(_sa_text(
        """SELECT id, message, link, created_at, is_sent
           FROM notifications
           WHERE recipient_id = :uid AND is_sent = 0
           ORDER BY created_at DESC LIMIT 5"""
    ), {"uid": current["id"]}).fetchall()]

    unread_notif_count = db.execute(
        _sa_text("SELECT COUNT(*) FROM notifications WHERE recipient_id=:uid AND is_sent=0"),
        {"uid": current["id"]}
    ).scalar()

    recent_memos = [dict(r._mapping) for r in db.execute(_sa_text(
        """SELECT cm.id, cm.hospital, cm.doctor_name, cm.memo, cm.updated_at
           FROM customer_memos cm
           WHERE cm.staff_id = :uid
           ORDER BY cm.updated_at DESC LIMIT 5"""
    ), {"uid": current["id"]}).fetchall()]

    overdue_repairs_count = db.execute(
        _sa_text("SELECT COUNT(*) FROM repairs WHERE step_deadline < :today AND status != 'closed'"),
        {"today": today.isoformat()}
    ).scalar()

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "current": current,
        "alerts": alerts,
        "recent_quotes": recent_quotes,
        "overdue_loans_count": overdue_loans_count,
        "online_staffs": online_staffs_data,
        "all_staffs": all_staffs_data,
        "now": now,
        "my_tasks": my_tasks,
        "my_task_count": my_task_count,
        "my_approvals": my_approvals,
        "my_approval_count": my_approval_count,
        "announcements": announcements,
        "fav_materials": fav_materials,
        "recent_notifs": recent_notifs,
        "unread_notif_count": unread_notif_count,
        "recent_memos": recent_memos,
        "overdue_repairs_count": overdue_repairs_count,
    })
