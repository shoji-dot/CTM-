import os, uuid, mimetypes
from pathlib import Path
from fastapi import APIRouter, Request, Form, File, UploadFile, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse, RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy import or_, text as _sa_text
from database import SessionLocal, get_db
from logging_config import get_logger

logger = get_logger(__name__)
from models import (
    Material, MaterialCategory, MaterialTag, MaterialTagRelation,
    MaterialVersion, Favorite
)

from templates_config import templates as TEMPLATES
router    = APIRouter(prefix="/materials", tags=["materials"])

UPLOAD_DIR = Path(__file__).parent / "uploads" / "materials"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


# [Medium-1] パストラバーサル対策
_APP_ROOT = Path(__file__).parent.resolve()

def _safe_resolve(file_path_str: str) -> Path:
    """DBから取得したfile_pathがUPLOAD_DIR内を指すか検証する。"""
    resolved = (_APP_ROOT / file_path_str).resolve()
    if not resolved.is_relative_to(UPLOAD_DIR.resolve()):
        logger.warning(
            "[security] パストラバーサル試行を検知: %s -> %s",
            file_path_str, resolved,
        )
        raise HTTPException(status_code=403, detail="アクセスが拒否されました")
    return resolved

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".doc", ".xlsx", ".xls", ".pptx", ".ppt"}

# [I8] マジックバイトによるファイル種別検証（外部ライブラリ不要）
_MAGIC_SIGNATURES: list = [
    (b'%PDF',                         {".pdf"}),
    (b'PK' + b'\x03\x04',            {".docx", ".xlsx", ".pptx"}),
    (bytes([0xD0, 0xCF, 0x11, 0xE0]), {".doc", ".xls", ".ppt"}),
]

def _validate_file_magic(content: bytes, suffix: str) -> bool:
    """ファイルの先頭バイトが拡張子と一致するか確認する。"""
    for magic, allowed_suffixes in _MAGIC_SIGNATURES:
        if content[:len(magic)] == magic:
            return suffix in allowed_suffixes
    return False
MAX_FILE_SIZE_MB   = 50
DROPBOX_TOKEN      = os.getenv("DROPBOX_ACCESS_TOKEN", "")
DROPBOX_FOLDER     = "/CTM_materials"


def _get_dropbox_client():
    if not DROPBOX_TOKEN:
        return None
    try:
        import dropbox
        return dropbox.Dropbox(DROPBOX_TOKEN)
    except Exception:
        return None


def _dropbox_upload(content: bytes, remote_name: str) -> str:
    """Upload bytes to Dropbox, return 'dropbox:/<remote_name>'."""
    dbx = _get_dropbox_client()
    if not dbx:
        return ""
    import dropbox
    remote_path = f"{DROPBOX_FOLDER}/{remote_name}"
    dbx.files_upload(content, remote_path, mode=dropbox.files.WriteMode.overwrite)
    return f"dropbox:{remote_path}"


def _dropbox_get_link(dropbox_path: str) -> str:
    """Return a temporary direct-download link for a Dropbox path."""
    dbx = _get_dropbox_client()
    if not dbx:
        return ""
    # dropbox_path format: "dropbox:/CTM_materials/xxx.pdf"
    remote_path = dropbox_path[len("dropbox:"):]
    try:
        link = dbx.files_get_temporary_link(remote_path)
        return link.link
    except Exception as e:
        logger.error("[Dropbox] get_link error: %s", e, exc_info=True)
        return ""


def _is_dropbox_path(path: str) -> bool:
    return path.startswith("dropbox:")



def _staff_id(request):
    staff = getattr(request.state, "staff", None)
    if staff is None:
        raise HTTPException(status_code=401)
    return staff["id"]



