from utils import now_jst
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, HTTPException, Request, Depends
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import text
from database import get_db

router = APIRouter(prefix="/tasks", tags=["tasks"])
from templates_config import templates as templates

def _require_manager(request: Request):
    """manager / admin のみ許可。それ以外は 403。"""
    staff = getattr(request.state, "staff", None)
    if not staff:
        raise HTTPException(status_code=401)
    if staff.get("role") not in ("admin", "manager"):
        raise HTTPException(status_code=403, detail="この操作には管理者権限が必要です")
    return staff


def _row(row):
    return dict(row._mapping)

def _rows(rows):
    return [_row(r) for r in rows]

def now():
    return now_jst().strftime('%Y-%m-%d %H:%M:%S')


# ─── Pydantic ─────────────────────────────────────────
class TaskCreate(BaseModel):
    title: str
    description: Optional[str] = None
    priority: str = 'medium'
    assignee_id: Optional[int] = None
    due_date: Optional[str] = None

class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[str] = None
    assignee_id: Optional[int] = None
    due_date: Optional[str] = None

class CommentCreate(BaseModel):
    author_id: int
    body: str


# ─── API ─────────────────────────────────────────────
@router.get("/api")
def list_tasks(
    status: Optional[str] = None,
    assignee_id: Optional[int] = None,
    priority: Optional[str] = None,
    db: Session = Depends(get_db)
):
    query = """
        SELECT t.*,
               a.name as assignee_name,
               c.name as creator_name
        FROM tasks t
        LEFT JOIN staffs a ON t.assignee_id = a.id
        LEFT JOIN staffs c ON t.created_by = c.id
        WHERE 1=1
    """
    params: dict = {}
    if status:
        query += " AND t.status=:status"
        params["status"] = status
    if assignee_id:
        query += " AND t.assignee_id=:aid"
        params["aid"] = assignee_id
    if priority:
        query += " AND t.priority=:priority"
        params["priority"] = priority
    query += """
        ORDER BY CASE t.priority WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END,
                 t.due_date ASC NULLS LAST,
                 t.created_at DESC
    """
    return _rows(db.execute(text(query), params).fetchall())


@router.post("/api")
def create_task(body: TaskCreate, request: Request, db: Session = Depends(get_db)):
    current = request.state.staff
    result = db.execute(
        text("""
            INSERT INTO tasks (title, description, priority, assignee_id, due_date, created_by)
            VALUES (:title,:desc,:priority,:aid,:due,:creator)
            RETURNING id
        """),
        {"title": body.title, "desc": body.description, "priority": body.priority,
         "aid": body.assignee_id, "due": body.due_date, "creator": current['id']}
    )
    new_id = result.scalar()
    db.commit()
    return {"id": new_id}


@router.patch("/api/{task_id}")
def update_task(task_id: int, body: TaskUpdate, db: Session = Depends(get_db)):
    # [C4] 動的SQLを廃止し ORM で更新
    from models import Task
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(404, "タスクが見つかりません")

    fields = {k: v for k, v in body.model_dump().items() if v is not None}
    if not fields:
        return {"result": "no change"}

    # ホワイトリストで許可カラムのみ更新
    ALLOWED_FIELDS = {"title", "description", "status", "priority", "assignee_id", "due_date"}
    for k, v in fields.items():
        if k in ALLOWED_FIELDS:
            setattr(task, k, v)
    from datetime import datetime as _dt
    task.updated_at = _dt.now()
    db.commit()
    return {"result": "ok"}


@router.delete("/api/{task_id}")
def delete_task(task_id: int, request: Request, db: Session = Depends(get_db)):
    _require_manager(request)
    db.execute(text("DELETE FROM task_comments WHERE task_id=:i"), {"i": task_id})
    db.execute(text("DELETE FROM tasks WHERE id=:i"), {"i": task_id})
    db.commit()
    return {"result": "ok"}


@router.get("/api/{task_id}/comments")
def get_comments(task_id: int, db: Session = Depends(get_db)):
    rows = db.execute(
        text("""
            SELECT tc.*, s.name as author_name
            FROM task_comments tc JOIN staffs s ON tc.author_id = s.id
            WHERE tc.task_id=:i ORDER BY tc.created_at ASC
        """),
        {"i": task_id}
    ).fetchall()
    return _rows(rows)


@router.post("/api/{task_id}/comments")
def add_comment(task_id: int, body: CommentCreate, db: Session = Depends(get_db)):
    result = db.execute(
        text("INSERT INTO task_comments (task_id, author_id, body) VALUES (:t,:a,:b) RETURNING id"),
        {"t": task_id, "a": body.author_id, "b": body.body}
    )
    new_id = result.scalar()
    db.execute(text("UPDATE tasks SET updated_at=:t WHERE id=:i"), {"t": now(), "i": task_id})
    db.commit()
    return {"id": new_id}


# ─── UI ──────────────────────────────────────────────
@router.get("/", response_class=HTMLResponse)
def task_list_page(request: Request, db: Session = Depends(get_db)):
    staffs = _rows(db.execute(text("SELECT id,name,role FROM staffs WHERE is_active=TRUE")).fetchall())
    counts = {}
    for s in ['todo', 'in_progress', 'done', 'cancelled']:
        counts[s] = db.execute(
            text("SELECT COUNT(*) FROM tasks WHERE status=:s"), {"s": s}
        ).scalar()
    return templates.TemplateResponse(request, "tasks/list.html", {
        "staffs": staffs,
        "counts": counts,
        "current": request.state.staff
    })


@router.get("/{task_id}", response_class=HTMLResponse)
def task_detail_page(task_id: int, request: Request, db: Session = Depends(get_db)):
    task_row = db.execute(
        text("""
            SELECT t.*, a.name as assignee_name, c.name as creator_name
            FROM tasks t
            LEFT JOIN staffs a ON t.assignee_id = a.id
            LEFT JOIN staffs c ON t.created_by = c.id
            WHERE t.id=:i
        """),
        {"i": task_id}
    ).fetchone()
    if not task_row:
        raise HTTPException(404, "Not found")

    comments = _rows(db.execute(
        text("""
            SELECT tc.*, s.name as author_name
            FROM task_comments tc JOIN staffs s ON tc.author_id=s.id
            WHERE tc.task_id=:i ORDER BY tc.created_at ASC
        """),
        {"i": task_id}
    ).fetchall())
    staffs = _rows(db.execute(text("SELECT id,name,role FROM staffs WHERE is_active=TRUE")).fetchall())

    return templates.TemplateResponse(request, "tasks/detail.html", {
        "task": dict(task_row._mapping),
        "comments": comments,
        "staffs": staffs,
        "current": request.state.staff
    })
