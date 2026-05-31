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
