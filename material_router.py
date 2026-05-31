import os, uuid, mimetypes, httpx, asyncio
from pathlib import Path
from fastapi import APIRouter, Request, Form, File, UploadFile, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.templating import Jinja2Templates
import sqlite3

TEMPLATES = Jinja2Templates(directory="templates")
router    = APIRouter(prefix="/materials", tags=["materials"])

DB_PATH    = os.path.join(os.path.dirname(__file__), "sales_app.db")
UPLOAD_DIR = Path(__file__).parent / "uploads" / "materials"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".doc", ".xlsx", ".xls", ".pptx", ".ppt"}
MAX_FILE_SIZE_MB   = 50
ANTHROPIC_API_KEY  = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL    = "claude-sonnet-4-20250514"


def get_db():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


def _staff_id(request):
    staff = getattr(request.state, "staff", None)
    if staff is None:
        raise HTTPException(status_code=401)
    return staff["id"]


async def generate_ai_summary(file_path, file_name, file_type):
    if not ANTHROPIC_API_KEY:
        return ""
    if file_type == ".pdf":
        try:
            import base64
            b64 = base64.b64encode(file_path.read_bytes()).decode()
            payload = {
                "model": ANTHROPIC_MODEL,
                "max_tokens": 512,
                "messages": [{"role": "user", "content": [
                    {"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": b64}},
                    {"type": "text", "text": "この文書の内容を日本語で3〜5文に要約してください。箇条書きは使わず連続した文章で。"}
                ]}]
            }
        except Exception:
            payload = None
    else:
        payload = None

    if payload is None:
        payload = {
            "model": ANTHROPIC_MODEL,
            "max_tokens": 256,
            "messages": [{"role": "user", "content": f"ファイル名: {file_name}\nこのファイル名から推測される資料の内容を日本語2〜3文で説明してください。"}]
        }

    try:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={"x-api-key": ANTHROPIC_API_KEY, "anthropic-version": "2023-06-01", "content-type": "application/json"},
                json=payload,
            )
            data = resp.json()
            return "\n".join(b["text"] for b in data.get("content", []) if b.get("type") == "text").strip()
    except Exception as e:
        print(f"[AI Summary] error: {e}")
        return ""


async def _safe_summary(file_path, file_name, file_type):
    try:
        return await asyncio.wait_for(generate_ai_summary(file_path, file_name, file_type), timeout=30.0)
    except Exception:
        return ""


@router.get("/", response_class=HTMLResponse)
async def material_list(request: Request, q: str = "", category_id: int = 0, tag: str = "", fav_only: int = 0):
    staff_id = _staff_id(request)
    con = get_db()
    categories = con.execute("SELECT * FROM material_categories ORDER BY sort_order").fetchall()
    tags = con.execute(
        "SELECT mt.* FROM material_tags mt JOIN material_tag_relations mtr ON mt.id=mtr.tag_id GROUP BY mt.id ORDER BY mt.name"
    ).fetchall()

    sql = """
        SELECT m.*, mc.name AS category_name, s.name AS uploader_name,
               CASE WHEN f.id IS NOT NULL THEN 1 ELSE 0 END AS is_fav,
               GROUP_CONCAT(mt.name, '|') AS tag_names
        FROM materials m
        LEFT JOIN material_categories mc ON m.category_id=mc.id
        LEFT JOIN staffs s ON m.uploaded_by=s.id
        LEFT JOIN favorites f ON f.material_id=m.id AND f.staff_id=?
        LEFT JOIN material_tag_relations mtr ON mtr.material_id=m.id
        LEFT JOIN material_tags mt ON mt.id=mtr.tag_id
        WHERE m.is_active=1
    """
    params = [staff_id]
    if q:
        sql += " AND (m.title LIKE ? OR m.description LIKE ? OR m.ai_summary LIKE ?)"
        params += [f"%{q}%"] * 3
    if category_id:
        sql += " AND m.category_id=?"
        params.append(category_id)
    if tag:
        sql += " AND m.id IN (SELECT material_id FROM material_tag_relations mtr2 JOIN material_tags mt2 ON mt2.id=mtr2.tag_id WHERE mt2.name=?)"
        params.append(tag)
    if fav_only:
        sql += " AND f.id IS NOT NULL"
    sql += " GROUP BY m.id ORDER BY m.updated_at DESC"

    materials = con.execute(sql, params).fetchall()
    con.close()
    return TEMPLATES.TemplateResponse("materials/list.html", {
        "request": request, "materials": materials, "categories": categories,
        "tags": tags, "q": q, "category_id": category_id, "tag": tag, "fav_only": fav_only,
    })


