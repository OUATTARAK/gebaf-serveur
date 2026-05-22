from pathlib import Path
from uuid import uuid4
from fastapi import APIRouter, Request, Depends, Form, HTTPException, UploadFile, File
from fastapi.responses import RedirectResponse, FileResponse
from sqlalchemy.orm import Session

from app.db import get_db, UPLOAD_DIR
from app.auth import require_user, can_edit
from app.models import Document, DocumentType, Chantier, User
from app.utils import audit
from app.routes import render, flash

router = APIRouter()


@router.post("/chantiers/{cid}/documents/new")
async def upload_documents(
    request: Request, cid: int, db: Session = Depends(get_db), user: User = Depends(require_user),
    files: list[UploadFile] = File(...),
    doc_type: str = Form("autre"),
    description: str = Form(""),
):
    if not can_edit(user, "document"):
        raise HTTPException(403)
    chantier = db.query(Chantier).filter(Chantier.id == cid).first()
    if not chantier:
        raise HTTPException(404)
    count = 0
    for f in files:
        if not f.filename:
            continue
        data = await f.read()
        ext = Path(f.filename).suffix
        safe = f"doc_{uuid4().hex}{ext}"
        target = UPLOAD_DIR / safe
        target.write_bytes(data)
        d = Document(
            chantier_id=cid,
            original_name=f.filename,
            file_path=safe,
            mime_type=f.content_type or None,
            size_bytes=len(data),
            doc_type=DocumentType(doc_type),
            description=description.strip() or None,
            uploaded_by=user.id,
        )
        db.add(d); count += 1
    audit(db, user.id, "document.upload", "chantier", cid, f"count={count}")
    db.commit()
    flash(request, f"{count} document(s) uploadé(s)", "success")
    return RedirectResponse(url=f"/chantiers/{cid}#documents", status_code=303)


@router.get("/documents/{did}")
def download_document(did: int, db: Session = Depends(get_db), user: User = Depends(require_user)):
    d = db.query(Document).filter(Document.id == did).first()
    if not d:
        raise HTTPException(404)
    path = UPLOAD_DIR / d.file_path
    if not path.exists():
        raise HTTPException(404)
    return FileResponse(path, filename=d.original_name, media_type=d.mime_type or "application/octet-stream")


@router.post("/documents/{did}/delete")
def delete_document(request: Request, did: int, db: Session = Depends(get_db), user: User = Depends(require_user)):
    if not can_edit(user, "document"):
        raise HTTPException(403)
    d = db.query(Document).filter(Document.id == did).first()
    if not d:
        raise HTTPException(404)
    cid = d.chantier_id
    path = UPLOAD_DIR / d.file_path
    if path.exists():
        try:
            path.unlink()
        except OSError:
            pass
    db.delete(d)
    audit(db, user.id, "document.delete", "document", did)
    db.commit()
    flash(request, "Document supprimé", "warning")
    return RedirectResponse(url=f"/chantiers/{cid}#documents", status_code=303)
