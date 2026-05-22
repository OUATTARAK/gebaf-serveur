from fastapi import APIRouter, Request, Depends, Form, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.auth import require_user, can_edit
from app.models import Contact, ContactType, User
from app.utils import audit
from app.routes import render, flash

router = APIRouter()


@router.get("/contacts")
def list_contacts(
    request: Request, db: Session = Depends(get_db), user: User = Depends(require_user),
    q: str = "", type: str = "",
):
    query = db.query(Contact)
    if q:
        like = f"%{q}%"
        query = query.filter(
            (Contact.name.ilike(like)) | (Contact.company.ilike(like)) |
            (Contact.specialty.ilike(like)) | (Contact.email.ilike(like))
        )
    if type:
        try:
            query = query.filter(Contact.type == ContactType(type))
        except ValueError:
            pass
    contacts = query.order_by(Contact.type, Contact.name).all()
    return render(request, "contacts/list.html", contacts=contacts, q=q, type=type, types=list(ContactType))


@router.get("/contacts/new")
def new_contact(request: Request, user: User = Depends(require_user)):
    if not can_edit(user, "contact"):
        raise HTTPException(403)
    return render(request, "contacts/form.html", contact=None, types=list(ContactType))


@router.post("/contacts/new")
def create_contact(
    request: Request, db: Session = Depends(get_db), user: User = Depends(require_user),
    type: str = Form("fournisseur"),
    name: str = Form(...),
    company: str = Form(""),
    email: str = Form(""),
    phone: str = Form(""),
    address: str = Form(""),
    specialty: str = Form(""),
    notes: str = Form(""),
):
    if not can_edit(user, "contact"):
        raise HTTPException(403)
    c = Contact(
        type=ContactType(type), name=name.strip(),
        company=company.strip() or None, email=email.strip() or None,
        phone=phone.strip() or None, address=address.strip() or None,
        specialty=specialty.strip() or None, notes=notes.strip() or None,
    )
    db.add(c); db.flush()
    audit(db, user.id, "contact.create", "contact", c.id, c.name)
    db.commit()
    flash(request, "Contact ajouté", "success")
    return RedirectResponse(url="/contacts", status_code=303)


@router.get("/contacts/{cid}/edit")
def edit_contact(request: Request, cid: int, db: Session = Depends(get_db), user: User = Depends(require_user)):
    if not can_edit(user, "contact"):
        raise HTTPException(403)
    c = db.query(Contact).filter(Contact.id == cid).first()
    if not c:
        raise HTTPException(404)
    return render(request, "contacts/form.html", contact=c, types=list(ContactType))


@router.post("/contacts/{cid}/edit")
def update_contact(
    request: Request, cid: int, db: Session = Depends(get_db), user: User = Depends(require_user),
    type: str = Form("fournisseur"),
    name: str = Form(...),
    company: str = Form(""),
    email: str = Form(""),
    phone: str = Form(""),
    address: str = Form(""),
    specialty: str = Form(""),
    notes: str = Form(""),
):
    if not can_edit(user, "contact"):
        raise HTTPException(403)
    c = db.query(Contact).filter(Contact.id == cid).first()
    if not c:
        raise HTTPException(404)
    c.type = ContactType(type); c.name = name.strip()
    c.company = company.strip() or None; c.email = email.strip() or None
    c.phone = phone.strip() or None; c.address = address.strip() or None
    c.specialty = specialty.strip() or None; c.notes = notes.strip() or None
    audit(db, user.id, "contact.update", "contact", c.id, c.name)
    db.commit()
    flash(request, "Contact mis à jour", "success")
    return RedirectResponse(url="/contacts", status_code=303)


@router.post("/contacts/{cid}/delete")
def delete_contact(request: Request, cid: int, db: Session = Depends(get_db), user: User = Depends(require_user)):
    if not can_edit(user, "contact"):
        raise HTTPException(403)
    c = db.query(Contact).filter(Contact.id == cid).first()
    if not c:
        raise HTTPException(404)
    name = c.name
    db.delete(c)
    audit(db, user.id, "contact.delete", "contact", cid, name)
    db.commit()
    flash(request, "Contact supprimé", "warning")
    return RedirectResponse(url="/contacts", status_code=303)
