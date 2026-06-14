from fastapi import APIRouter, Depends, Request, Form, Cookie
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from database import get_db
from models import Staff, Quote, Customer, Task, Material, MaterialVersion, Favorite, TaskComment
from auth import hash_password, verify_password, verify_and_update_password, create_session_token, get_current_staff, now_jst
import crud

# [B2] ログイン試行制限（DB永続化）
_MAX_ATTEMPTS = 5
_LOCK_MINUTES = 15  # ロック時間を5分→15分に強化


def _is_locked(staff: Staff) -> bool:
    """True=ロック中。ロック期限切れなら False を返す（DBはログイン成功時にリセット）。"""
    if staff.locked_until and staff.locked_until > now_jst():
        return True
    return False


def _record_fail_db(staff: Staff, db: Session) -> int:
    """失敗カウントをインクリメント。上限到達時はロックタイムを設定。残り試行回数を返す。"""
    staff.failed_attempts = (staff.failed_attempts or 0) + 1
    remaining = max(0, _MAX_ATTEMPTS - staff.failed_attempts)
    if staff.failed_attempts >= _MAX_ATTEMPTS:
        staff.locked_until = now_jst() + timedelta(minutes=_LOCK_MINUTES)
    db.commit()
    return remaining


def _clear_fail_db(staff: Staff, db: Session):
    staff.failed_attempts = 0
    staff.locked_until = None
    db.commit()

router = APIRouter()
from templates_config import templates


def get_staff_or_redirect(request: Request, db: Session):
    token = request.cookies.get("session")
    staff = get_current_staff(token, db)
    return staff


@router.get("/login", response_class=HTMLResponse)
def login_form(request: Request):
    return templates.TemplateResponse(request, "auth/login.html", {"error": None})


