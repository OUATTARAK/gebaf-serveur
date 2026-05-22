from datetime import date
from pathlib import Path
from uuid import uuid4
from fastapi import APIRouter, Request, Depends, Form, HTTPException, UploadFile, File
from fastapi.responses import RedirectResponse, FileResponse
from sqlalchemy.orm import Session, selectinload

from app.db import get_db, UPLOAD_DIR
from app.auth import require_user, can_edit, can_view
from app.models import Depense, DepenseCategory, Chantier, Contact, ContactType, User, UserRole
from app.utils import audit
from app.routes import render, flash

router = APIRouter()


def _parse_date(s):
    s = (s or "").strip()
    if not s:
        return None
    try:
        return date.fromisoformat(s)
    except ValueError:
        return None


def _float(s, default=0.0):
    try:
        return float((s or "").replace(",", ".").strip())
    except (ValueError, AttributeError):
        return default


@router.get("/depenses")
def list_depenses(
    request: Request, db: Session = Depends(get_db), user: User = Depends(require_user),
    chantier_id: int | None = None, category: str = "",
):
    if not can_view(user, "depense"):
        raise HTTPException(403)
    query = db.query(Depense).options(
        selectinload(Depense.chantier), selectinload(Depense.supplier),
    )
    # Worker ne voit que ses dépenses
    if user.role == UserRole.WORKER:
        query = query.filter(Depense.created_by == user.id)
    if chantier_id:
        query = query.filter(Depense.chantier_id == chantier_id)
    if category:
        try:
            query = query.filter(Depense.category == DepenseCategory(category))
        except ValueError:
            pass
    depenses = query.order_by(Depense.date.desc(), Depense.id.desc()).all()
    total_ht = sum(d.amount_ht for d in depenses)
    total_ttc = sum(d.amount_ttc for d in depenses)
    chantiers = db.query(Chantier).order_by(Chantier.reference.desc()).all()
    return render(request, "depenses/list.html",
                  depenses=depenses, total_ht=total_ht, total_ttc=total_ttc,
                  chantier_id=chantier_id, category=category,
                  categories=list(DepenseCategory), chantiers=chantiers)


@router.get("/depenses/new")
def new_depense(
    request: Request, db: Session = Depends(get_db), user: User = Depends(require_user),
    chantier_id: int | None = None,
):
    if not can_edit(user, "depense"):
        raise HTTPException(403)
    chantiers = db.query(Chantier).order_by(Chantier.reference.desc()).all()
    suppliers = db.query(Contact).filter(
        Contact.type.in_([ContactType.FOURNISSEUR, ContactType.SOUS_TRAITANT, ContactType.ARTISAN])
    ).order_by(Contact.name).all()
    return render(request, "depenses/form.html",
                  depense=None, chantiers=chantiers, suppliers=suppliers,
                  selected_chantier=chantier_id,
                  categories=list(DepenseCategory))


@router.post("/depenses/new")
async def create_depense(
    request: Request, db: Session = Depends(get_db), user: User = Depends(require_user),
    chantier_id: int = Form(...),
    date_val: str = Form(...),
    supplier_id: str = Form(""),
    category: str = Form("materiaux"),
    description: str = Form(...),
    quantity: str = Form("1"),
    unit: str = Form(""),
    amount_ht: str = Form("0"),
    tva_rate: str = Form("20"),
    receipt: UploadFile = File(None),
):
    if not can_edit(user, "depense"):
        raise HTTPException(403)
    ht = _float(amount_ht)
    tva = _float(tva_rate, 20.0)
    ttc = round(ht * (1 + tva / 100), 2)
    receipt_path = None
    if receipt and receipt.filename:
        ext = Path(receipt.filename).suffix
        safe = f"depense_{uuid4().hex}{ext}"
        target = UPLOAD_DIR / safe
        target.write_bytes(await receipt.read())
        receipt_path = safe  # relatif à UPLOAD_DIR
    d = Depense(
        chantier_id=chantier_id,
        date=_parse_date(date_val) or date.today(),
        supplier_id=int(supplier_id) if supplier_id else None,
        category=DepenseCategory(category),
        description=description.strip(),
        quantity=_float(quantity, 1.0),
        unit=unit.strip() or None,
        amount_ht=ht, tva_rate=tva, amount_ttc=ttc,
        receipt_path=receipt_path,
        created_by=user.id,
    )
    db.add(d); db.flush()
    audit(db, user.id, "depense.create", "depense", d.id, f"chantier={chantier_id}, montant={ttc}")
    db.commit()
    flash(request, "Dépense ajoutée", "success")
    return RedirectResponse(url=f"/chantiers/{chantier_id}#depenses", status_code=303)


