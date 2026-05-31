from fastapi import APIRouter, Depends, Request, Form, Cookie
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from database import get_db
from models import Staff
from auth import hash_password, verify_password, create_session_token, get_current_staff
import crud

router = APIRouter()
templates = Jinja2Templates(directory="templates")


def get_staff_or_redirect(request: Request, db: Session):
    token = request.cookies.get("session")
    staff = get_current_staff(token, db)
    return staff


@router.get("/login", response_class=HTMLResponse)
def login_form(request: Request):
    return templates.TemplateResponse("auth/login.html", {"request": request, "error": None})


@router.post("/login")
def login(request: Request, login_id: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    staff = db.query(Staff).filter(Staff.login_id == login_id, Staff.is_active == True).first()
    if not staff or not verify_password(password, staff.password_hash):
        return templates.TemplateResponse("auth/login.html", {"request": request, "error": "IDまたはパスワードが正しくありません"})
    token = create_session_token(staff.id)
    response = RedirectResponse("/", status_code=303)
    response.set_cookie("session", token, max_age=60*60*8, httponly=True)
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
    now = datetime.now()
    return templates.TemplateResponse("staff/list.html", {
        "request": request, "staffs": staffs, "current": current, "now": now
    })


@router.get("/staff/new", response_class=HTMLResponse)
def new_staff_form(request: Request, db: Session = Depends(get_db)):
    current = get_staff_or_redirect(request, db)
    if not current or current.role != "admin":
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse("staff/form.html", {"request": request, "staff": None, "current": current})


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
    return templates.TemplateResponse("staff/form.html", {"request": request, "staff": staff, "current": current})


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
    current = get_staff_or_redirect(request, db)
    if not current or current.role != "admin":
        return RedirectResponse("/", status_code=303)
    staff = db.query(Staff).filter(Staff.id == staff_id).first()
    if staff and staff.id != current.id:
        db.delete(staff)
        db.commit()
    return RedirectResponse("/staff", status_code=303)
