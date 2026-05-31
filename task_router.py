import os
import sqlite3
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

router = APIRouter(prefix="/tasks", tags=["tasks"])

DB_PATH = os.path.join(os.path.dirname(__file__), 'sales_app.db')
templates = Jinja2Templates(directory="templates")

# ─── DB ──────────────────────────────────────────────
def db():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn

def now():
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')

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
def list_tasks(status: Optional[str] = None, assignee_id: Optional[int] = None, priority: Optional[str] = None):
    conn = db()
    query = """
        SELECT t.*, 
               a.name as assignee_name,
               c.name as creator_name
        FROM tasks t
        LEFT JOIN staffs a ON t.assignee_id = a.id
        LEFT JOIN staffs c ON t.created_by = c.id
        WHERE 1=1
    """
    params = []
    if status:
        query += " AND t.status=?"
        params.append(status)
    if assignee_id:
        query += " AND t.assignee_id=?"
        params.append(assignee_id)
    if priority:
        query += " AND t.priority=?"
        params.append(priority)
    query += " ORDER BY CASE t.priority WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END, t.due_date ASC NULLS LAST, t.created_at DESC"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]

@router.post("/api")
def create_task(body: TaskCreate, request: Request):
    current = request.state.staff
    conn = db()
    cur = conn.execute("""
        INSERT INTO tasks (title, description, priority, assignee_id, due_date, created_by)
        VALUES (?,?,?,?,?,?)
    """, (body.title, body.description, body.priority,
          body.assignee_id, body.due_date, current['id']))
    conn.commit()
    task_id = cur.lastrowid
    conn.close()
    return {"id": task_id}

@router.patch("/api/{task_id}")
def update_task(task_id: int, body: TaskUpdate):
    conn = db()
    task = conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
    if not task:
        conn.close()
        raise HTTPException(404, "タスクが見つかりません")

    fields = {k: v for k, v in body.model_dump().items() if v is not None}
    if not fields:
        conn.close()
        return {"result": "no change"}

    fields['updated_at'] = now()
    set_clause = ", ".join(f"{k}=?" for k in fields)
    conn.execute(f"UPDATE tasks SET {set_clause} WHERE id=?", (*fields.values(), task_id))
    conn.commit()
    conn.close()
    return {"result": "ok"}

@router.delete("/api/{task_id}")
def delete_task(task_id: int):
    conn = db()
    conn.execute("DELETE FROM task_comments WHERE task_id=?", (task_id,))
    conn.execute("DELETE FROM tasks WHERE id=?", (task_id,))
    conn.commit()
    conn.close()
    return {"result": "ok"}

@router.get("/api/{task_id}/comments")
def get_comments(task_id: int):
    conn = db()
    rows = conn.execute("""
        SELECT tc.*, s.name as author_name
        FROM task_comments tc JOIN staffs s ON tc.author_id = s.id
        WHERE tc.task_id=? ORDER BY tc.created_at ASC
    """, (task_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

@router.post("/api/{task_id}/comments")
def add_comment(task_id: int, body: CommentCreate):
    conn = db()
    cur = conn.execute("""
        INSERT INTO task_comments (task_id, author_id, body) VALUES (?,?,?)
    """, (task_id, body.author_id, body.body))
    conn.execute("UPDATE tasks SET updated_at=? WHERE id=?", (now(), task_id))
    conn.commit()
    comment_id = cur.lastrowid
    conn.close()
    return {"id": comment_id}

# ─── UI ──────────────────────────────────────────────
@router.get("/", response_class=HTMLResponse)
def task_list_page(request: Request):
    conn = db()
    staffs = [dict(r) for r in conn.execute("SELECT id,name,role FROM staffs WHERE is_active=1").fetchall()]
    # サマリー
    counts = {}
    for s in ['todo','in_progress','done','cancelled']:
        counts[s] = conn.execute("SELECT COUNT(*) FROM tasks WHERE status=?", (s,)).fetchone()[0]
    conn.close()
    return templates.TemplateResponse("tasks/list.html", {
        "request": request,
        "staffs": staffs,
        "counts": counts,
        "current": request.state.staff,
    })

@router.get("/{task_id}", response_class=HTMLResponse)
def task_detail_page(task_id: int, request: Request):
    conn = db()
    task = conn.execute("""
        SELECT t.*, a.name as assignee_name, c.name as creator_name
        FROM tasks t
        LEFT JOIN staffs a ON t.assignee_id = a.id
        LEFT JOIN staffs c ON t.created_by = c.id
        WHERE t.id=?
    """, (task_id,)).fetchone()
    if not task:
        conn.close()
        raise HTTPException(404, "Not found")
    comments = conn.execute("""
        SELECT tc.*, s.name as author_name
        FROM task_comments tc JOIN staffs s ON tc.author_id=s.id
        WHERE tc.task_id=? ORDER BY tc.created_at ASC
    """, (task_id,)).fetchall()
    staffs = [dict(r) for r in conn.execute("SELECT id,name,role FROM staffs WHERE is_active=1").fetchall()]
    conn.close()
    return templates.TemplateResponse("tasks/detail.html", {
        "request": request,
        "task": dict(task),
        "comments": [dict(r) for r in comments],
        "staffs": staffs,
        "current": request.state.staff,
        "now": datetime.now().strftime('%Y-%m-%d'),
    })