@router.get("/depenses/{did}/edit")
def edit_depense(request: Request, did: int, db: Session = Depends(get_db), user: User = Depends(require_user)):
    if not can_edit(user, "depense"):
        raise HTTPException(403)
    d = db.query(Depense).filter(Depense.id == did).first()
    if not d:
        raise HTTPException(404)
    if user.role == UserRole.WORKER and d.created_by != user.id:
        raise HTTPException(403)
    chantiers = db.query(Chantier).order_by(Chantier.reference.desc()).all()
    suppliers = db.query(Contact).filter(
        Contact.type.in_([ContactType.FOURNISSEUR, ContactType.SOUS_TRAITANT, ContactType.ARTISAN])
    ).order_by(Contact.name).all()
    return render(request, "depenses/form.html",
                  depense=d, chantiers=chantiers, suppliers=suppliers,
                  categories=list(DepenseCategory))


@router.post("/depenses/{did}/edit")
async def update_depense(
    request: Request, did: int, db: Session = Depends(get_db), user: User = Depends(require_user),
    chantier_id: int = Form(...),
    date_val: str = Form(...),
    supplier_id: str = Form(""),
    category: str = Form("materiaux"),
    description: str = Form(...),
    quantity: str = Form("1"),
    unit: str = Form(""),
    amount_ht: str = Form("0"),
    tva_rate: str = Form("20"),
    receipt: UploadFile = File(None),
):
    if not can_edit(user, "depense"):
        raise HTTPException(403)
    d = db.query(Depense).filter(Depense.id == did).first()
    if not d:
        raise HTTPException(404)
    if user.role == UserRole.WORKER and d.created_by != user.id:
        raise HTTPException(403)
    ht = _float(amount_ht); tva = _float(tva_rate, 20.0)
    d.chantier_id = chantier_id
    d.date = _parse_date(date_val) or d.date
    d.supplier_id = int(supplier_id) if supplier_id else None
    d.category = DepenseCategory(category)
    d.description = description.strip()
    d.quantity = _float(quantity, 1.0); d.unit = unit.strip() or None
    d.amount_ht = ht; d.tva_rate = tva; d.amount_ttc = round(ht * (1 + tva / 100), 2)
    if receipt and receipt.filename:
        ext = Path(receipt.filename).suffix
        safe = f"depense_{uuid4().hex}{ext}"
        (UPLOAD_DIR / safe).write_bytes(await receipt.read())
        d.receipt_path = safe
    audit(db, user.id, "depense.update", "depense", d.id)
    db.commit()
    flash(request, "Dépense mise à jour", "success")
    return RedirectResponse(url=f"/chantiers/{d.chantier_id}#depenses", status_code=303)


@router.get("/depenses/{did}/receipt")
def view_receipt(did: int, db: Session = Depends(get_db), user: User = Depends(require_user)):
    d = db.query(Depense).filter(Depense.id == did).first()
    if not d or not d.receipt_path:
        raise HTTPException(404)
    path = UPLOAD_DIR / d.receipt_path
    if not path.exists():
        raise HTTPException(404)
    return FileResponse(path)


@router.post("/depenses/{did}/delete")
def delete_depense(request: Request, did: int, db: Session = Depends(get_db), user: User = Depends(require_user)):
    if not can_edit(user, "depense"):
        raise HTTPException(403)
    d = db.query(Depense).filter(Depense.id == did).first()
    if not d:
        raise HTTPException(404)
    if user.role == UserRole.WORKER and d.created_by != user.id:
        raise HTTPException(403)
    cid = d.chantier_id
    db.delete(d)
    audit(db, user.id, "depense.delete", "depense", did)
    db.commit()
    flash(request, "Dépense supprimée", "warning")
    return RedirectResponse(url=f"/chantiers/{cid}#depenses", status_code=303)
