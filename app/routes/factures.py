from datetime import date, timedelta
from fastapi import APIRouter, Request, Depends, Form, HTTPException
from fastapi.responses import RedirectResponse, Response
from sqlalchemy.orm import Session, selectinload

from app.db import get_db
from app.auth import require_user, can_edit, can_view
from app.models import Facture, FactureItem, FactureStatus, Paiement, Chantier, User
from app.utils import next_facture_number, recompute_facture_totals, audit
from app.pdf import render_facture_pdf
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


def _float(s, default=0.0):
    try:
        return float((s or "").replace(",", ".").strip())
    except (ValueError, AttributeError):
        return default


@router.get("/factures")
def list_factures(
    request: Request, db: Session = Depends(get_db), user: User = Depends(require_user),
    statut: str = "",
):
    if not can_view(user, "facture"):
        raise HTTPException(403)
    query = db.query(Facture).options(selectinload(Facture.chantier).selectinload(Chantier.client))
    if statut:
        try:
            query = query.filter(Facture.status == FactureStatus(statut))
        except ValueError:
            pass
    factures = query.order_by(Facture.date.desc(), Facture.id.desc()).all()
    # Marquer "en retard" celles dues passées non payées
    today = date.today()
    for f in factures:
        if (f.due_date and f.due_date < today and
                f.status in (FactureStatus.ENVOYEE, FactureStatus.PARTIELLEMENT_PAYEE)):
            f.status = FactureStatus.EN_RETARD
    db.commit()
    return render(request, "factures/list.html",
                  factures=factures, statut=statut, statuses=list(FactureStatus))


@router.get("/factures/new")
def new_facture(
    request: Request, db: Session = Depends(get_db), user: User = Depends(require_user),
    chantier_id: int | None = None,
):
    if not can_edit(user, "facture"):
        raise HTTPException(403)
    chantiers = db.query(Chantier).order_by(Chantier.reference.desc()).all()
    return render(request, "factures/form.html",
                  facture=None, chantiers=chantiers,
                  selected_chantier=chantier_id,
                  next_number=next_facture_number(db),
                  default_due=(date.today() + timedelta(days=30)).isoformat(),
                  statuses=list(FactureStatus))


@router.post("/factures/new")
async def create_facture(request: Request, db: Session = Depends(get_db), user: User = Depends(require_user)):
    if not can_edit(user, "facture"):
        raise HTTPException(403)
    form = await request.form()
    f = Facture(
        number=(form.get("number") or "").strip() or next_facture_number(db),
        chantier_id=int(form.get("chantier_id")),
        date=_parse_date(form.get("date")) or date.today(),
        due_date=_parse_date(form.get("due_date")),
        tva_rate=_float(form.get("tva_rate"), 20.0),
        status=FactureStatus(form.get("status") or "brouillon"),
        notes=(form.get("notes") or "").strip() or None,
    )
    db.add(f); db.flush()
    for i, desc in enumerate(form.getlist("item_description")):
        if not desc.strip():
            continue
        qtys = form.getlist("item_quantity")
        units = form.getlist("item_unit")
        pus = form.getlist("item_unit_price")
        db.add(FactureItem(
            facture_id=f.id, ordering=i,
            description=desc.strip(),
            quantity=_float(qtys[i] if i < len(qtys) else "1", 1.0),
            unit=(units[i] if i < len(units) else "u") or "u",
            unit_price_ht=_float(pus[i] if i < len(pus) else "0"),
        ))
    db.flush(); db.refresh(f)
    recompute_facture_totals(f)
    audit(db, user.id, "facture.create", "facture", f.id, f.number)
    db.commit()
    flash(request, f"Facture {f.number} créée", "success")
    return RedirectResponse(url=f"/factures/{f.id}", status_code=303)


@router.get("/factures/{fid}")
def view_facture(request: Request, fid: int, db: Session = Depends(get_db), user: User = Depends(require_user)):
    if not can_view(user, "facture"):
        raise HTTPException(403)
    f = db.query(Facture).filter(Facture.id == fid).first()
    if not f:
        raise HTTPException(404)
    return render(request, "factures/detail.html", facture=f)


@router.get("/factures/{fid}/edit")
def edit_facture(request: Request, fid: int, db: Session = Depends(get_db), user: User = Depends(require_user)):
    if not can_edit(user, "facture"):
        raise HTTPException(403)
    f = db.query(Facture).filter(Facture.id == fid).first()
    if not f:
        raise HTTPException(404)
    chantiers = db.query(Chantier).order_by(Chantier.reference.desc()).all()
    return render(request, "factures/form.html",
                  facture=f, chantiers=chantiers,
                  statuses=list(FactureStatus))


