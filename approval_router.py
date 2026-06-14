import os
import shutil
from pathlib import Path
from utils import now_jst
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Depends, Request
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import text
from database import get_db
from logging_config import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/approval", tags=["approval"])

UPLOAD_DIR = Path(__file__).parent / "uploads" / "documents"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def _safe_resolve_doc(file_path_str: str) -> Path:
    """DBから取得したfile_pathがUPLOAD_DIR内を指すか検証する。"""
    resolved = Path(file_path_str).resolve()
    if not resolved.is_relative_to(UPLOAD_DIR.resolve()):
        logger.warning(
            "[security] 承認ドキュメントへのパストラバーサル試行: %s -> %s",
            file_path_str, resolved,
        )
        raise HTTPException(status_code=403, detail="アクセスが拒否されました")
    return resolved

from templates_config import templates as templates_approval


def _row(row):
    """SQLAlchemy Row → dict"""
    return dict(row._mapping)

def _rows(rows):
    return [_row(r) for r in rows]

def now():
    return now_jst().strftime('%Y-%m-%d %H:%M:%S')


# ─── Pydantic ─────────────────────────────────────────
class ApprovalAction(BaseModel):
    approver_id: int
    action: str
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
def get_active_flow(db: Session, document_type_id: int):
    row = db.execute(
        text("SELECT * FROM approval_flows WHERE document_type_id=:t AND is_active=TRUE LIMIT 1"),
        {"t": document_type_id}
    ).fetchone()
    return _row(row) if row else None

def get_steps(db: Session, flow_id: int):
    rows = db.execute(
        text("SELECT * FROM approval_steps WHERE flow_id=:f ORDER BY step_order"),
        {"f": flow_id}
    ).fetchall()
    return _rows(rows)

def create_notification(db: Session, document_id: int, recipient_id: int, ntype: str):
    db.execute(
        text("INSERT INTO notifications (document_id, recipient_id, type) VALUES (:d,:r,:t)"),
        {"d": document_id, "r": recipient_id, "t": ntype}
    )


# ─── ドキュメント種別 ─────────────────────────────────
@router.get("/document-types")
def list_document_types(db: Session = Depends(get_db)):
    rows = db.execute(text("SELECT * FROM document_types WHERE is_active=TRUE")).fetchall()
    return _rows(rows)

@router.post("/document-types")
def create_document_type(body: DocumentTypeCreate, db: Session = Depends(get_db)):
    try:
        result = db.execute(
            text("INSERT INTO document_types (name, description) VALUES (:n,:d) RETURNING id"),
            {"n": body.name, "d": body.description}
        )
        new_id = result.scalar()
        db.commit()
        return {"id": new_id, "name": body.name}
    except Exception:
        db.rollback()
        raise HTTPException(400, "同名のドキュメント種別が存在します")

@router.delete("/document-types/{type_id}")
def delete_document_type(type_id: int, db: Session = Depends(get_db)):
    db.execute(text("UPDATE document_types SET is_active=FALSE WHERE id=:i"), {"i": type_id})
    db.commit()
    return {"result": "ok"}


