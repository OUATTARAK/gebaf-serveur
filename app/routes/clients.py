from fastapi import APIRouter, Request, Depends, Form, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.auth import require_user, can_edit
from app.models import Client, ClientType, User
from app.utils import audit
from app.routes import render, flash

router = APIRouter()


@router.get("/clients")
def list_clients(request: Request, db: Session = Depends(get_db), user: User = Depends(require_user), q: str = ""):
    query = db.query(Client)
    if q:
        like = f"%{q}%"
        query = query.filter((Client.name.ilike(like)) | (Client.email.ilike(like)) | (Client.phone.ilike(like)))
    clients = query.order_by(Client.name).all()
    return render(request, "clients/list.html", clients=clients, q=q, types=list(ClientType))


@router.get("/clients/new")
def new_client(request: Request, user: User = Depends(require_user)):
    if not can_edit(user, "client"):
        raise HTTPException(403)
    return render(request, "clients/form.html", client=None, types=list(ClientType))


@router.post("/clients/new")
def create_client(
    request: Request, db: Session = Depends(get_db), user: User = Depends(require_user),
    name: str = Form(...),
    type: str = Form("particulier"),
    email: str = Form(""),
    phone: str = Form(""),
    address: str = Form(""),
    siret: str = Form(""),
    notes: str = Form(""),
):
    if not can_edit(user, "client"):
        raise HTTPException(403)
    c = Client(
        name=name.strip(), type=ClientType(type),
        email=email.strip() or None, phone=phone.strip() or None,
        address=address.strip() or None, siret=siret.strip() or None,
        notes=notes.strip() or None,
    )
    db.add(c); db.flush()
    audit(db, user.id, "client.create", "client", c.id, c.name)
    db.commit()
    flash(request, "Client créé", "success")
    return RedirectResponse(url=f"/clients/{c.id}", status_code=303)


@router.get("/clients/{cid}")
def view_client(request: Request, cid: int, db: Session = Depends(get_db), user: User = Depends(require_user)):
    c = db.query(Client).filter(Client.id == cid).first()
    if not c:
        raise HTTPException(404)
    return render(request, "clients/detail.html", client=c)


@router.get("/clients/{cid}/edit")
def edit_client(request: Request, cid: int, db: Session = Depends(get_db), user: User = Depends(require_user)):
    if not can_edit(user, "client"):
        raise HTTPException(403)
    c = db.query(Client).filter(Client.id == cid).first()
    if not c:
        raise HTTPException(404)
    return render(request, "clients/form.html", client=c, types=list(ClientType))


@router.post("/clients/{cid}/edit")
def update_client(
    request: Request, cid: int, db: Session = Depends(get_db), user: User = Depends(require_user),
    name: str = Form(...),
    type: str = Form("particulier"),
    email: str = Form(""),
    phone: str = Form(""),
    address: str = Form(""),
    siret: str = Form(""),
    notes: str = Form(""),
):
    if not can_edit(user, "client"):
        raise HTTPException(403)
    c = db.query(Client).filter(Client.id == cid).first()
    if not c:
        raise HTTPException(404)
    c.name = name.strip(); c.type = ClientType(type)
    c.email = email.strip() or None; c.phone = phone.strip() or None
    c.address = address.strip() or None; c.siret = siret.strip() or None
    c.notes = notes.strip() or None
    audit(db, user.id, "client.update", "client", c.id, c.name)
    db.commit()
    flash(request, "Client mis à jour", "success")
    return RedirectResponse(url=f"/clients/{c.id}", status_code=303)


@router.post("/clients/{cid}/delete")
def delete_client(request: Request, cid: int, db: Session = Depends(get_db), user: User = Depends(require_user)):
    if not can_edit(user, "client"):
        raise HTTPException(403)
    c = db.query(Client).filter(Client.id == cid).first()
    if not c:
        raise HTTPException(404)
    if c.chantiers:
        flash(request, "Impossible : ce client a des chantiers rattachés", "danger")
        return RedirectResponse(url=f"/clients/{cid}", status_code=303)
    name = c.name
    db.delete(c)
    audit(db, user.id, "client.delete", "client", cid, name)
    db.commit()
    flash(request, "Client supprimé", "warning")
    return RedirectResponse(url="/clients", status_code=303)
