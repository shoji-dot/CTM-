from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Depends, Body
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from sqlalchemy.orm import Session
import sys, os, pathlib
sys.path.insert(0, os.path.dirname(__file__))

import models
from models import Base
from database import engine, get_db, SessionLocal
from routers import customers, products, inventory, quotes, shipments
from routers import staff as staff_router
from routers.returns import router as returns_router
import crud
import company_config
from auth import decode_session_token, now_jst, generate_csrf_token, verify_csrf_token
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

# 起動時マイグレーション（列追加・既存は無視）
def _run_migrations():
    is_pg = "postgresql" in str(engine.url)
    if is_pg:
        stmts = [
            # ── テーブル新規作成（存在しない場合のみ） ──
            """CREATE TABLE IF NOT EXISTS announcements (
                id SERIAL PRIMARY KEY,
                title TEXT NOT NULL,
                body TEXT NOT NULL,
                author_id INTEGER NOT NULL REFERENCES staffs(id),
                is_pinned BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )""",
            """CREATE TABLE IF NOT EXISTS document_types (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                description TEXT,
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT NOW()
            )""",
            """CREATE TABLE IF NOT EXISTS documents (
                id SERIAL PRIMARY KEY,
                title TEXT NOT NULL,
                document_type_id INTEGER NOT NULL REFERENCES document_types(id),
                file_path TEXT NOT NULL,
                file_name TEXT NOT NULL,
                file_size INTEGER,
                mime_type TEXT,
                status TEXT NOT NULL DEFAULT 'draft',
                uploaded_by INTEGER NOT NULL REFERENCES staffs(id),
                current_step INTEGER DEFAULT 0,
                comment TEXT,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )""",
            """CREATE TABLE IF NOT EXISTS approval_flows (
                id SERIAL PRIMARY KEY,
                document_type_id INTEGER NOT NULL REFERENCES document_types(id),
                name TEXT NOT NULL,
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT NOW()
            )""",
            """CREATE TABLE IF NOT EXISTS approval_steps (
                id SERIAL PRIMARY KEY,
                flow_id INTEGER NOT NULL REFERENCES approval_flows(id),
                step_order INTEGER NOT NULL,
                step_name TEXT NOT NULL,
                approver_id INTEGER REFERENCES staffs(id),
                approver_role TEXT,
                required_level INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT NOW()
            )""",
            """CREATE TABLE IF NOT EXISTS approval_logs (
                id SERIAL PRIMARY KEY,
                document_id INTEGER NOT NULL REFERENCES documents(id),
                step_order INTEGER NOT NULL,
                approver_id INTEGER NOT NULL REFERENCES staffs(id),
                action TEXT NOT NULL,
                comment TEXT,
                created_at TIMESTAMP DEFAULT NOW()
            )""",
            """CREATE TABLE IF NOT EXISTS notifications (
                id SERIAL PRIMARY KEY,
                document_id INTEGER,
                recipient_id INTEGER NOT NULL REFERENCES staffs(id),
                type TEXT NOT NULL,
                is_sent BOOLEAN DEFAULT FALSE,
                sent_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT NOW(),
                resource_type TEXT,
                resource_id INTEGER,
                message TEXT DEFAULT '',
                link TEXT DEFAULT ''
            )""",
            """CREATE TABLE IF NOT EXISTS customer_memos (
                id SERIAL PRIMARY KEY,
                hospital TEXT NOT NULL,
                doctor_name TEXT,
                memo TEXT,
                staff_id INTEGER REFERENCES staffs(id),
                created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMP NOT NULL DEFAULT NOW()
            )""",
            # ── 列追加（既存テーブルへ） ──
            "ALTER TABLE quotes ADD COLUMN IF NOT EXISTS approval_doc_id INTEGER",
            "ALTER TABLE quotes ADD COLUMN IF NOT EXISTS created_by_id INTEGER REFERENCES staffs(id)",
            "ALTER TABLE products ADD COLUMN IF NOT EXISTS alert_enabled BOOLEAN NOT NULL DEFAULT TRUE",
            "ALTER TABLE staffs ADD COLUMN IF NOT EXISTS position VARCHAR(100)",
            "ALTER TABLE staffs ADD COLUMN IF NOT EXISTS approval_level INTEGER DEFAULT 0",
            # [C5] 承認・取消カラム追加
            "ALTER TABLE quotes ADD COLUMN IF NOT EXISTS approved_by_id INTEGER REFERENCES staffs(id)",
            "ALTER TABLE quotes ADD COLUMN IF NOT EXISTS approved_at TIMESTAMP",
            "ALTER TABLE quotes ADD COLUMN IF NOT EXISTS approval_comment TEXT",
            "ALTER TABLE quotes ADD COLUMN IF NOT EXISTS cancelled_by_id INTEGER REFERENCES staffs(id)",
            "ALTER TABLE quotes ADD COLUMN IF NOT EXISTS cancel_comment TEXT",
            "ALTER TABLE quotes ADD COLUMN IF NOT EXISTS cancelled_at TIMESTAMP",
            # ── ShipmentItem マイグレーション ──
            """CREATE TABLE IF NOT EXISTS shipment_items (
                id            SERIAL PRIMARY KEY,
                shipment_id   INTEGER NOT NULL REFERENCES shipments(id) ON DELETE CASCADE,
                line_no       INTEGER NOT NULL DEFAULT 1,
                shipment_type VARCHAR(20) NOT NULL,
                product_id    INTEGER NOT NULL REFERENCES products(id),
                quantity      INTEGER NOT NULL DEFAULT 1,
                serial_number VARCHAR(100),
                lot_number    VARCHAR(100),
                expiry_date   DATE,
                demo_unit_id  INTEGER REFERENCES demo_units(id)
            )""",
            "CREATE INDEX IF NOT EXISTS ix_shipment_items_shipment_id ON shipment_items(shipment_id)",
            "CREATE INDEX IF NOT EXISTS ix_shipment_items_product_id  ON shipment_items(product_id)",
            "ALTER TABLE sales ADD COLUMN IF NOT EXISTS shipment_item_id INTEGER REFERENCES shipment_items(id)",
            # ── DemoUnit 所在地カラム ──
            "ALTER TABLE demo_units ADD COLUMN IF NOT EXISTS location_type VARCHAR(50) DEFAULT 'own'",
            "ALTER TABLE demo_units ADD COLUMN IF NOT EXISTS location_name VARCHAR(200) DEFAULT 'CTM本社'",
            "ALTER TABLE shipments ADD COLUMN IF NOT EXISTS shipment_type VARCHAR(20)",
            "ALTER TABLE shipments ADD COLUMN IF NOT EXISTS contact_name VARCHAR(100)",
            # ── RepairRecord staff_name カラム ──
            "ALTER TABLE repair_records ADD COLUMN IF NOT EXISTS staff_name VARCHAR(100)",
        ]
    else:
        stmts = [
            "ALTER TABLE quotes ADD COLUMN approval_doc_id INTEGER",
            "ALTER TABLE quotes ADD COLUMN created_by_id INTEGER",
            "ALTER TABLE products ADD COLUMN alert_enabled BOOLEAN NOT NULL DEFAULT TRUE",
            "ALTER TABLE staffs ADD COLUMN position VARCHAR(100)",
            "ALTER TABLE staffs ADD COLUMN approval_level INTEGER DEFAULT 0",
            # [C5] 承認・取消カラム追加
            "ALTER TABLE quotes ADD COLUMN approved_by_id INTEGER",
            "ALTER TABLE quotes ADD COLUMN approved_at DATETIME",
            "ALTER TABLE quotes ADD COLUMN approval_comment TEXT",
            "ALTER TABLE quotes ADD COLUMN cancelled_by_id INTEGER",
            "ALTER TABLE quotes ADD COLUMN cancel_comment TEXT",
            "ALTER TABLE quotes ADD COLUMN cancelled_at DATETIME",
        ]
    with engine.connect() as conn:
        for stmt in stmts:
            try:
                conn.execute(_sa_text(stmt))
                conn.commit()
            except Exception:
                pass

