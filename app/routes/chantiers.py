from datetime import date
from fastapi import APIRouter, Request, Depends, Form, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session, selectinload

from app.db import get_db
from app.auth import require_user, can_edit
from app.models import Chantier, Client, ChantierStatus, User
from app.utils import next_chantier_ref, compute_chantier_marge, audit
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


@router.get("/chantiers")
def list_chantiers(
    request: Request, db: Session = Depends(get_db), user: User = Depends(require_user),
    q: str = "", statut: str = "",
):
    query = db.query(Chantier).options(selectinload(Chantier.client))
    if q:
        like = f"%{q}%"
        query = query.outerjoin(Client).filter(
            (Chantier.name.ilike(like)) | (Chantier.reference.ilike(like)) |
            (Chantier.address.ilike(like)) | (Client.name.ilike(like))
        )
    if statut:
        try:
            query = query.filter(Chantier.status == ChantierStatus(statut))
        except ValueError:
            pass
    chantiers = query.order_by(Chantier.id.desc()).all()
    return render(request, "chantiers/list.html",
                  chantiers=chantiers, q=q, statut=statut,
                  statuses=list(ChantierStatus))


@router.get("/chantiers/new")
def new_chantier(request: Request, db: Session = Depends(get_db), user: User = Depends(require_user)):
    if not can_edit(user, "chantier"):
        raise HTTPException(403)
    clients = db.query(Client).order_by(Client.name).all()
    return render(request, "chantiers/form.html",
                  chantier=None, clients=clients,
                  statuses=list(ChantierStatus),
                  next_ref=next_chantier_ref(db))


@router.post("/chantiers/new")
def create_chantier(
    request: Request, db: Session = Depends(get_db), user: User = Depends(require_user),
    reference: str = Form(""),
    name: str = Form(...),
    client_id: str = Form(""),
    address: str = Form(""),
    description: str = Form(""),
    status: str = Form("prospect"),
    start_date: str = Form(""),
    end_date: str = Form(""),
    budget_ht: str = Form("0"),
):
    if not can_edit(user, "chantier"):
        raise HTTPException(403)
    ref = (reference or "").strip() or next_chantier_ref(db)
    try:
        budget = float((budget_ht or "0").replace(",", "."))
    except ValueError:
        budget = 0.0
    c = Chantier(
        reference=ref, name=name.strip(),
        client_id=int(client_id) if client_id else None,
        address=address.strip() or None,
        description=description.strip() or None,
        status=ChantierStatus(status),
        start_date=_parse_date(start_date),
        end_date=_parse_date(end_date),
        budget_ht=budget,
        created_by=user.id,
    )
    db.add(c)
    db.flush()
    audit(db, user.id, "chantier.create", "chantier", c.id, c.reference)
    db.commit()
    flash(request, f"Chantier {c.reference} créé", "success")
    return RedirectResponse(url=f"/chantiers/{c.id}", status_code=303)


@router.get("/chantiers/{cid}")
def view_chantier(request: Request, cid: int, db: Session = Depends(get_db), user: User = Depends(require_user)):
    c = db.query(Chantier).filter(Chantier.id == cid).first()
    if not c:
        raise HTTPException(404)
    marge = compute_chantier_marge(c)
    return render(request, "chantiers/detail.html", chantier=c, marge=marge)


@router.get("/chantiers/{cid}/edit")
def edit_chantier(request: Request, cid: int, db: Session = Depends(get_db), user: User = Depends(require_user)):
    if not can_edit(user, "chantier"):
        raise HTTPException(403)
    c = db.query(Chantier).filter(Chantier.id == cid).first()
    if not c:
        raise HTTPException(404)
    clients = db.query(Client).order_by(Client.name).all()
    return render(request, "chantiers/form.html",
                  chantier=c, clients=clients,
                  statuses=list(ChantierStatus))


@router.post("/chantiers/{cid}/edit")
def update_chantier(
    request: Request, cid: int, db: Session = Depends(get_db), user: User = Depends(require_user),
    name: str = Form(...),
    client_id: str = Form(""),
    address: str = Form(""),
    description: str = Form(""),
    status: str = Form("prospect"),
    start_date: str = Form(""),
    end_date: str = Form(""),
    budget_ht: str = Form("0"),
):
    if not can_edit(user, "chantier"):
        raise HTTPException(403)
    c = db.query(Chantier).filter(Chantier.id == cid).first()
    if not c:
        raise HTTPException(404)
    c.name = name.strip()
    c.client_id = int(client_id) if client_id else None
    c.address = address.strip() or None
    c.description = description.strip() or None
    c.status = ChantierStatus(status)
    c.start_date = _parse_date(start_date)
    c.end_date = _parse_date(end_date)
    try:
        c.budget_ht = float((budget_ht or "0").replace(",", "."))
    except ValueError:
        pass
    audit(db, user.id, "chantier.update", "chantier", c.id, c.reference)
    db.commit()
    flash(request, "Chantier mis à jour", "success")
    return RedirectResponse(url=f"/chantiers/{c.id}", status_code=303)


@router.post("/chantiers/{cid}/delete")
def delete_chantier(request: Request, cid: int, db: Session = Depends(get_db), user: User = Depends(require_user)):
    if not can_edit(user, "chantier"):
        raise HTTPException(403)
    c = db.query(Chantier).filter(Chantier.id == cid).first()
    if not c:
        raise HTTPException(404)
    ref = c.reference
    db.delete(c)
    audit(db, user.id, "chantier.delete", "chantier", cid, ref)
    db.commit()
    flash(request, f"Chantier {ref} supprimé", "warning")
    return RedirectResponse(url="/chantiers", status_code=303)
