from datetime import date, timedelta
from fastapi import APIRouter, Request, Depends, Form, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session, selectinload
from sqlalchemy import func

from app.db import get_db
from app.auth import require_user, can_edit
from app.models import HeuresTravail, Chantier, User, UserRole
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


@router.get("/heures")
def list_heures(
    request: Request, db: Session = Depends(get_db), user: User = Depends(require_user),
    user_id: int | None = None, chantier_id: int | None = None,
    start: str = "", end: str = "",
):
    today = date.today()
    start_d = _parse_date(start) or today.replace(day=1)
    end_d = _parse_date(end) or today

    query = db.query(HeuresTravail).options(
        selectinload(HeuresTravail.user), selectinload(HeuresTravail.chantier),
    ).filter(HeuresTravail.date >= start_d, HeuresTravail.date <= end_d)

    # Worker / Viewer ne voit que les siennes
    if user.role in (UserRole.WORKER, UserRole.VIEWER):
        query = query.filter(HeuresTravail.user_id == user.id)
    elif user_id:
        query = query.filter(HeuresTravail.user_id == user_id)

    if chantier_id:
        query = query.filter(HeuresTravail.chantier_id == chantier_id)

    heures = query.order_by(HeuresTravail.date.desc()).all()
    total = sum(h.hours for h in heures)
    cout = sum(h.hours * (h.hourly_rate or 0) for h in heures)

    users = db.query(User).filter(User.active == True).order_by(User.full_name).all()  # noqa
    chantiers = db.query(Chantier).order_by(Chantier.reference.desc()).all()

    return render(request, "heures/list.html",
                  heures=heures, total=total, cout=cout,
                  users=users, chantiers=chantiers,
                  filter_user_id=user_id, filter_chantier_id=chantier_id,
                  start=start_d.isoformat(), end=end_d.isoformat())


@router.get("/heures/new")
def new_heures(
    request: Request, db: Session = Depends(get_db), user: User = Depends(require_user),
    chantier_id: int | None = None,
):
    if not can_edit(user, "heure"):
        raise HTTPException(403)
    chantiers = db.query(Chantier).order_by(Chantier.reference.desc()).all()
    users = db.query(User).filter(User.active == True).order_by(User.full_name).all()  # noqa
    return render(request, "heures/form.html",
                  heures=None, chantiers=chantiers, users=users,
                  selected_chantier=chantier_id,
                  today=date.today().isoformat())


@router.post("/heures/new")
def create_heures(
    request: Request, db: Session = Depends(get_db), user: User = Depends(require_user),
    chantier_id: int = Form(...),
    user_id: str = Form(""),
    date_val: str = Form(...),
    hours: str = Form(...),
    description: str = Form(""),
    hourly_rate: str = Form("0"),
):
    if not can_edit(user, "heure"):
        raise HTTPException(403)
    # Worker ne peut saisir que pour lui-même
    if user.role == UserRole.WORKER:
        uid = user.id
    else:
        uid = int(user_id) if user_id else user.id
    h = HeuresTravail(
        user_id=uid, chantier_id=chantier_id,
        date=_parse_date(date_val) or date.today(),
        hours=_float(hours, 0),
        description=description.strip() or None,
        hourly_rate=_float(hourly_rate, 0),
    )
    db.add(h); db.flush()
    audit(db, user.id, "heures.create", "heures", h.id, f"{h.hours}h sur chantier {chantier_id}")
    db.commit()
    flash(request, f"{h.hours}h enregistrée(s)", "success")
    return RedirectResponse(url=f"/chantiers/{chantier_id}#heures", status_code=303)


@router.post("/heures/{hid}/delete")
def delete_heures(request: Request, hid: int, db: Session = Depends(get_db), user: User = Depends(require_user)):
    h = db.query(HeuresTravail).filter(HeuresTravail.id == hid).first()
    if not h:
        raise HTTPException(404)
    # Worker peut supprimer ses propres saisies
    if user.role == UserRole.WORKER and h.user_id != user.id:
        raise HTTPException(403)
    if user.role == UserRole.VIEWER:
        raise HTTPException(403)
    cid = h.chantier_id
    db.delete(h)
    audit(db, user.id, "heures.delete", "heures", hid)
    db.commit()
    flash(request, "Saisie supprimée", "warning")
    return RedirectResponse(url=f"/chantiers/{cid}#heures", status_code=303)