_run_migrations()

# Alembicマイグレーション（__file__基準でalembic.iniを解決）
def _run_alembic():
    try:
        from alembic import command
        from alembic.config import Config
        ini_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "alembic.ini")
        cfg = Config(ini_path)
        command.upgrade(cfg, "head")
        print("[alembic] upgrade head: OK")
    except Exception as e:
        print(f"[alembic] migration skipped: {e}")

_run_alembic()

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

# [C2] 管理者アカウントが存在しない場合のみ自動作成
# 初期パスワードは環境変数 ADMIN_INITIAL_PASSWORD から取得。
# 未設定の場合は起動を中断してパスワード設定を強制する。
def _create_default_admin():
    from models import Staff
    from auth import hash_password
    initial_password = os.environ.get("ADMIN_INITIAL_PASSWORD")
    if not initial_password:
        # 既に管理者が存在する場合は問題なし
        db = SessionLocal()
        try:
            exists = db.query(Staff).filter(Staff.role == "admin").first()
        finally:
            db.close()
        if not exists:
            raise RuntimeError(
                "環境変数 ADMIN_INITIAL_PASSWORD が未設定です。"
                ".env に推測困難なパスワードを設定してください。"
            )
        return
    db = SessionLocal()
    try:
        if not db.query(Staff).filter(Staff.login_id == "284").first():
            db.add(Staff(
                name="管理者",
                login_id="284",
                password_hash=hash_password(initial_password),
                role="admin",
                department="管理部",
            ))
            db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()