# ─── ドキュメントアップロード ─────────────────────────
@router.post("/documents/upload")
async def upload_document(
    title: str = Form(...),
    document_type_id: int = Form(...),
    uploaded_by: int = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    allowed = [
        'application/pdf',
        'application/msword',
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        'application/vnd.ms-excel',
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    ]
    if file.content_type not in allowed:
        raise HTTPException(400, "PDF/Word/Excelのみアップロード可能です")

    timestamp = now_jst().strftime('%Y%m%d_%H%M%S')
    safe_name = f"{timestamp}_{file.filename}"
    file_path = os.path.join(UPLOAD_DIR, safe_name)
    with open(file_path, 'wb') as f:
        shutil.copyfileobj(file.file, f)
    file_size = os.path.getsize(file_path)

    result = db.execute(
        text("""
            INSERT INTO documents
              (title, document_type_id, file_path, file_name, file_size, mime_type, uploaded_by, status)
            VALUES (:title,:dtype,:fpath,:fname,:fsize,:mime,:uploader,'draft')
            RETURNING id
        """),
        {"title": title, "dtype": document_type_id, "fpath": file_path,
         "fname": file.filename, "fsize": file_size, "mime": file.content_type,
         "uploader": uploaded_by}
    )
    doc_id = result.scalar()
    db.commit()
    return {"id": doc_id, "status": "draft", "message": "アップロード完了"}


@router.get("/documents")
def list_documents(
    status: Optional[str] = None,
    approver_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    query = """
        SELECT d.*, dt.name as type_name, s.name as uploader_name
        FROM documents d
        JOIN document_types dt ON d.document_type_id = dt.id
        JOIN staffs s ON d.uploaded_by = s.id
        WHERE 1=1
    """
    params: dict = {}
    if status:
        query += " AND d.status=:status"
        params["status"] = status
    if approver_id:
        query += """
            AND d.id IN (
                SELECT doc.id FROM documents doc
                JOIN approval_flows af ON af.document_type_id = doc.document_type_id AND af.is_active=TRUE
                JOIN approval_steps ast ON ast.flow_id = af.id AND ast.step_order = doc.current_step
                WHERE (ast.approver_id=:aid OR ast.approver_role=(SELECT role FROM staffs WHERE id=:aid2))
                AND doc.status='in_review'
            )
        """
        params["aid"] = approver_id
        params["aid2"] = approver_id
    query += " ORDER BY d.updated_at DESC"
    rows = db.execute(text(query), params).fetchall()
    return _rows(rows)


@router.get("/documents/{doc_id}")
def get_document(doc_id: int, db: Session = Depends(get_db)):
    row = db.execute(
        text("""
            SELECT d.*, dt.name as type_name, s.name as uploader_name
            FROM documents d
            JOIN document_types dt ON d.document_type_id = dt.id
            JOIN staffs s ON d.uploaded_by = s.id
            WHERE d.id=:i
        """),
        {"i": doc_id}
    ).fetchone()
    if not row:
        raise HTTPException(404, "ドキュメントが見つかりません")
    return _row(row)


@router.get("/documents/{doc_id}/file")
def download_document(doc_id: int, db: Session = Depends(get_db)):
    row = db.execute(
        text("SELECT file_path, file_name FROM documents WHERE id=:i"),
        {"i": doc_id}
    ).fetchone()
    if not row:
        raise HTTPException(404, "ドキュメントが見つかりません")
    r = _row(row)
    safe_path = _safe_resolve_doc(r['file_path'])  # [Medium-1] パストラバーサル対策
    if not safe_path.exists():
        raise HTTPException(404, "ファイルが見つかりません")
    return FileResponse(str(safe_path), filename=r['file_name'])


# ─── 承認フロー申請 ───────────────────────────────────
@router.post("/documents/{doc_id}/submit")
def submit_document(doc_id: int, submitter_id: int, db: Session = Depends(get_db)):
    doc_row = db.execute(text("SELECT * FROM documents WHERE id=:i"), {"i": doc_id}).fetchone()
    if not doc_row:
        raise HTTPException(404, "ドキュメントが見つかりません")
    doc = _row(doc_row)
    if doc['status'] not in ('draft', 'revising'):
        raise HTTPException(400, f"申請できない状態です: {doc['status']}")

    flow = get_active_flow(db, doc['document_type_id'])
    if not flow:
        raise HTTPException(400, "承認フローが設定されていません")
    steps = get_steps(db, flow['id'])
    if not steps:
        raise HTTPException(400, "承認ステップが設定されていません")

    db.execute(
        text("UPDATE documents SET status='in_review', current_step=1, updated_at=:t WHERE id=:i"),
        {"t": now(), "i": doc_id}
    )
    db.execute(
        text("""
            INSERT INTO approval_logs (document_id, step_order, approver_id, action, comment)
            VALUES (:d,0,:a,'submitted','承認申請')
        """),
        {"d": doc_id, "a": submitter_id}
    )
    first_step = steps[0]
    if first_step['approver_id']:
        create_notification(db, doc_id, first_step['approver_id'], 'approval_request')

    db.commit()
    return {"result": "申請完了", "status": "in_review", "next_step": 1}


# ─── 承認・否認・コメント ─────────────────────────────
@router.post("/documents/{doc_id}/action")
def approval_action(doc_id: int, body: ApprovalAction, db: Session = Depends(get_db)):
    if body.action not in ('approved', 'rejected', 'commented'):
        raise HTTPException(400, "actionはapproved/rejected/commentedのいずれか")
    if body.action == 'rejected' and not body.comment:
        raise HTTPException(400, "否認時はコメント必須です")

    doc_row = db.execute(text("SELECT * FROM documents WHERE id=:i"), {"i": doc_id}).fetchone()
    if not doc_row:
        raise HTTPException(404, "ドキュメントが見つかりません")
    doc = _row(doc_row)
    if doc['status'] != 'in_review':
        raise HTTPException(400, "承認中でないドキュメントです")

    flow = get_active_flow(db, doc['document_type_id'])
    steps = get_steps(db, flow['id'])
    current_step = doc['current_step']

    step = next((s for s in steps if s['step_order'] == current_step), None)
    if not step:
        raise HTTPException(400, "ステップ設定が見つかりません")

    approver_row = db.execute(
        text("SELECT * FROM staffs WHERE id=:i"), {"i": body.approver_id}
    ).fetchone()
    if not approver_row:
        raise HTTPException(404, "承認者が見つかりません")
    approver = _row(approver_row)

    is_authorized = (
        step['approver_id'] == body.approver_id or
        step['approver_role'] == approver['role'] or
        approver.get('approval_level', 0) >= step['required_level']
    )
    if not is_authorized:
        raise HTTPException(403, "このステップの承認権限がありません")

    db.execute(
        text("""
            INSERT INTO approval_logs (document_id, step_order, approver_id, action, comment)
            VALUES (:d,:s,:a,:act,:c)
        """),
        {"d": doc_id, "s": current_step, "a": body.approver_id,
         "act": body.action, "c": body.comment}
    )

    if body.action == 'approved':
        next_steps = [s for s in steps if s['step_order'] > current_step]
        if next_steps:
            next_step = next_steps[0]
            db.execute(
                text("UPDATE documents SET current_step=:ns, updated_at=:t WHERE id=:i"),
                {"ns": next_step['step_order'], "t": now(), "i": doc_id}
            )
            if next_step['approver_id']:
                create_notification(db, doc_id, next_step['approver_id'], 'approval_request')
            result = {"result": "承認完了", "status": "in_review", "next_step": next_step['step_order']}
        else:
            db.execute(
                text("UPDATE documents SET status='approved', updated_at=:t WHERE id=:i"),
                {"t": now(), "i": doc_id}
            )
            create_notification(db, doc_id, doc['uploaded_by'], 'approved')
            result = {"result": "最終承認完了", "status": "approved"}

    elif body.action == 'rejected':
        prev_steps = [s for s in steps if s['step_order'] < current_step]
        if prev_steps:
            prev_step = prev_steps[-1]
            db.execute(
                text("UPDATE documents SET status='in_review', current_step=:ps, comment=:c, updated_at=:t WHERE id=:i"),
                {"ps": prev_step['step_order'], "c": body.comment, "t": now(), "i": doc_id}
            )
        else:
            db.execute(
                text("UPDATE documents SET status='revising', current_step=0, comment=:c, updated_at=:t WHERE id=:i"),
                {"c": body.comment, "t": now(), "i": doc_id}
            )
        create_notification(db, doc_id, doc['uploaded_by'], 'rejected')
        result = {"result": "差し戻し", "status": "revising", "comment": body.comment}

    else:  # commented
        db.execute(text("UPDATE documents SET updated_at=:t WHERE id=:i"), {"t": now(), "i": doc_id})
        result = {"result": "コメント追加", "status": "in_review"}

    db.commit()
    return result


# ─── 承認履歴 ─────────────────────────────────────────
@router.get("/documents/{doc_id}/logs")
def get_approval_logs(doc_id: int, db: Session = Depends(get_db)):
    rows = db.execute(
        text("""
            SELECT al.*, s.name as approver_name, s.role as approver_role
            FROM approval_logs al
            JOIN staffs s ON al.approver_id = s.id
            WHERE al.document_id=:i
            ORDER BY al.created_at ASC
        """),
        {"i": doc_id}
    ).fetchall()
    return _rows(rows)


# ─── 承認フロー管理 ───────────────────────────────────
@router.get("/flows")
def list_flows(db: Session = Depends(get_db)):
    rows = db.execute(
        text("""
            SELECT af.*, dt.name as type_name
            FROM approval_flows af
            JOIN document_types dt ON af.document_type_id = dt.id
            WHERE af.is_active=TRUE
        """)
    ).fetchall()
    return _rows(rows)

@router.post("/flows")
def create_flow(body: FlowCreate, db: Session = Depends(get_db)):
    result = db.execute(
        text("INSERT INTO approval_flows (document_type_id, name) VALUES (:d,:n) RETURNING id"),
        {"d": body.document_type_id, "n": body.name}
    )
    new_id = result.scalar()
    db.commit()
    return {"id": new_id}

@router.post("/flows/steps")
def add_step(body: StepCreate, db: Session = Depends(get_db)):
    result = db.execute(
        text("""
            INSERT INTO approval_steps
              (flow_id, step_order, step_name, approver_id, approver_role, required_level)
            VALUES (:f,:so,:sn,:ai,:ar,:rl)
            RETURNING id
        """),
        {"f": body.flow_id, "so": body.step_order, "sn": body.step_name,
         "ai": body.approver_id, "ar": body.approver_role, "rl": body.required_level}
    )
    new_id = result.scalar()
    db.commit()
    return {"id": new_id}

@router.get("/flows/{flow_id}/steps")
def get_flow_steps(flow_id: int, db: Session = Depends(get_db)):
    rows = db.execute(
        text("""
            SELECT ast.*, s.name as approver_name
            FROM approval_steps ast
            LEFT JOIN staffs s ON ast.approver_id = s.id
            WHERE ast.flow_id=:f
            ORDER BY ast.step_order
        """),
        {"f": flow_id}
    ).fetchall()
    return _rows(rows)

@router.delete("/flows/steps/{step_id}")
def delete_step(step_id: int, db: Session = Depends(get_db)):
    db.execute(text("DELETE FROM approval_steps WHERE id=:i"), {"i": step_id})
    db.commit()
    return {"result": "ok"}

@router.delete("/flows/{flow_id}")
def delete_flow(flow_id: int, db: Session = Depends(get_db)):
    db.execute(text("UPDATE approval_flows SET is_active=FALSE WHERE id=:i"), {"i": flow_id})
    db.commit()
    return {"result": "ok"}


# ─── 通知一覧 ─────────────────────────────────────────
@router.get("/notifications/{staff_id}")
def get_notifications(staff_id: int, db: Session = Depends(get_db)):
    rows = db.execute(
        text("""
            SELECT n.*, d.title as doc_title, d.status as doc_status
            FROM notifications n
            JOIN documents d ON n.document_id = d.id
            WHERE n.recipient_id=:r
            ORDER BY n.created_at DESC
            LIMIT 50
        """),
        {"r": staff_id}
    ).fetchall()
    return _rows(rows)


# ─── Jinja2 UI ────────────────────────────────────────
@router.get("/", response_class=HTMLResponse)
def approval_list_page(
    request: Request,
    status: str = None,
    approver_id: int = None,
    db: Session = Depends(get_db)
):
    query = """
        SELECT d.*, dt.name as type_name, s.name as uploader_name
        FROM documents d
        JOIN document_types dt ON d.document_type_id = dt.id
        JOIN staffs s ON d.uploaded_by = s.id
        WHERE 1=1
    """
    params: dict = {}
    if status:
        query += " AND d.status=:status"
        params["status"] = status
    if approver_id:
        query += """
            AND d.id IN (
                SELECT doc.id FROM documents doc
                JOIN approval_flows af ON af.document_type_id = doc.document_type_id AND af.is_active=TRUE
                JOIN approval_steps ast ON ast.flow_id = af.id AND ast.step_order = doc.current_step
                WHERE (ast.approver_id=:aid OR ast.approver_role=(SELECT role FROM staffs WHERE id=:aid2))
                AND doc.status='in_review'
            )
        """
        params["aid"] = approver_id
        params["aid2"] = approver_id
    query += " ORDER BY d.updated_at DESC"
    documents = _rows(db.execute(text(query), params).fetchall())

    for doc in documents:
        flow = get_active_flow(db, doc['document_type_id'])
        doc['total_steps'] = len(get_steps(db, flow['id'])) if flow else 0

    total_count = db.execute(text("SELECT COUNT(*) FROM documents")).scalar()
    in_review_count = db.execute(text("SELECT COUNT(*) FROM documents WHERE status='in_review'")).scalar()

    current = request.state.staff
    my_rows = db.execute(
        text("""
            SELECT d.id FROM documents d
            JOIN approval_flows af ON af.document_type_id = d.document_type_id AND af.is_active=TRUE
            JOIN approval_steps ast ON ast.flow_id = af.id AND ast.step_order = d.current_step
            WHERE d.status='in_review'
            AND (ast.approver_id=:aid OR ast.approver_role=(SELECT role FROM staffs WHERE id=:aid2))
        """),
        {"aid": current['id'], "aid2": current['id']}
    ).fetchall()
    my_turn_ids = {r[0] for r in my_rows}
    my_pending_count = len(my_turn_ids)

    document_types = _rows(db.execute(text("SELECT * FROM document_types WHERE is_active=TRUE")).fetchall())

    return templates_approval.TemplateResponse(request, "approval/list.html", {
        "documents": documents,
        "document_types": document_types,
        "status": status,
        "total_count": total_count,
        "in_review_count": in_review_count,
        "my_pending_count": my_pending_count,
        "my_turn_ids": my_turn_ids,
        "current": current
    })


@router.get("/settings", response_class=HTMLResponse)
def approval_settings_page(request: Request, db: Session = Depends(get_db)):
    document_types = _rows(db.execute(text("SELECT * FROM document_types WHERE is_active=TRUE")).fetchall())
    flows_raw = _rows(db.execute(
        text("""
            SELECT af.*, dt.name as type_name
            FROM approval_flows af JOIN document_types dt ON af.document_type_id=dt.id
            WHERE af.is_active=TRUE
        """)
    ).fetchall())
    flows = []
    for f in flows_raw:
        steps = _rows(db.execute(
            text("""
                SELECT ast.*, s.name as approver_name
                FROM approval_steps ast LEFT JOIN staffs s ON ast.approver_id=s.id
                WHERE ast.flow_id=:f ORDER BY ast.step_order
            """),
            {"f": f['id']}
        ).fetchall())
        f['steps'] = steps
        flows.append(f)
    staffs = _rows(db.execute(text("SELECT id,name,role FROM staffs WHERE is_active=TRUE")).fetchall())
    return templates_approval.TemplateResponse(request, "approval/settings.html", {
        "document_types": document_types,
        "flows": flows,
        "staffs": staffs,
        "current": request.state.staff
    })


@router.get("/{doc_id}", response_class=HTMLResponse)
def approval_detail_page(doc_id: int, request: Request, db: Session = Depends(get_db)):
    doc_row = db.execute(
        text("""
            SELECT d.*, dt.name as type_name, s.name as uploader_name
            FROM documents d
            JOIN document_types dt ON d.document_type_id = dt.id
            JOIN staffs s ON d.uploaded_by = s.id
            WHERE d.id=:i
        """),
        {"i": doc_id}
    ).fetchone()
    if not doc_row:
        raise HTTPException(404, "Not found")
    doc = _row(doc_row)

    logs = _rows(db.execute(
        text("""
            SELECT al.*, s.name as approver_name
            FROM approval_logs al JOIN staffs s ON al.approver_id=s.id
            WHERE al.document_id=:i ORDER BY al.created_at ASC
        """),
        {"i": doc_id}
    ).fetchall())

    flow = get_active_flow(db, doc['document_type_id'])
    steps = get_steps(db, flow['id']) if flow else []

    for s in steps:
        if s.get('approver_id'):
            r = db.execute(
                text("SELECT name FROM staffs WHERE id=:i"), {"i": s['approver_id']}
            ).fetchone()
            s['approver_name'] = r[0] if r else None
        else:
            s['approver_name'] = None

    current = request.state.staff
    is_my_turn = False
    if doc['status'] == 'in_review' and flow:
        cur_step = next((s for s in steps if s['step_order'] == doc['current_step']), None)
        if cur_step:
            is_my_turn = (
                cur_step.get('approver_id') == current['id'] or
                cur_step.get('approver_role') == current.get('role')
            )

    return templates_approval.TemplateResponse(request, "approval/detail.html", {
        "doc": doc,
        "logs": logs,
        "steps": steps,
        "is_my_turn": is_my_turn,
        "current": current
    })
