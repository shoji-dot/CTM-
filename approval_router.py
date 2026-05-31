import os
import shutil
from datetime import datetime
from typing import Optional, List
from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Depends
from fastapi.responses import FileResponse
from pydantic import BaseModel
import sqlite3

router = APIRouter(prefix="/approval", tags=["approval"])

DB_PATH = os.path.join(os.path.dirname(__file__), 'sales_app.db')
UPLOAD_DIR = os.path.join(os.path.dirname(__file__), 'uploads', 'documents')
os.makedirs(UPLOAD_DIR, exist_ok=True)

# ─── DB接続 ───────────────────────────────────────────
def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    try:
        yield conn
    finally:
        conn.close()

def db():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn

# ─── Pydantic モデル ──────────────────────────────────
class ApprovalAction(BaseModel):
    approver_id: int
    action: str          # approved / rejected / commented
    comment: Optional[str] = None

class FlowCreate(BaseModel):
    document_type_id: int
    name: str

class StepCreate(BaseModel):
    flow_id: int
    step_order: int
    step_name: str
    approver_id: Optional[int] = None
    approver_role: Optional[str] = None
    required_level: int = 0

class DocumentTypeCreate(BaseModel):
    name: str
    description: Optional[str] = None

# ─── ヘルパー ─────────────────────────────────────────
def now():
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')

def get_active_flow(conn, document_type_id: int):
    return conn.execute(
        "SELECT * FROM approval_flows WHERE document_type_id=? AND is_active=1 LIMIT 1",
        (document_type_id,)
    ).fetchone()

def get_steps(conn, flow_id: int):
    return conn.execute(
        "SELECT * FROM approval_steps WHERE flow_id=? ORDER BY step_order",
        (flow_id,)
    ).fetchall()

def create_notification(conn, document_id: int, recipient_id: int, ntype: str):
    conn.execute(
        "INSERT INTO notifications (document_id, recipient_id, type) VALUES (?,?,?)",
        (document_id, recipient_id, ntype)
    )

# ─── ドキュメント種別 ─────────────────────────────────
@router.get("/document-types")
def list_document_types():
    conn = db()
    rows = conn.execute("SELECT * FROM document_types WHERE is_active=1").fetchall()
    conn.close()
    return [dict(r) for r in rows]

@router.post("/document-types")
def create_document_type(body: DocumentTypeCreate):
    conn = db()
    try:
        cur = conn.execute(
            "INSERT INTO document_types (name, description) VALUES (?,?)",
            (body.name, body.description)
        )
        conn.commit()
        return {"id": cur.lastrowid, "name": body.name}
    except sqlite3.IntegrityError:
        raise HTTPException(400, "同名のドキュメント種別が存在します")
    finally:
        conn.close()

@router.delete("/document-types/{type_id}")
def delete_document_type(type_id: int):
    conn = db()
    conn.execute("UPDATE document_types SET is_active=0 WHERE id=?", (type_id,))
    conn.commit()
    conn.close()
    return {"result": "ok"}

# ─── ドキュメントアップロード ─────────────────────────
@router.post("/documents/upload")
async def upload_document(
    title: str = Form(...),
    document_type_id: int = Form(...),
    uploaded_by: int = Form(...),
    file: UploadFile = File(...)
):
    # ファイル種別チェック
    allowed = ['application/pdf',
               'application/msword',
               'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
               'application/vnd.ms-excel',
               'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet']
    if file.content_type not in allowed:
        raise HTTPException(400, "PDF/Word/Excelのみアップロード可能です")

    # 保存
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    safe_name = f"{timestamp}_{file.filename}"
    file_path = os.path.join(UPLOAD_DIR, safe_name)
    with open(file_path, 'wb') as f:
        shutil.copyfileobj(file.file, f)
    file_size = os.path.getsize(file_path)

    conn = db()
    try:
        cur = conn.execute("""
            INSERT INTO documents
              (title, document_type_id, file_path, file_name, file_size, mime_type, uploaded_by, status)
            VALUES (?,?,?,?,?,?,?,'draft')
        """, (title, document_type_id, file_path, file.filename, file_size, file.content_type, uploaded_by))
        doc_id = cur.lastrowid
        conn.commit()
        return {"id": doc_id, "status": "draft", "message": "アップロード完了"}
    finally:
        conn.close()