_create_default_admin()

def _send_expiry_alert_job():
    """使用期限アラートメールを管理者・マネージャーに送信"""
    from datetime import date
    db = SessionLocal()
    try:
        alerts = crud.get_expiry_alerts(db, days=30)
        if not alerts:
            return
        from models import Staff
        managers = db.query(Staff).filter(
            Staff.is_active == True,
            Staff.role.in_(["admin", "manager"]),
            Staff.email.isnot(None),
        ).all()
        to_list = [s.email for s in managers if s.email]
        if not to_list:
            return
        from notification_service import send_email
        today_str = date.today().strftime("%Y/%m/%d")
        rows_html = ""
        for a in alerts:
            color = "#fee2e2" if a["is_expired"] else "#fef9c3"
            label = f"<b style='color:#dc2626'>期限切れ</b>" if a["is_expired"] else f"残{a['days_left']}日"
            rows_html += f"""<tr style='background:{color}'>
              <td style='padding:8px 12px;border-bottom:1px solid #e5e7eb'>{a['product_name']}</td>
              <td style='padding:8px 12px;border-bottom:1px solid #e5e7eb'>{a['lot_number'] or '―'}</td>
              <td style='padding:8px 12px;border-bottom:1px solid #e5e7eb'>{a['expiry_date']}</td>
              <td style='padding:8px 12px;border-bottom:1px solid #e5e7eb'>{label}</td>
            </tr>"""
        html_body = f"""<html><body style='font-family:sans-serif;color:#1f2937'>
          <div style='max-width:640px;margin:32px auto;background:#fff;padding:32px;border:1px solid #e5e7eb;border-radius:8px'>
            <h2 style='color:#dc2626'>⚠ 使用期限アラート ({today_str})</h2>
            <p>以下の商品の使用期限が30日以内または期限切れです。</p>
            <table style='width:100%;border-collapse:collapse;font-size:0.9rem'>
              <thead><tr style='background:#f3f4f6'>
                <th style='padding:8px 12px;text-align:left'>商品名</th>
                <th style='padding:8px 12px;text-align:left'>ロット番号</th>
                <th style='padding:8px 12px;text-align:left'>使用期限</th>
                <th style='padding:8px 12px;text-align:left'>状態</th>
              </tr></thead>
              <tbody>{rows_html}</tbody>
            </table>
          </div>
        </body></html>"""
        send_email(to_list, f"【使用期限アラート】{len(alerts)}件 ({today_str})", "使用期限アラート", html_body=html_body)
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron import CronTrigger
    from zoneinfo import ZoneInfo
    scheduler = BackgroundScheduler(timezone=ZoneInfo("Asia/Tokyo"))
    scheduler.add_job(_send_expiry_alert_job, CronTrigger(hour=8, minute=0))
    scheduler.start()
    yield
    scheduler.shutdown()