@router.post("/upload")
async def upload_material(
    request: Request,
    title: str = Form(""),
    description: str = Form(""),
    category_id: int = Form(0),
    tags: str = Form(""),
    files: list[UploadFile] = File(...),
):
    staff_id = _staff_id(request)
    con = get_db()
    results = []

    for f in files:
        suffix = Path(f.filename).suffix.lower()
        if suffix not in ALLOWED_EXTENSIONS:
            results.append({"file": f.filename, "status": "skipped", "reason": "非対応形式"})
            continue
        content = await f.read()
        if len(content) > MAX_FILE_SIZE_MB * 1024 * 1024:
            results.append({"file": f.filename, "status": "skipped", "reason": "サイズ超過"})
            continue

        unique_name = f"{uuid.uuid4().hex}{suffix}"
        dest = UPLOAD_DIR / unique_name
        dest.write_bytes(content)
        display_title = title or Path(f.filename).stem
        ai_summary = await _safe_summary(dest, f.filename, suffix)

        cur = con.cursor()
        cur.execute(
            "INSERT INTO materials (title, description, category_id, file_path, file_name, file_type, file_size, ai_summary, uploaded_by) VALUES (?,?,?,?,?,?,?,?,?)",
            (display_title, description, category_id or None,
             str(dest.relative_to(Path(__file__).parent)), f.filename, suffix, len(content), ai_summary, staff_id),
        )
        material_id = cur.lastrowid

        if tags:
            for tag_name in [t.strip() for t in tags.split(",") if t.strip()]:
                cur.execute("INSERT OR IGNORE INTO material_tags (name) VALUES (?)", (tag_name,))
                tag_id = cur.execute("SELECT id FROM material_tags WHERE name=?", (tag_name,)).fetchone()[0]
                cur.execute("INSERT OR IGNORE INTO material_tag_relations VALUES (?,?)", (material_id, tag_id))

        cur.execute(
            "INSERT INTO material_versions (material_id, version, file_path, file_name, file_size, ai_summary, uploaded_by, note) VALUES (?,1,?,?,?,?,?,'初版')",
            (material_id, str(dest.relative_to(Path(__file__).parent)), f.filename, len(content), ai_summary, staff_id),
        )
        con.commit()
        results.append({"file": f.filename, "status": "ok", "material_id": material_id})

    con.close()
    return JSONResponse({"results": results})


