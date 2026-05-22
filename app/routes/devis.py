from datetime import date, timedelta
from fastapi import APIRouter, Request, Depends, Form, HTTPException
from fastapi.responses import RedirectResponse, Response
from sqlalchemy.orm import Session, selectinload

from app.db import get_db
from app.auth import require_user, can_edit
from app.models import Devis, DevisItem, DevisStatus, Chantier, User
from app.utils import next_devis_number, recompute_devis_totals, audit
from app.pdf import render_devis_pdf
from app.routes import render, flash

router = APIRouter()


def _parse_date(s: str):
    s = (s or "").strip()
    if not s:
        return None
    try:
        return date.fromisoformat(s)
    except ValueError:
        return None


def _float(s: str, default: float = 0.0) -> float:
    try:
        return float((s or "").replace(",", ".").strip())
    except (ValueError, AttributeError):
        return default


@router.get("/devis")
def list_devis(
    request: Request, db: Session = Depends(get_db), user: User = Depends(require_user),
    statut: str = "",
):
    query = db.query(Devis).options(selectinload(Devis.chantier).selectinload(Chantier.client))
    if statut:
        try:
            query = query.filter(Devis.status == DevisStatus(statut))
        except ValueError:
            pass
    devis = query.order_by(Devis.date.desc(), Devis.id.desc()).all()
    return render(request, "devis/list.html", devis=devis, statut=statut, statuses=list(DevisStatus))


@router.get("/devis/new")
def new_devis(
    request: Request, db: Session = Depends(get_db), user: User = Depends(require_user),
    chantier_id: int | None = None,
):
    if not can_edit(user, "devis"):
        raise HTTPException(403)
    chantiers = db.query(Chantier).order_by(Chantier.reference.desc()).all()
    return render(request, "devis/form.html",
                  devis=None, chantiers=chantiers,
                  selected_chantier=chantier_id,
                  next_number=next_devis_number(db),
                  statuses=list(DevisStatus),
                  default_validity=(date.today() + timedelta(days=30)).isoformat())


@router.post("/devis/new")
async def create_devis(
    request: Request, db: Session = Depends(get_db), user: User = Depends(require_user),
):
    if not can_edit(user, "devis"):
        raise HTTPException(403)
    form = await request.form()
    number = (form.get("number") or "").strip() or next_devis_number(db)
    chantier_id = int(form.get("chantier_id"))
    d = Devis(
        number=number,
        chantier_id=chantier_id,
        date=_parse_date(form.get("date")) or date.today(),
        validity_date=_parse_date(form.get("validity_date")),
        tva_rate=_float(form.get("tva_rate"), 20.0),
        status=DevisStatus(form.get("status") or "brouillon"),
        notes=(form.get("notes") or "").strip() or None,
    )
    db.add(d); db.flush()
    # Items
    descs = form.getlist("item_description")
    qtys = form.getlist("item_quantity")
    units = form.getlist("item_unit")
    pus = form.getlist("item_unit_price")
    for i, desc in enumerate(descs):
        if not desc.strip():
            continue
        db.add(DevisItem(
            devis_id=d.id, ordering=i,
            description=desc.strip(),
            quantity=_float(qtys[i] if i < len(qtys) else "1", 1.0),
            unit=(units[i] if i < len(units) else "u") or "u",
            unit_price_ht=_float(pus[i] if i < len(pus) else "0"),
        ))
    db.flush()
    db.refresh(d)
    recompute_devis_totals(d)
    audit(db, user.id, "devis.create", "devis", d.id, d.number)
    db.commit()
    flash(request, f"Devis {d.number} créé", "success")
    return RedirectResponse(url=f"/devis/{d.id}", status_code=303)


@router.get("/devis/{did}")
def view_devis(request: Request, did: int, db: Session = Depends(get_db), user: User = Depends(require_user)):
    d = db.query(Devis).filter(Devis.id == did).first()
    if not d:
        raise HTTPException(404)
    return render(request, "devis/detail.html", devis=d)


@router.get("/devis/{did}/edit")
def edit_devis(request: Request, did: int, db: Session = Depends(get_db), user: User = Depends(require_user)):
    if not can_edit(user, "devis"):
        raise HTTPException(403)
    d = db.query(Devis).filter(Devis.id == did).first()
    if not d:
        raise HTTPException(404)
    chantiers = db.query(Chantier).order_by(Chantier.reference.desc()).all()
    return render(request, "devis/form.html",
                  devis=d, chantiers=chantiers,
                  statuses=list(DevisStatus))


