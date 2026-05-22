from datetime import date, datetime, timedelta
from fastapi import APIRouter, Request, Depends, Form, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session, selectinload

from app.db import get_db
from app.auth import require_user, can_edit
from app.models import Intervention, InterventionStatus, Chantier, Contact, User
from app.utils import audit
from app.routes import render, flash

router = APIRouter()


def _parse_dt(s):
    s = (s or "").strip()
    if not s:
        return None
    try:
        # input datetime-local renvoie "YYYY-MM-DDTHH:MM"
        return datetime.fromisoformat(s)
    except ValueError:
        return None


@router.get("/planning")
def planning_view(
    request: Request, db: Session = Depends(get_db), user: User = Depends(require_user),
    year: int | None = None, month: int | None = None,
):
    today = date.today()
    y = year or today.year
    m = month or today.month
    # bornes du mois
    first = date(y, m, 1)
    if m == 12:
        next_first = date(y + 1, 1, 1)
    else:
        next_first = date(y, m + 1, 1)
    last = next_first - timedelta(days=1)

    interventions = db.query(Intervention).options(
        selectinload(Intervention.chantier), selectinload(Intervention.assignee),
    ).filter(
        Intervention.start_dt < datetime.combine(next_first, datetime.min.time()),
        Intervention.end_dt >= datetime.combine(first, datetime.min.time()),
    ).order_by(Intervention.start_dt).all()

    # Map: date -> [interventions]
    by_day: dict[date, list[Intervention]] = {}
    for iv in interventions:
        d = iv.start_dt.date()
        end_d = iv.end_dt.date()
        cur = d
        while cur <= end_d and cur <= last:
            if cur >= first:
                by_day.setdefault(cur, []).append(iv)
            cur += timedelta(days=1)

    # Construction grille calendrier (semaines)
    # Lundi = jour 0
    weekday_first = first.weekday()
    grid_start = first - timedelta(days=weekday_first)
    weeks = []
    cur = grid_start
    while cur <= last or cur.weekday() != 0:
        week = []
        for _ in range(7):
            week.append({
                "date": cur, "in_month": cur.month == m,
                "is_today": cur == today,
                "events": by_day.get(cur, []),
            })
            cur += timedelta(days=1)
        weeks.append(week)
        if cur > last and cur.weekday() == 0:
            break

    prev_y, prev_m = (y - 1, 12) if m == 1 else (y, m - 1)
    next_y, next_m = (y + 1, 1) if m == 12 else (y, m + 1)
    return render(request, "planning/calendar.html",
                  year=y, month=m, weeks=weeks,
                  prev_y=prev_y, prev_m=prev_m, next_y=next_y, next_m=next_m,
                  month_name=["", "Janvier", "Février", "Mars", "Avril", "Mai", "Juin",
                              "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre"][m],
                  today=today)


@router.get("/interventions/new")
def new_intervention(
    request: Request, db: Session = Depends(get_db), user: User = Depends(require_user),
    chantier_id: int | None = None, start: str | None = None,
):
    if not can_edit(user, "intervention"):
        raise HTTPException(403)
    chantiers = db.query(Chantier).order_by(Chantier.reference.desc()).all()
    users = db.query(User).filter(User.active == True).order_by(User.full_name).all()  # noqa
    contacts = db.query(Contact).order_by(Contact.name).all()
    default_start = start or datetime.now().replace(minute=0, second=0, microsecond=0).strftime("%Y-%m-%dT%H:%M")
    return render(request, "planning/form.html",
                  intervention=None, chantiers=chantiers, users=users, contacts=contacts,
                  selected_chantier=chantier_id, default_start=default_start,
                  statuses=list(InterventionStatus))


@router.post("/interventions/new")
def create_intervention(
    request: Request, db: Session = Depends(get_db), user: User = Depends(require_user),
    chantier_id: int = Form(...),
    title: str = Form(...),
    description: str = Form(""),
    start_dt: str = Form(...),
    end_dt: str = Form(...),
    assignee_id: str = Form(""),
    contact_id: str = Form(""),
    status: str = Form("planifiee"),
):
    if not can_edit(user, "intervention"):
        raise HTTPException(403)
    iv = Intervention(
        chantier_id=chantier_id, title=title.strip(),
        description=description.strip() or None,
        start_dt=_parse_dt(start_dt) or datetime.now(),
        end_dt=_parse_dt(end_dt) or datetime.now(),
        assignee_id=int(assignee_id) if assignee_id else None,
        contact_id=int(contact_id) if contact_id else None,
        status=InterventionStatus(status),
    )
    db.add(iv); db.flush()
    audit(db, user.id, "intervention.create", "intervention", iv.id, iv.title)
    db.commit()
    flash(request, "Intervention planifiée", "success")
    return RedirectResponse(url="/planning", status_code=303)


@router.get("/interventions/{iid}/edit")
def edit_intervention(request: Request, iid: int, db: Session = Depends(get_db), user: User = Depends(require_user)):
    if not can_edit(user, "intervention"):
        raise HTTPException(403)
    iv = db.query(Intervention).filter(Intervention.id == iid).first()
    if not iv:
        raise HTTPException(404)
    chantiers = db.query(Chantier).order_by(Chantier.reference.desc()).all()
    users = db.query(User).filter(User.active == True).order_by(User.full_name).all()  # noqa
    contacts = db.query(Contact).order_by(Contact.name).all()
    return render(request, "planning/form.html",
                  intervention=iv, chantiers=chantiers, users=users, contacts=contacts,
                  statuses=list(InterventionStatus))


@router.post("/interventions/{iid}/edit")
def update_intervention(
    request: Request, iid: int, db: Session = Depends(get_db), user: User = Depends(require_user),
    chantier_id: int = Form(...),
    title: str = Form(...),
    description: str = Form(""),
    start_dt: str = Form(...),
    end_dt: str = Form(...),
    assignee_id: str = Form(""),
    contact_id: str = Form(""),
    status: str = Form("planifiee"),
):
    if not can_edit(user, "intervention"):
        raise HTTPException(403)
    iv = db.query(Intervention).filter(Intervention.id == iid).first()
    if not iv:
        raise HTTPException(404)
    iv.chantier_id = chantier_id
    iv.title = title.strip()
    iv.description = description.strip() or None
    iv.start_dt = _parse_dt(start_dt) or iv.start_dt
    iv.end_dt = _parse_dt(end_dt) or iv.end_dt
    iv.assignee_id = int(assignee_id) if assignee_id else None
    iv.contact_id = int(contact_id) if contact_id else None
    iv.status = InterventionStatus(status)
    audit(db, user.id, "intervention.update", "intervention", iv.id)
    db.commit()
    flash(request, "Intervention mise à jour", "success")
    return RedirectResponse(url="/planning", status_code=303)


@router.post("/interventions/{iid}/delete")
def delete_intervention(request: Request, iid: int, db: Session = Depends(get_db), user: User = Depends(require_user)):
    if not can_edit(user, "intervention"):
        raise HTTPException(403)
    iv = db.query(Intervention).filter(Intervention.id == iid).first()
    if not iv:
        raise HTTPException(404)
    db.delete(iv)
    audit(db, user.id, "intervention.delete", "intervention", iid)
    db.commit()
    flash(request, "Intervention supprimée", "warning")
    return RedirectResponse(url="/planning", status_code=303)