@router.post("/factures/{fid}/edit")
async def update_facture(
    request: Request, fid: int, db: Session = Depends(get_db), user: User = Depends(require_user),
):
    if not can_edit(user, "facture"):
        raise HTTPException(403)
    f = db.query(Facture).filter(Facture.id == fid).first()
    if not f:
        raise HTTPException(404)
    form = await request.form()
    f.chantier_id = int(form.get("chantier_id"))
    f.date = _parse_date(form.get("date")) or f.date
    f.due_date = _parse_date(form.get("due_date"))
    f.tva_rate = _float(form.get("tva_rate"), 20.0)
    f.status = FactureStatus(form.get("status") or "brouillon")
    f.notes = (form.get("notes") or "").strip() or None
    for it in list(f.items):
        db.delete(it)
    db.flush()
    descs = form.getlist("item_description")
    qtys = form.getlist("item_quantity")
    units = form.getlist("item_unit")
    pus = form.getlist("item_unit_price")
    for i, desc in enumerate(descs):
        if not desc.strip():
            continue
        db.add(FactureItem(
            facture_id=f.id, ordering=i,
            description=desc.strip(),
            quantity=_float(qtys[i] if i < len(qtys) else "1", 1.0),
            unit=(units[i] if i < len(units) else "u") or "u",
            unit_price_ht=_float(pus[i] if i < len(pus) else "0"),
        ))
    db.flush(); db.refresh(f)
    recompute_facture_totals(f)
    audit(db, user.id, "facture.update", "facture", f.id, f.number)
    db.commit()
    flash(request, f"Facture {f.number} mise à jour", "success")
    return RedirectResponse(url=f"/factures/{f.id}", status_code=303)


@router.post("/factures/{fid}/status")
def change_status(
    request: Request, fid: int, db: Session = Depends(get_db), user: User = Depends(require_user),
    status: str = Form(...),
):
    if not can_edit(user, "facture"):
        raise HTTPException(403)
    f = db.query(Facture).filter(Facture.id == fid).first()
    if not f:
        raise HTTPException(404)
    f.status = FactureStatus(status)
    audit(db, user.id, f"facture.status.{status}", "facture", f.id, f.number)
    db.commit()
    flash(request, "Statut mis à jour", "success")
    return RedirectResponse(url=f"/factures/{f.id}", status_code=303)


@router.get("/factures/{fid}/pdf")
def facture_pdf(fid: int, db: Session = Depends(get_db), user: User = Depends(require_user)):
    if not can_view(user, "facture"):
        raise HTTPException(403)
    f = db.query(Facture).filter(Facture.id == fid).first()
    if not f:
        raise HTTPException(404)
    pdf = render_facture_pdf(f)
    return Response(
        content=pdf, media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="facture_{f.number}.pdf"'},
    )


@router.post("/factures/{fid}/delete")
def delete_facture(request: Request, fid: int, db: Session = Depends(get_db), user: User = Depends(require_user)):
    if not can_edit(user, "facture"):
        raise HTTPException(403)
    f = db.query(Facture).filter(Facture.id == fid).first()
    if not f:
        raise HTTPException(404)
    num = f.number; cid = f.chantier_id
    db.delete(f)
    audit(db, user.id, "facture.delete", "facture", fid, num)
    db.commit()
    flash(request, f"Facture {num} supprimée", "warning")
    return RedirectResponse(url=f"/chantiers/{cid}", status_code=303)


# -------- Paiements --------

@router.post("/factures/{fid}/paiements/new")
def add_paiement(
    request: Request, fid: int, db: Session = Depends(get_db), user: User = Depends(require_user),
    date_val: str = Form(...),
    amount: str = Form(...),
    method: str = Form(""),
    reference: str = Form(""),
    notes: str = Form(""),
):
    if not can_edit(user, "paiement"):
        raise HTTPException(403)
    f = db.query(Facture).filter(Facture.id == fid).first()
    if not f:
        raise HTTPException(404)
    p = Paiement(
        facture_id=f.id,
        date=_parse_date(date_val) or date.today(),
        amount=_float(amount),
        method=method.strip() or None,
        reference=reference.strip() or None,
        notes=notes.strip() or None,
    )
    db.add(p); db.flush()
    f.paid_amount = sum(x.amount for x in f.paiements) + p.amount
    recompute_facture_totals(f)
    audit(db, user.id, "paiement.create", "paiement", p.id, f"facture={f.number}, montant={p.amount}")
    db.commit()
    flash(request, f"Paiement de {p.amount:.0f} F CFA enregistré", "success")
    return RedirectResponse(url=f"/factures/{f.id}", status_code=303)


@router.post("/paiements/{pid}/delete")
def delete_paiement(request: Request, pid: int, db: Session = Depends(get_db), user: User = Depends(require_user)):
    if not can_edit(user, "paiement"):
        raise HTTPException(403)
    p = db.query(Paiement).filter(Paiement.id == pid).first()
    if not p:
        raise HTTPException(404)
    f = p.facture
    db.delete(p); db.flush(); db.refresh(f)
    f.paid_amount = sum(x.amount for x in f.paiements)
    recompute_facture_totals(f)
    audit(db, user.id, "paiement.delete", "paiement", pid)
    db.commit()
    flash(request, "Paiement supprimé", "warning")
    return RedirectResponse(url=f"/factures/{f.id}", status_code=303)