app = FastAPI(title="営業・在庫管理システム", lifespan=lifespan)

# ── 静的ファイル（ルーター登録より前にまとめてマウント）──
app.mount("/static", StaticFiles(directory="static"), name="static")

uploads_dir = pathlib.Path(__file__).parent / "uploads"
uploads_dir.mkdir(exist_ok=True)
app.mount("/uploads", StaticFiles(directory=str(uploads_dir)), name="uploads")

from starlette.middleware.sessions import SessionMiddleware
# [C1] secret_key を環境変数から取得（.env の SESSION_SECRET_KEY を使用）
_session_secret = os.environ.get("SESSION_SECRET_KEY")
if not _session_secret:
    raise RuntimeError("環境変数 SESSION_SECRET_KEY が未設定です。.env を確認してください。")
app.add_middleware(SessionMiddleware, secret_key=_session_secret)
from templates_config import templates  # [I1] csrf_token登録済み

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
                    staff.last_active_at = now_jst()
                    staff.last_active_page = path
                    db.commit()
            finally:
                db.close()

    if not staff_dict:
        return RedirectResponse("/login")

    request.state.staff = staff_dict

    # [I1] POST/PUT/DELETE リクエストのCSRF strict 検証
    if request.method in ("POST", "PUT", "DELETE", "PATCH"):
        # ログイン・ログアウトはCSRF対象外
        if request.url.path not in ("/login", "/logout"):
            csrf_token_val = request.headers.get("X-CSRF-Token")
            content_type = request.headers.get("content-type", "")
            session_token = request.cookies.get("session", "")

            if not csrf_token_val:
                if "application/x-www-form-urlencoded" in content_type:
                    from urllib.parse import parse_qs
                    body = await request.body()
                    form_vals = parse_qs(body.decode("utf-8", errors="ignore"))
                    csrf_token_val = (form_vals.get("_csrf") or [""])[0]
                elif "multipart/form-data" in content_type:
                    form = await request.form()
                    csrf_token_val = form.get("_csrf", "") or ""
                else:
                    csrf_token_val = request.query_params.get("_csrf", "")

            if not csrf_token_val or not verify_csrf_token(session_token, csrf_token_val):
                from fastapi.responses import HTMLResponse as _HTML
                return _HTML("CSRF verification failed (403)", status_code=403)

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
app.include_router(returns_router)
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
    return _dashboard_inner(request, db)

def _dashboard_inner(request: Request, db: Session):
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
    threshold = now_jst() - timedelta(minutes=5)
    all_staffs = db.query(Staff).filter(Staff.is_active == True).all()
    online_staffs = [s for s in all_staffs if s.last_active_at and s.last_active_at >= threshold]
    now = now_jst()

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
        JOIN approval_flows af ON af.document_type_id=d.document_type_id AND af.is_active=TRUE
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
           WHERE recipient_id = :uid AND is_sent = FALSE
           ORDER BY created_at DESC LIMIT 5"""
    ), {"uid": current["id"]}).fetchall()]

    unread_notif_count = db.execute(
        _sa_text("SELECT COUNT(*) FROM notifications WHERE recipient_id=:uid AND is_sent=FALSE"),
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

    return templates.TemplateResponse(request, "dashboard.html", {
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
        "recent_notifs": recent_notifs
    })