@router.post("/devis/{did}/edit")
async def update_devis(
    request: Request, did: int, db: Session = Depends(get_db), user: User = Depends(require_user),
):
    if not can_edit(user, "devis"):
        raise HTTPException(403)
    d = db.query(Devis).filter(Devis.id == did).first()
    if not d:
        raise HTTPException(404)
    form = await request.form()
    d.chantier_id = int(form.get("chantier_id"))
    d.date = _parse_date(form.get("date")) or d.date
    d.validity_date = _parse_date(form.get("validity_date"))
    d.tva_rate = _float(form.get("tva_rate"), 20.0)
    d.status = DevisStatus(form.get("status") or "brouillon")
    d.notes = (form.get("notes") or "").strip() or None
    # Reset items
    for it in list(d.items):
        db.delete(it)
    db.flush()
    descs = form.getlist("item_description")
    qtys = form.getlist("item_quantity")
    units = form.getlist("item_unit")
    pus = form.getlist("item_unit_price")
    for i, desc in enumerate(descs):
        if not desc.strip():
            continue
        db.add(DevisItem(
            devis_id=d.id, ordering=i,
            description=desc.strip(),
            quantity=_float(qtys[i] if i < len(qtys) else "1", 1.0),
            unit=(units[i] if i < len(units) else "u") or "u",
            unit_price_ht=_float(pus[i] if i < len(pus) else "0"),
        ))
    db.flush()
    db.refresh(d)
    recompute_devis_totals(d)
    audit(db, user.id, "devis.update", "devis", d.id, d.number)
    db.commit()
    flash(request, f"Devis {d.number} mis à jour", "success")
    return RedirectResponse(url=f"/devis/{d.id}", status_code=303)


@router.post("/devis/{did}/status")
def change_status(
    request: Request, did: int, db: Session = Depends(get_db), user: User = Depends(require_user),
    status: str = Form(...),
):
    if not can_edit(user, "devis"):
        raise HTTPException(403)
    d = db.query(Devis).filter(Devis.id == did).first()
    if not d:
        raise HTTPException(404)
    d.status = DevisStatus(status)
    if d.status == DevisStatus.ACCEPTE and not d.accepted_date:
        d.accepted_date = date.today()
    audit(db, user.id, f"devis.status.{status}", "devis", d.id, d.number)
    db.commit()
    flash(request, "Statut du devis mis à jour", "success")
    return RedirectResponse(url=f"/devis/{d.id}", status_code=303)


@router.get("/devis/{did}/pdf")
def devis_pdf(did: int, db: Session = Depends(get_db), user: User = Depends(require_user)):
    d = db.query(Devis).filter(Devis.id == did).first()
    if not d:
        raise HTTPException(404)
    pdf = render_devis_pdf(d)
    return Response(
        content=pdf, media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="devis_{d.number}.pdf"'},
    )


@router.post("/devis/{did}/delete")
def delete_devis(request: Request, did: int, db: Session = Depends(get_db), user: User = Depends(require_user)):
    if not can_edit(user, "devis"):
        raise HTTPException(403)
    d = db.query(Devis).filter(Devis.id == did).first()
    if not d:
        raise HTTPException(404)
    num = d.number
    cid = d.chantier_id
    db.delete(d)
    audit(db, user.id, "devis.delete", "devis", did, num)
    db.commit()
    flash(request, f"Devis {num} supprimé", "warning")
    return RedirectResponse(url=f"/chantiers/{cid}", status_code=303)


@router.post("/devis/{did}/to-facture")
def devis_to_facture(request: Request, did: int, db: Session = Depends(get_db), user: User = Depends(require_user)):
    """Crée une facture à partir d'un devis accepté."""
    if not can_edit(user, "facture"):
        raise HTTPException(403)
    d = db.query(Devis).filter(Devis.id == did).first()
    if not d:
        raise HTTPException(404)
    from app.models import Facture, FactureItem, FactureStatus
    from app.utils import next_facture_number, recompute_facture_totals
    f = Facture(
        number=next_facture_number(db),
        chantier_id=d.chantier_id,
        devis_id=d.id,
        date=date.today(),
        due_date=date.today() + timedelta(days=30),
        tva_rate=d.tva_rate,
        status=FactureStatus.BROUILLON,
        notes=d.notes,
    )
    db.add(f); db.flush()
    for it in d.items:
        db.add(FactureItem(
            facture_id=f.id, ordering=it.ordering,
            description=it.description, quantity=it.quantity,
            unit=it.unit, unit_price_ht=it.unit_price_ht,
        ))
    db.flush()
    db.refresh(f)
    recompute_facture_totals(f)
    audit(db, user.id, "facture.create_from_devis", "facture", f.id, f.number)
    db.commit()
    flash(request, f"Facture {f.number} créée depuis le devis", "success")
    return RedirectResponse(url=f"/factures/{f.id}", status_code=303)