@router.post("/{material_id}/update")
async def update_material_version(request: Request, material_id: int, note: str = Form(""), file: UploadFile = File(...)):
    staff_id = _staff_id(request)
    con = get_db()
    row = con.execute("SELECT * FROM materials WHERE id=?", (material_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404)

    suffix = Path(file.filename).suffix.lower()
    content = await file.read()
    dest = UPLOAD_DIR / f"{uuid.uuid4().hex}{suffix}"
    dest.write_bytes(content)
    ai_summary = await _safe_summary(dest, file.filename, suffix)
    new_ver = row["version"] + 1
    rel_path = str(dest.relative_to(Path(__file__).parent))

    con.execute(
        "UPDATE materials SET file_path=?, file_name=?, file_size=?, ai_summary=?, version=?, updated_at=datetime('now','localtime') WHERE id=?",
        (rel_path, file.filename, len(content), ai_summary, new_ver, material_id),
    )
    con.execute(
        "INSERT INTO material_versions (material_id, version, file_path, file_name, file_size, ai_summary, uploaded_by, note) VALUES (?,?,?,?,?,?,?,?)",
        (material_id, new_ver, rel_path, file.filename, len(content), ai_summary, staff_id, note),
    )
    con.commit()
    con.close()
    return JSONResponse({"status": "ok", "version": new_ver})


@router.post("/{material_id}/favorite")
async def toggle_favorite(request: Request, material_id: int):
    staff_id = _staff_id(request)
    con = get_db()
    existing = con.execute("SELECT id FROM favorites WHERE staff_id=? AND material_id=?", (staff_id, material_id)).fetchone()
    if existing:
        con.execute("DELETE FROM favorites WHERE id=?", (existing["id"],))
        is_fav = False
    else:
        con.execute("INSERT INTO favorites (staff_id, material_id) VALUES (?,?)", (staff_id, material_id))
        is_fav = True
    con.commit()
    con.close()
    return JSONResponse({"is_fav": is_fav})


@router.get("/{material_id}/file")
async def serve_file(request: Request, material_id: int):
    _staff_id(request)
    con = get_db()
    row = con.execute("SELECT file_path, file_name, file_type FROM materials WHERE id=? AND is_active=1", (material_id,)).fetchone()
    con.close()
    if not row:
        raise HTTPException(status_code=404)
    path = Path(__file__).parent / row["file_path"]
    if not path.exists():
        raise HTTPException(status_code=404)
    media_type = mimetypes.guess_type(row["file_name"])[0] or "application/octet-stream"
    if row["file_type"] == ".pdf":
        return FileResponse(path, media_type=media_type, headers={"Content-Disposition": "inline"})
    return FileResponse(path, media_type=media_type, filename=row["file_name"])
@router.get("/{material_id}/download")
async def download_file(request: Request, material_id: int):
    _staff_id(request)
    con = get_db()
    row = con.execute(
        "SELECT file_path, file_name, file_type FROM materials WHERE id=? AND is_active=1",
        (material_id,),
    ).fetchone()
    con.close()
    if not row:
        raise HTTPException(status_code=404)
    path = Path(__file__).parent / row["file_path"]
    if not path.exists():
        raise HTTPException(status_code=404)
    media_type = mimetypes.guess_type(row["file_name"])[0] or "application/octet-stream"
    return FileResponse(path, media_type=media_type, filename=row["file_name"],
                        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{row['file_name']}"})


@router.get("/{material_id}/json")
async def material_detail_json(request: Request, material_id: int):
    staff_id = _staff_id(request)
    con = get_db()
    row = con.execute(
        """SELECT m.*, mc.name AS category_name, s.name AS uploader_name,
                  CASE WHEN f.id IS NOT NULL THEN 1 ELSE 0 END AS is_fav
           FROM materials m
           LEFT JOIN material_categories mc ON m.category_id=mc.id
           LEFT JOIN staffs s ON m.uploaded_by=s.id
           LEFT JOIN favorites f ON f.material_id=m.id AND f.staff_id=?
           WHERE m.id=? AND m.is_active=1""",
        (staff_id, material_id),
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404)
    tags = con.execute(
        "SELECT mt.name FROM material_tags mt JOIN material_tag_relations mtr ON mt.id=mtr.tag_id WHERE mtr.material_id=?",
        (material_id,),
    ).fetchall()
    versions = con.execute("SELECT * FROM material_versions WHERE material_id=? ORDER BY version DESC", (material_id,)).fetchall()
    con.close()
    return JSONResponse({**dict(row), "tags": [t["name"] for t in tags], "versions": [dict(v) for v in versions]})


@router.post("/categories")
async def add_category(request: Request, name: str = Form(...), description: str = Form("")):
    _staff_id(request)
    con = get_db()
    con.execute("INSERT INTO material_categories (name, description) VALUES (?,?)", (name, description))
    con.commit()
    con.close()
    return JSONResponse({"status": "ok"})


@router.put("/categories/{cat_id}")
async def edit_category(request: Request, cat_id: int, name: str = Form(...)):
    _staff_id(request)
    con = get_db()
    con.execute("UPDATE material_categories SET name=? WHERE id=?", (name, cat_id))
    con.commit()
    con.close()
    return JSONResponse({"status": "ok"})


@router.post("/from-approval/{document_id}")
async def import_from_approval(request: Request, document_id: int, category_id: int = Form(0), tags: str = Form("")):
    staff_id = _staff_id(request)
    con = get_db()
    doc = con.execute("SELECT * FROM documents WHERE id=?", (document_id,)).fetchone()
    if not doc:
        raise HTTPException(status_code=404)

    existing = con.execute("SELECT id FROM materials WHERE from_approval=?", (document_id,)).fetchone()
    suffix = Path(doc["file_path"]).suffix.lower()
    src = Path(__file__).parent / doc["file_path"]
    dest = UPLOAD_DIR / f"{uuid.uuid4().hex}{suffix}"
    dest.write_bytes(src.read_bytes())
    ai_summary = await _safe_summary(dest, doc["file_name"], suffix)
    rel_path = str(dest.relative_to(Path(__file__).parent))

    if existing:
        material_id = existing["id"]
        row = con.execute("SELECT version FROM materials WHERE id=?", (material_id,)).fetchone()
        new_ver = row["version"] + 1
        con.execute(
            "UPDATE materials SET file_path=?, file_name=?, file_size=?, ai_summary=?, version=?, updated_at=datetime('now','localtime') WHERE id=?",
            (rel_path, doc["file_name"], src.stat().st_size, ai_summary, new_ver, material_id),
        )
        con.execute(
            "INSERT INTO material_versions (material_id, version, file_path, file_name, file_size, ai_summary, uploaded_by, note) VALUES (?,?,?,?,?,?,?,'承認済み更新')",
            (material_id, new_ver, rel_path, doc["file_name"], src.stat().st_size, ai_summary, staff_id),
        )
    else:
        cur = con.cursor()
        cur.execute(
            "INSERT INTO materials (title, category_id, file_path, file_name, file_type, file_size, ai_summary, uploaded_by, from_approval) VALUES (?,?,?,?,?,?,?,?,?)",
            (doc["title"], category_id or None, rel_path, doc["file_name"], suffix, src.stat().st_size, ai_summary, staff_id, document_id),
        )
        material_id = cur.lastrowid
        con.execute(
            "INSERT INTO material_versions (material_id, version, file_path, file_name, file_size, ai_summary, uploaded_by, note) VALUES (?,1,?,?,?,?,?,'承認済み取込')",
            (material_id, rel_path, doc["file_name"], src.stat().st_size, ai_summary, staff_id),
        )

    for tag_name in [t.strip() for t in tags.split(",") if t.strip()]:
        con.execute("INSERT OR IGNORE INTO material_tags (name) VALUES (?)", (tag_name,))
        tag_id = con.execute("SELECT id FROM material_tags WHERE name=?", (tag_name,)).fetchone()[0]
        con.execute("INSERT OR IGNORE INTO material_tag_relations VALUES (?,?)", (material_id, tag_id))

    con.commit()
    con.close()
    return JSONResponse({"status": "ok", "material_id": material_id})