@router.post("/login")
def login(request: Request, login_id: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    # [B2] ユーザーを先に取得してDB側でロック確認
    staff = db.query(Staff).filter(Staff.login_id == login_id, Staff.is_active == True).first()

    # アカウントが存在しない場合も同じメッセージを返す（ユーザー列挙防止）
    if not staff:
        return templates.TemplateResponse(request, "auth/login.html", {
            "error": "IDまたはパスワードが正しくありません"
        })

    # ロック中チェック
    if _is_locked(staff):
        remaining_sec = int((staff.locked_until - now_jst()).total_seconds())
        remaining_min = max(1, remaining_sec // 60)
        return templates.TemplateResponse(request, "auth/login.html", {
            "error": f"ログインがロックされています。約{remaining_min}分後に再試行してください。"
        })

    # パスワード検証（sha256_crypt → bcrypt 自動移行）
    valid, new_hash = verify_and_update_password(password, staff.password_hash)
    if not valid:
        remaining = _record_fail_db(staff, db)
        msg = "IDまたはパスワードが正しくありません"
        if remaining == 0:
            msg = f"ログインをロックしました。{_LOCK_MINUTES}分後に再試行してください。"
        elif remaining <= 2:
            msg += f"（あと{remaining}回失敗するとロックされます）"
        return templates.TemplateResponse(request, "auth/login.html", {"error": msg})

    # 認証成功 → 失敗カウントをリセット・ハッシュ移行があれば保存
    _clear_fail_db(staff, db)
    if new_hash:
        staff.password_hash = new_hash
        db.commit()
    token = create_session_token(staff.id)
    response = RedirectResponse("/", status_code=303)
    response.set_cookie("session", token, max_age=60*60*8, httponly=True, samesite="lax", secure=True)
    return response


@router.get("/logout")
def logout():
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie("session")
    return response


@router.get("/staff", response_class=HTMLResponse)
def list_staff(request: Request, db: Session = Depends(get_db)):
    current = get_staff_or_redirect(request, db)
    if not current:
        return RedirectResponse("/login", status_code=303)
    if current.role != "admin":
        return RedirectResponse("/", status_code=303)
    staffs = db.query(Staff).order_by(Staff.id).all()
    now = now_jst()
    return templates.TemplateResponse(request, "staff/list.html", {
        "staffs": staffs, "current": current, "now": now
    })


@router.get("/staff/new", response_class=HTMLResponse)
def new_staff_form(request: Request, db: Session = Depends(get_db)):
    current = get_staff_or_redirect(request, db)
    if not current or current.role != "admin":
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse(request, "staff/form.html", {"staff": None, "current": current})


@router.post("/staff/new")
def create_staff(
    request: Request,
    name: str = Form(...),
    login_id: str = Form(...),
    password: str = Form(...),
    role: str = Form("user"),
    department: str = Form(""),
    email: str = Form(""),
    db: Session = Depends(get_db)
):
    current = get_staff_or_redirect(request, db)
    if not current or current.role != "admin":
        return RedirectResponse("/", status_code=303)
    staff = Staff(
        name=name,
        login_id=login_id,
        password_hash=hash_password(password),
        role=role,
        department=department or None,
        email=email or None,
    )
    db.add(staff)
    db.commit()
    return RedirectResponse("/staff", status_code=303)


@router.get("/staff/{staff_id}/edit", response_class=HTMLResponse)
def edit_staff_form(staff_id: int, request: Request, db: Session = Depends(get_db)):
    current = get_staff_or_redirect(request, db)
    if not current or current.role != "admin":
        return RedirectResponse("/", status_code=303)
    staff = db.query(Staff).filter(Staff.id == staff_id).first()
    return templates.TemplateResponse(request, "staff/form.html", {"staff": staff, "current": current})


@router.post("/staff/{staff_id}/edit")
def update_staff(
    staff_id: int,
    request: Request,
    name: str = Form(...),
    login_id: str = Form(...),
    password: str = Form(""),
    role: str = Form("user"),
    department: str = Form(""),
    email: str = Form(""),
    is_active: str = Form("on"),
    db: Session = Depends(get_db)
):
    current = get_staff_or_redirect(request, db)
    if not current or current.role != "admin":
        return RedirectResponse("/", status_code=303)
    staff = db.query(Staff).filter(Staff.id == staff_id).first()
    if staff:
        staff.name = name
        staff.login_id = login_id
        staff.role = role
        staff.department = department or None
        staff.email = email or None
        staff.is_active = (is_active == "on")
        if password:
            staff.password_hash = hash_password(password)
        db.commit()
    return RedirectResponse("/staff", status_code=303)


@router.post("/staff/{staff_id}/delete")
def delete_staff(staff_id: int, request: Request, db: Session = Depends(get_db)):
    from urllib.parse import quote as urlquote
    current = get_staff_or_redirect(request, db)
    if not current or current.role != "admin":
        return RedirectResponse("/", status_code=303)
    staff = db.query(Staff).filter(Staff.id == staff_id).first()
    if not staff:
        return RedirectResponse("/staff", status_code=303)
    if staff.id == current.id:
        return RedirectResponse("/staff?error=" + urlquote("自分自身は削除できません"), status_code=303)
    # 整合性チェック: 関連データが存在する場合は削除不可
    from sqlalchemy import text as sqla_text
    checks = [
        ("見積もり(作成)",    db.query(Quote).filter(Quote.created_by_id == staff_id).count()),
        ("見積もり(承認)",    db.query(Quote).filter(Quote.approved_by_id == staff_id).count()),
        ("担当顧客",          db.query(Customer).filter(Customer.staff_id == staff_id).count()),
        ("タスク(担当)",      db.query(Task).filter(Task.assignee_id == staff_id).count()),
        ("タスク(作成)",      db.query(Task).filter(Task.created_by == staff_id).count()),
        ("タスクコメント",    db.query(TaskComment).filter(TaskComment.staff_id == staff_id).count()),
        ("資材(アップロード)",db.query(Material).filter(Material.uploaded_by == staff_id).count()),
        ("資材バージョン",    db.query(MaterialVersion).filter(MaterialVersion.uploaded_by == staff_id).count()),
        ("お気に入り",        db.query(Favorite).filter(Favorite.staff_id == staff_id).count()),
    ]
    # raw SQL テーブル（ORM モデル外）
    for tbl, col in [("documents", "uploaded_by"), ("approval_logs", "approver_id"), ("notifications", "recipient_id")]:
        try:
            row = db.execute(sqla_text(f"SELECT COUNT(*) FROM {tbl} WHERE {col}=:sid"), {"sid": staff_id}).scalar()
            checks.append((tbl, row or 0))
        except Exception:
            pass  # テーブルが存在しない環境ではスキップ

    errors = [f"{label} {cnt}件" for label, cnt in checks if cnt]
    if errors:
        msg = urlquote("削除できません。関連データあり: " + ", ".join(errors))
        return RedirectResponse(f"/staff?error={msg}", status_code=303)
    try:
        db.delete(staff)
        db.commit()
    except Exception as e:
        db.rollback()
        msg = urlquote(f"削除エラー: {e}")
        return RedirectResponse(f"/staff?error={msg}", status_code=303)
    return RedirectResponse("/staff", status_code=303)