@router.get("/documents")
def list_documents(status: Optional[str] = None, approver_id: Optional[int] = None):
    conn = db()
    query = """
        SELECT d.*, dt.name as type_name, s.name as uploader_name
        FROM documents d
        JOIN document_types dt ON d.document_type_id = dt.id
        JOIN staffs s ON d.uploaded_by = s.id
        WHERE 1=1
    """
    params = []
    if status:
        query += " AND d.status=?"
        params.append(status)
    if approver_id:
        # 自分が承認待ちのもの
        query += """
            AND d.id IN (
                SELECT doc.id FROM documents doc
                JOIN approval_flows af ON af.document_type_id = doc.document_type_id AND af.is_active=1
                JOIN approval_steps ast ON ast.flow_id = af.id AND ast.step_order = doc.current_step
                WHERE (ast.approver_id=? OR ast.approver_role=(SELECT role FROM staffs WHERE id=?))
                AND doc.status='in_review'
            )
        """
        params.extend([approver_id, approver_id])
    query += " ORDER BY d.updated_at DESC"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]

@router.get("/documents/{doc_id}")
def get_document(doc_id: int):
    conn = db()
    row = conn.execute("""
        SELECT d.*, dt.name as type_name, s.name as uploader_name
        FROM documents d
        JOIN document_types dt ON d.document_type_id = dt.id
        JOIN staffs s ON d.uploaded_by = s.id
        WHERE d.id=?
    """, (doc_id,)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(404, "ドキュメントが見つかりません")
    return dict(row)

@router.get("/documents/{doc_id}/file")
def download_document(doc_id: int):
    conn = db()
    row = conn.execute("SELECT file_path, file_name FROM documents WHERE id=?", (doc_id,)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(404, "ドキュメントが見つかりません")
    return FileResponse(row['file_path'], filename=row['file_name'])

# ─── 承認フロー申請 ───────────────────────────────────
@router.post("/documents/{doc_id}/submit")
def submit_document(doc_id: int, submitter_id: int):
    conn = db()
    try:
        doc = conn.execute("SELECT * FROM documents WHERE id=?", (doc_id,)).fetchone()
        if not doc:
            raise HTTPException(404, "ドキュメントが見つかりません")
        if doc['status'] not in ('draft', 'revising'):
            raise HTTPException(400, f"申請できない状態です: {doc['status']}")

        flow = get_active_flow(conn, doc['document_type_id'])
        if not flow:
            raise HTTPException(400, "承認フローが設定されていません")

        steps = get_steps(conn, flow['id'])
        if not steps:
            raise HTTPException(400, "承認ステップが設定されていません")

        # ステータス更新
        conn.execute("""
            UPDATE documents SET status='in_review', current_step=1, updated_at=? WHERE id=?
        """, (now(), doc_id))

        # ログ記録
        conn.execute("""
            INSERT INTO approval_logs (document_id, step_order, approver_id, action, comment)
            VALUES (?,0,?,'submitted','承認申請')
        """, (doc_id, submitter_id))

        # 最初の承認者に通知
        first_step = steps[0]
        if first_step['approver_id']:
            create_notification(conn, doc_id, first_step['approver_id'], 'approval_request')

        conn.commit()
        return {"result": "申請完了", "status": "in_review", "next_step": 1}
    finally:
        conn.close()

# ─── 承認・否認・コメント ─────────────────────────────
@router.post("/documents/{doc_id}/action")
def approval_action(doc_id: int, body: ApprovalAction):
    if body.action not in ('approved', 'rejected', 'commented'):
        raise HTTPException(400, "actionはapproved/rejected/commentedのいずれか")
    if body.action == 'rejected' and not body.comment:
        raise HTTPException(400, "否認時はコメント必須です")

    conn = db()
    try:
        doc = conn.execute("SELECT * FROM documents WHERE id=?", (doc_id,)).fetchone()
        if not doc:
            raise HTTPException(404, "ドキュメントが見つかりません")
        if doc['status'] != 'in_review':
            raise HTTPException(400, "承認中でないドキュメントです")

        flow = get_active_flow(conn, doc['document_type_id'])
        steps = get_steps(conn, flow['id'])
        current_step = doc['current_step']

        # 現在のステップ取得
        step = next((s for s in steps if s['step_order'] == current_step), None)
        if not step:
            raise HTTPException(400, "ステップ設定が見つかりません")

        # 承認権限チェック
        approver = conn.execute("SELECT * FROM staffs WHERE id=?", (body.approver_id,)).fetchone()
        if not approver:
            raise HTTPException(404, "承認者が見つかりません")

        is_authorized = (
            step['approver_id'] == body.approver_id or
            step['approver_role'] == approver['role'] or
            approver['approval_level'] >= step['required_level']
        )
        if not is_authorized:
            raise HTTPException(403, "このステップの承認権限がありません")

        # ログ記録
        conn.execute("""
            INSERT INTO approval_logs (document_id, step_order, approver_id, action, comment)
            VALUES (?,?,?,?,?)
        """, (doc_id, current_step, body.approver_id, body.action, body.comment))

        if body.action == 'approved':
            # 次のステップへ
            next_steps = [s for s in steps if s['step_order'] > current_step]
            if next_steps:
                next_step = next_steps[0]
                conn.execute("""
                    UPDATE documents SET current_step=?, updated_at=? WHERE id=?
                """, (next_step['step_order'], now(), doc_id))
                # 次の承認者に通知
                if next_step['approver_id']:
                    create_notification(conn, doc_id, next_step['approver_id'], 'approval_request')
                result = {"result": "承認完了", "status": "in_review", "next_step": next_step['step_order']}
            else:
                # 全ステップ完了
                conn.execute("""
                    UPDATE documents SET status='approved', updated_at=? WHERE id=?
                """, (now(), doc_id))
                # アップロード者に完了通知
                create_notification(conn, doc_id, doc['uploaded_by'], 'approved')
                result = {"result": "最終承認完了", "status": "approved"}

        elif body.action == 'rejected':
            # 差し戻し：前のステップへ
            prev_steps = [s for s in steps if s['step_order'] < current_step]
            if prev_steps:
                prev_step = prev_steps[-1]
                conn.execute("""
                    UPDATE documents SET status='in_review', current_step=?, comment=?, updated_at=? WHERE id=?
                """, (prev_step['step_order'], body.comment, now(), doc_id))
            else:
                # 最初のステップから差し戻し → 申請者へ
                conn.execute("""
                    UPDATE documents SET status='revising', current_step=0, comment=?, updated_at=? WHERE id=?
                """, (body.comment, now(), doc_id))
            # アップロード者に差し戻し通知
            create_notification(conn, doc_id, doc['uploaded_by'], 'rejected')
            result = {"result": "差し戻し", "status": "revising", "comment": body.comment}

        else:  # commented
            conn.execute("UPDATE documents SET updated_at=? WHERE id=?", (now(), doc_id))
            result = {"result": "コメント追加", "status": "in_review"}

        conn.commit()
        return result
    finally:
        conn.close()

# ─── 承認履歴 ─────────────────────────────────────────
@router.get("/documents/{doc_id}/logs")
def get_approval_logs(doc_id: int):
    conn = db()
    rows = conn.execute("""
        SELECT al.*, s.name as approver_name, s.role as approver_role
        FROM approval_logs al
        JOIN staffs s ON al.approver_id = s.id
        WHERE al.document_id=?
        ORDER BY al.created_at ASC
    """, (doc_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

# ─── 承認フロー管理 ───────────────────────────────────
@router.get("/flows")
def list_flows():
    conn = db()
    rows = conn.execute("""
        SELECT af.*, dt.name as type_name
        FROM approval_flows af
        JOIN document_types dt ON af.document_type_id = dt.id
        WHERE af.is_active=1
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]

@router.post("/flows")
def create_flow(body: FlowCreate):
    conn = db()
    cur = conn.execute(
        "INSERT INTO approval_flows (document_type_id, name) VALUES (?,?)",
        (body.document_type_id, body.name)
    )
    conn.commit()
    flow_id = cur.lastrowid
    conn.close()
    return {"id": flow_id}

@router.post("/flows/steps")
def add_step(body: StepCreate):
    conn = db()
    cur = conn.execute("""
        INSERT INTO approval_steps
          (flow_id, step_order, step_name, approver_id, approver_role, required_level)
        VALUES (?,?,?,?,?,?)
    """, (body.flow_id, body.step_order, body.step_name,
          body.approver_id, body.approver_role, body.required_level))
    conn.commit()
    step_id = cur.lastrowid
    conn.close()
    return {"id": step_id}

@router.get("/flows/{flow_id}/steps")
def get_flow_steps(flow_id: int):
    conn = db()
    rows = conn.execute("""
        SELECT ast.*, s.name as approver_name
        FROM approval_steps ast
        LEFT JOIN staffs s ON ast.approver_id = s.id
        WHERE ast.flow_id=?
        ORDER BY ast.step_order
    """, (flow_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

@router.delete("/flows/steps/{step_id}")
def delete_step(step_id: int):
    conn = db()
    conn.execute("DELETE FROM approval_steps WHERE id=?", (step_id,))
    conn.commit()
    conn.close()
    return {"result": "ok"}

@router.delete("/flows/{flow_id}")
def delete_flow(flow_id: int):
    conn = db()
    conn.execute("UPDATE approval_flows SET is_active=0 WHERE id=?", (flow_id,))
    conn.commit()
    conn.close()
    return {"result": "ok"}

# ─── 通知一覧 ─────────────────────────────────────────
@router.get("/notifications/{staff_id}")
def get_notifications(staff_id: int):
    conn = db()
    rows = conn.execute("""
        SELECT n.*, d.title as doc_title, d.status as doc_status
        FROM notifications n
        JOIN documents d ON n.document_id = d.id
        WHERE n.recipient_id=?
        ORDER BY n.created_at DESC
        LIMIT 50
    """, (staff_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

# approval_router.py の末尾に追記するコード

# ─── Jinja2 UI ルート ─────────────────────────────────
from fastapi import Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

templates_approval = Jinja2Templates(directory="templates")

@router.get("/", response_class=HTMLResponse)
def approval_list_page(request: Request, status: str = None, approver_id: int = None):
    conn = db()
    # ドキュメント一覧
    query = """
        SELECT d.*, dt.name as type_name, s.name as uploader_name
        FROM documents d
        JOIN document_types dt ON d.document_type_id = dt.id
        JOIN staffs s ON d.uploaded_by = s.id
        WHERE 1=1
    """
    params = []
    if status:
        query += " AND d.status=?"
        params.append(status)
    if approver_id:
        query += """
            AND d.id IN (
                SELECT doc.id FROM documents doc
                JOIN approval_flows af ON af.document_type_id = doc.document_type_id AND af.is_active=1
                JOIN approval_steps ast ON ast.flow_id = af.id AND ast.step_order = doc.current_step
                WHERE (ast.approver_id=? OR ast.approver_role=(SELECT role FROM staffs WHERE id=?))
                AND doc.status='in_review'
            )
        """
        params.extend([approver_id, approver_id])
    query += " ORDER BY d.updated_at DESC"
    documents = [dict(r) for r in conn.execute(query, params).fetchall()]

    # ステップ数を付与
    for doc in documents:
        flow = get_active_flow(conn, doc['document_type_id'])
        doc['total_steps'] = len(get_steps(conn, flow['id'])) if flow else 0

    # カウント
    total_count = conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
    in_review_count = conn.execute("SELECT COUNT(*) FROM documents WHERE status='in_review'").fetchone()[0]

    # 自分の承認待ちID
    current = request.state.staff
    my_rows = conn.execute("""
        SELECT d.id FROM documents d
        JOIN approval_flows af ON af.document_type_id = d.document_type_id AND af.is_active=1
        JOIN approval_steps ast ON ast.flow_id = af.id AND ast.step_order = d.current_step
        WHERE d.status='in_review'
        AND (ast.approver_id=? OR ast.approver_role=(SELECT role FROM staffs WHERE id=?))
    """, (current['id'], current['id'])).fetchall()
    my_turn_ids = {r[0] for r in my_rows}
    my_pending_count = len(my_turn_ids)

    document_types = [dict(r) for r in conn.execute("SELECT * FROM document_types WHERE is_active=1").fetchall()]
    conn.close()

    return templates_approval.TemplateResponse("approval/list.html", {
        "request": request,
        "documents": documents,
        "document_types": document_types,
        "status": status,
        "total_count": total_count,
        "in_review_count": in_review_count,
        "my_pending_count": my_pending_count,
        "my_turn_ids": my_turn_ids,
        "current": current,
    })



@router.get("/settings", response_class=HTMLResponse)
def approval_settings_page(request: Request):
    conn = db()
    document_types = [dict(r) for r in conn.execute("SELECT * FROM document_types WHERE is_active=1").fetchall()]
    flows_raw = conn.execute("""
        SELECT af.*, dt.name as type_name
        FROM approval_flows af JOIN document_types dt ON af.document_type_id=dt.id
        WHERE af.is_active=1
    """).fetchall()
    flows = []
    for f in flows_raw:
        fd = dict(f)
        steps = conn.execute("""
            SELECT ast.*, s.name as approver_name
            FROM approval_steps ast LEFT JOIN staffs s ON ast.approver_id=s.id
            WHERE ast.flow_id=? ORDER BY ast.step_order
        """, (f['id'],)).fetchall()
        fd['steps'] = [dict(s) for s in steps]
        flows.append(fd)
    staffs = [dict(r) for r in conn.execute("SELECT id,name,role FROM staffs WHERE is_active=1").fetchall()]
    conn.close()
    return templates_approval.TemplateResponse("approval/settings.html", {
        "request": request, "document_types": document_types,
        "flows": flows, "staffs": staffs, "current": request.state.staff,
    })
@router.get("/{doc_id}", response_class=HTMLResponse)
def approval_detail_page(doc_id: int, request: Request):
    conn = db()
    doc = conn.execute("""
        SELECT d.*, dt.name as type_name, s.name as uploader_name
        FROM documents d
        JOIN document_types dt ON d.document_type_id = dt.id
        JOIN staffs s ON d.uploaded_by = s.id
        WHERE d.id=?
    """, (doc_id,)).fetchone()
    if not doc:
        conn.close()
        raise HTTPException(404, "Not found")
    doc = dict(doc)

    logs = [dict(r) for r in conn.execute("""
        SELECT al.*, s.name as approver_name
        FROM approval_logs al JOIN staffs s ON al.approver_id=s.id
        WHERE al.document_id=? ORDER BY al.created_at ASC
    """, (doc_id,)).fetchall()]

    flow = get_active_flow(conn, doc['document_type_id'])
    steps = get_steps(conn, flow['id']) if flow else []
    steps = [dict(s) for s in steps]

    # 承認者名を付与
    for s in steps:
        if s.get('approver_id'):
            row = conn.execute("SELECT name FROM staffs WHERE id=?", (s['approver_id'],)).fetchone()
            s['approver_name'] = row['name'] if row else None
        else:
            s['approver_name'] = None

    current = request.state.staff
    # 自分のターンか
    is_my_turn = False
    if doc['status'] == 'in_review' and flow:
        cur_step = next((s for s in steps if s['step_order'] == doc['current_step']), None)
        if cur_step:
            is_my_turn = (
                cur_step.get('approver_id') == current['id'] or
                cur_step.get('approver_role') == current.get('role')
            )
    conn.close()
    return templates_approval.TemplateResponse("approval/detail.html", {
        "request": request, "doc": doc, "logs": logs,
        "steps": steps, "is_my_turn": is_my_turn, "current": current,
    })