@router.get("/", response_class=HTMLResponse)
async def material_list(request: Request, q: str = "", category_id: int = 0, tag: str = "", fav_only: int = 0):
    staff_id = _staff_id(request)
    db = get_db()
    try:
        categories = [
            {"id": c.id, "name": c.name}
            for c in db.query(MaterialCategory).order_by(MaterialCategory.sort_order).all()
        ]
        tags = [
            {"id": t.id, "name": t.name}
            for t in (
                db.query(MaterialTag)
                .join(MaterialTagRelation)
                .group_by(MaterialTag.id)
                .order_by(MaterialTag.name)
                .all()
            )
        ]

        query = db.query(Material).filter(Material.is_active == True)
        if q:
            like = f"%{q}%"
            query = query.filter(
                or_(Material.title.ilike(like), Material.description.ilike(like))
            )
        if category_id:
            query = query.filter(Material.category_id == category_id)
        if tag:
            query = query.filter(
                Material.id.in_(
                    db.query(MaterialTagRelation.material_id)
                    .join(MaterialTag)
                    .filter(MaterialTag.name == tag)
                )
            )
        if fav_only:
            query = query.filter(
                Material.id.in_(
                    db.query(Favorite.material_id).filter(Favorite.staff_id == staff_id)
                )
            )

        raw_materials = query.order_by(Material.updated_at.desc()).all()
        fav_ids = {f.material_id for f in db.query(Favorite).filter(Favorite.staff_id == staff_id).all()}

        materials = []
        for m in raw_materials:
            d = {c.name: getattr(m, c.name) for c in m.__table__.columns}
            for k, v in d.items():
                if hasattr(v, "isoformat"):
                    d[k] = v.isoformat()
            d["category_name"] = m.category.name if m.category else ""
            d["uploader_name"] = m.uploader.name if m.uploader else ""
            d["is_fav"] = 1 if m.id in fav_ids else 0
            d["tag_names"] = "|".join(r.tag.name for r in m.tag_relations)
            materials.append(d)

    finally:
        db.close()

    return TEMPLATES.TemplateResponse(request, "materials/list.html", {
        "materials": materials, "categories": categories,
        "tags": tags, "q": q, "category_id": category_id, "tag": tag, "fav_only": fav_only
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
    db = get_db()
    results = []
    try:
        for f in files:
            suffix = Path(f.filename).suffix.lower()
            if suffix not in ALLOWED_EXTENSIONS:
                results.append({"file": f.filename, "status": "skipped", "reason": "非対応形式"})
                continue
            content = await f.read()
            if len(content) > MAX_FILE_SIZE_MB * 1024 * 1024:
                results.append({"file": f.filename, "status": "skipped", "reason": "サイズ超過"})
                continue
            # [I8] マジックバイト検証（拡張子偽装を検出）
            if not _validate_file_magic(content, suffix):
                results.append({"file": f.filename, "status": "skipped", "reason": "ファイル形式が拡張子と一致しません"})
                continue

            unique_name = f"{uuid.uuid4().hex}{suffix}"
            dest = UPLOAD_DIR / unique_name
            dest.write_bytes(content)
            display_title = title or Path(f.filename).stem
            
            # Dropbox upload
            if DROPBOX_TOKEN:
                file_path_str = _dropbox_upload(content, unique_name)
                if not file_path_str:
                    file_path_str = str(dest.relative_to(Path(__file__).parent))
            else:
                file_path_str = str(dest.relative_to(Path(__file__).parent))

            material = Material(
                title=display_title,
                description=description,
                category_id=category_id or None,
                file_path=file_path_str,
                file_name=f.filename,
                file_type=suffix,
                file_size=len(content),
                uploaded_by=staff_id,
            )
            db.add(material)
            db.flush()

            for tag_name in [t.strip() for t in tags.split(",") if t.strip()]:
                tag_obj = db.query(MaterialTag).filter(MaterialTag.name == tag_name).first()
                if not tag_obj:
                    tag_obj = MaterialTag(name=tag_name)
                    db.add(tag_obj)
                    db.flush()
                db.add(MaterialTagRelation(material_id=material.id, tag_id=tag_obj.id))

            db.add(MaterialVersion(
                material_id=material.id,
                version=1,
                file_path=file_path_str,
                file_name=f.filename,
                file_size=len(content),
                uploaded_by=staff_id,
                note="初版",
            ))
            db.commit()
            results.append({"file": f.filename, "status": "ok", "material_id": material.id})

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()

    return JSONResponse({"results": results})


@router.post("/{material_id}/update")
async def update_material_version(request: Request, material_id: int, note: str = Form(""), file: UploadFile = File(...)):
    staff_id = _staff_id(request)
    db = get_db()
    try:
        material = db.query(Material).filter(Material.id == material_id).first()
        if not material:
            raise HTTPException(status_code=404)

        suffix = Path(file.filename).suffix.lower()
        content = await file.read()
        unique_name = f"{uuid.uuid4().hex}{suffix}"
        dest = UPLOAD_DIR / unique_name
        dest.write_bytes(content)
        new_ver = material.version + 1

        if DROPBOX_TOKEN:
            rel_path = _dropbox_upload(content, unique_name)
            if not rel_path:
                rel_path = str(dest.relative_to(Path(__file__).parent))
        else:
            rel_path = str(dest.relative_to(Path(__file__).parent))

        material.file_path = rel_path
        material.file_name = file.filename
        material.file_size = len(content)
        material.ai_summary = ai_summary
        material.version = new_ver

        db.add(MaterialVersion(
            material_id=material_id,
            version=new_ver,
            file_path=rel_path,
            file_name=file.filename,
            file_size=len(content),
            uploaded_by=staff_id,
            note=note,
        ))
        db.commit()
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()

    return JSONResponse({"status": "ok", "version": new_ver})


@router.post("/{material_id}/edit")
async def edit_material(
    request: Request,
    material_id: int,
    title: str = Form(...),
    description: str = Form(""),
    category_id: int = Form(0),
    tags: str = Form(""),
):
    _staff_id(request)
    db = get_db()
    try:
        material = db.query(Material).filter(Material.id == material_id).first()
        if not material:
            raise HTTPException(status_code=404)
        material.title = title
        material.description = description
        material.category_id = category_id or None

        db.query(MaterialTagRelation).filter(MaterialTagRelation.material_id == material_id).delete()
        for tag_name in [t.strip() for t in tags.split(",") if t.strip()]:
            tag_obj = db.query(MaterialTag).filter(MaterialTag.name == tag_name).first()
            if not tag_obj:
                tag_obj = MaterialTag(name=tag_name)
                db.add(tag_obj)
                db.flush()
            db.add(MaterialTagRelation(material_id=material_id, tag_id=tag_obj.id))

        db.commit()
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()
    return JSONResponse({"status": "ok"})


@router.post("/{material_id}/delete")
async def delete_material(request: Request, material_id: int):
    _staff_id(request)
    db = get_db()
    try:
        material = db.query(Material).filter(Material.id == material_id).first()
        if not material:
            raise HTTPException(status_code=404)
        material.is_active = False
        db.commit()
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()
    return JSONResponse({"status": "ok"})


@router.post("/{material_id}/favorite")
async def toggle_favorite(request: Request, material_id: int):
    staff_id = _staff_id(request)
    db = get_db()
    try:
        existing = db.query(Favorite).filter(
            Favorite.staff_id == staff_id,
            Favorite.material_id == material_id
        ).first()
        if existing:
            db.delete(existing)
            is_fav = False
        else:
            db.add(Favorite(staff_id=staff_id, material_id=material_id))
            is_fav = True
        db.commit()
    finally:
        db.close()
    return JSONResponse({"is_fav": is_fav})


@router.get("/{material_id}/file")
async def serve_file(request: Request, material_id: int):
    _staff_id(request)
    db = get_db()
    try:
        material = db.query(Material).filter(Material.id == material_id, Material.is_active == True).first()
        if not material:
            raise HTTPException(status_code=404)
        file_path_str = material.file_path
        file_name = material.file_name
        file_type = material.file_type
    finally:
        db.close()

    if _is_dropbox_path(file_path_str):
        link = _dropbox_get_link(file_path_str)
        if not link:
            raise HTTPException(status_code=404, detail="Dropboxからリンクを取得できませんでした")
        return RedirectResponse(url=link)

    path = _safe_resolve(file_path_str)   # [Medium-1] パストラバーサル対策
    if not path.exists():
        raise HTTPException(status_code=404)
    media_type = mimetypes.guess_type(file_name)[0] or "application/octet-stream"
    if file_type == ".pdf":
        return FileResponse(path, media_type=media_type, headers={"Content-Disposition": "inline"})
    return FileResponse(path, media_type=media_type, filename=file_name)


@router.get("/{material_id}/download")
async def download_file(request: Request, material_id: int):
    _staff_id(request)
    db = get_db()
    try:
        material = db.query(Material).filter(Material.id == material_id, Material.is_active == True).first()
        if not material:
            raise HTTPException(status_code=404)
        file_path_str = material.file_path
        file_name = material.file_name
    finally:
        db.close()

    if _is_dropbox_path(file_path_str):
        link = _dropbox_get_link(file_path_str)
        if not link:
            raise HTTPException(status_code=404, detail="Dropboxからリンクを取得できませんでした")
        return RedirectResponse(url=link)

    path = _safe_resolve(file_path_str)   # [Medium-1] パストラバーサル対策
    if not path.exists():
        raise HTTPException(status_code=404)
    media_type = mimetypes.guess_type(file_name)[0] or "application/octet-stream"
    return FileResponse(path, media_type=media_type, filename=file_name,
                        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{file_name}"})


@router.get("/{material_id}/json")
async def material_detail_json(request: Request, material_id: int):
    staff_id = _staff_id(request)
    db = get_db()
    try:
        material = db.query(Material).filter(Material.id == material_id, Material.is_active == True).first()
        if not material:
            raise HTTPException(status_code=404)

        is_fav = db.query(Favorite).filter(
            Favorite.staff_id == staff_id, Favorite.material_id == material_id
        ).first() is not None

        tags = [r.tag.name for r in material.tag_relations]
        versions = [
            {c.name: getattr(v, c.name) for c in v.__table__.columns}
            for v in sorted(material.versions, key=lambda x: x.version, reverse=True)
        ]

        d = {c.name: getattr(material, c.name) for c in material.__table__.columns}
        d["category_name"] = material.category.name if material.category else ""
        d["uploader_name"] = material.uploader.name if material.uploader else ""
        d["is_fav"] = is_fav
        d["tags"] = tags
        d["versions"] = versions
    finally:
        db.close()

    for key, val in d.items():
        if hasattr(val, "isoformat"):
            d[key] = val.isoformat()
    for v in versions:
        for key, val in v.items():
            if hasattr(val, "isoformat"):
                v[key] = val.isoformat()

    return JSONResponse(d)


@router.post("/categories")
async def add_category(request: Request, name: str = Form(...), description: str = Form("")):
    _staff_id(request)
    db = get_db()
    try:
        db.add(MaterialCategory(name=name, description=description))
        db.commit()
    finally:
        db.close()
    return JSONResponse({"status": "ok"})


@router.put("/categories/{cat_id}")
async def edit_category(request: Request, cat_id: int, name: str = Form(...)):
    _staff_id(request)
    db = get_db()
    try:
        cat = db.query(MaterialCategory).filter(MaterialCategory.id == cat_id).first()
        if cat:
            cat.name = name
            db.commit()
    finally:
        db.close()
    return JSONResponse({"status": "ok"})


@router.post("/from-approval/{document_id}")
async def import_from_approval(request: Request, document_id: int, category_id: int = Form(0), tags: str = Form("")):
    staff_id = _staff_id(request)
    db = get_db()
    try:
        doc_row = db.execute(_sa_text("SELECT * FROM documents WHERE id=:id"), {"id": document_id}).fetchone()
        if not doc_row:
            raise HTTPException(status_code=404)
        doc = dict(doc_row._mapping)

        suffix = Path(doc["file_path"]).suffix.lower()
        src = Path(__file__).parent / doc["file_path"]
        dest = UPLOAD_DIR / f"{uuid.uuid4().hex}{suffix}"
        dest.write_bytes(src.read_bytes())
        rel_path = str(dest.relative_to(Path(__file__).parent))
        file_size = src.stat().st_size

        existing = db.query(Material).filter(Material.from_approval == document_id).first()

        if existing:
            material = existing
            new_ver = material.version + 1
            material.file_path = rel_path
            material.file_name = doc["file_name"]
            material.file_size = file_size
            material.ai_summary = ai_summary
            material.version = new_ver
            db.add(MaterialVersion(
                material_id=material.id,
                version=new_ver,
                file_path=rel_path,
                file_name=doc["file_name"],
                file_size=file_size,
                uploaded_by=staff_id,
                note="承認済み更新",
            ))
        else:
            material = Material(
                title=doc["title"],
                category_id=category_id or None,
                file_path=rel_path,
                file_name=doc["file_name"],
                file_type=suffix,
                file_size=file_size,
                uploaded_by=staff_id,
                from_approval=document_id,
            )
            db.add(material)
            db.flush()
            db.add(MaterialVersion(
                material_id=material.id,
                version=1,
                file_path=rel_path,
                file_name=doc["file_name"],
                file_size=file_size,
                uploaded_by=staff_id,
                note="承認済み取込",
            ))

        for tag_name in [t.strip() for t in tags.split(",") if t.strip()]:
            tag_obj = db.query(MaterialTag).filter(MaterialTag.name == tag_name).first()
            if not tag_obj:
                tag_obj = MaterialTag(name=tag_name)
                db.add(tag_obj)
                db.flush()
            exists_rel = db.query(MaterialTagRelation).filter(
                MaterialTagRelation.material_id == material.id,
                MaterialTagRelation.tag_id == tag_obj.id
            ).first()
            if not exists_rel:
                db.add(MaterialTagRelation(material_id=material.id, tag_id=tag_obj.id))

        db.commit()
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()

    return JSONResponse({"status": "ok", "material_id": material.id})
