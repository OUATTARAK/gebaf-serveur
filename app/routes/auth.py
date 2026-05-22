from fastapi import APIRouter, Request, Form, Depends
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import User
from app.auth import verify_password
from app.routes import render, flash

router = APIRouter()


@router.get("/login")
def login_form(request: Request, next: str = "/"):
    if request.session.get("user_id"):
        return RedirectResponse(url="/", status_code=303)
    return render(request, "login.html", next=next, error=None)


@router.post("/login")
def login_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    next: str = Form("/"),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.email == email.lower().strip()).first()
    if not user or not user.active or not verify_password(password, user.password_hash):
        return render(request, "login.html", next=next, error="Identifiants invalides ou compte désactivé")
    request.session["user_id"] = user.id
    flash(request, f"Bienvenue {user.full_name}", "success")
    target = next if next and next.startswith("/") else "/"
    return RedirectResponse(url=target, status_code=303)


@router.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)
