from fastapi import APIRouter, Request, Depends, Form, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.auth import require_user, hash_password
from app.models import User, UserRole, AuditLog
from app.utils import audit
from app.routes import render, flash

router = APIRouter()


def _require_admin(user: User) -> None:
    if user.role != UserRole.ADMIN:
        raise HTTPException(403, "Réservé aux administrateurs")


@router.get("/admin/users")
def list_users(request: Request, db: Session = Depends(get_db), user: User = Depends(require_user)):
    _require_admin(user)
    users = db.query(User).order_by(User.full_name).all()
    return render(request, "admin/users.html", users=users, roles=list(UserRole))


@router.get("/admin/users/new")
def new_user_form(request: Request, user: User = Depends(require_user)):
    _require_admin(user)
    return render(request, "admin/user_form.html", target=None, roles=list(UserRole))


@router.post("/admin/users/new")
def create_user(
    request: Request, db: Session = Depends(get_db), user: User = Depends(require_user),
    email: str = Form(...),
    full_name: str = Form(...),
    role: str = Form("worker"),
    password: str = Form(...),
):
    _require_admin(user)
    email = email.lower().strip()
    if db.query(User).filter(User.email == email).first():
        return render(request, "admin/user_form.html", target=None, roles=list(UserRole),
                      error="Cet email est déjà utilisé")
    u = User(
        email=email, full_name=full_name.strip(),
        role=UserRole(role), password_hash=hash_password(password),
        active=True,
    )
    db.add(u); db.flush()
    audit(db, user.id, "user.create", "user", u.id, u.email)
    db.commit()
    flash(request, f"Utilisateur {u.email} créé", "success")
    return RedirectResponse(url="/admin/users", status_code=303)


@router.get("/admin/users/{uid}/edit")
def edit_user_form(request: Request, uid: int, db: Session = Depends(get_db), user: User = Depends(require_user)):
    _require_admin(user)
    target = db.query(User).filter(User.id == uid).first()
    if not target:
        raise HTTPException(404)
    return render(request, "admin/user_form.html", target=target, roles=list(UserRole))


@router.post("/admin/users/{uid}/edit")
def update_user(
    request: Request, uid: int, db: Session = Depends(get_db), user: User = Depends(require_user),
    email: str = Form(...),
    full_name: str = Form(...),
    role: str = Form("worker"),
    active: str = Form(""),
    password: str = Form(""),
):
    _require_admin(user)
    target = db.query(User).filter(User.id == uid).first()
    if not target:
        raise HTTPException(404)
    target.email = email.lower().strip()
    target.full_name = full_name.strip()
    target.role = UserRole(role)
    target.active = bool(active)
    if password.strip():
        target.password_hash = hash_password(password)
    audit(db, user.id, "user.update", "user", target.id, target.email)
    db.commit()
    flash(request, "Utilisateur mis à jour", "success")
    return RedirectResponse(url="/admin/users", status_code=303)


@router.post("/admin/users/{uid}/delete")
def delete_user(request: Request, uid: int, db: Session = Depends(get_db), user: User = Depends(require_user)):
    _require_admin(user)
    if uid == user.id:
        flash(request, "Vous ne pouvez pas vous supprimer", "danger")
        return RedirectResponse(url="/admin/users", status_code=303)
    target = db.query(User).filter(User.id == uid).first()
    if not target:
        raise HTTPException(404)
    target.active = False  # désactive plutôt que supprime (intégrité référentielle)
    audit(db, user.id, "user.deactivate", "user", target.id, target.email)
    db.commit()
    flash(request, "Utilisateur désactivé", "warning")
    return RedirectResponse(url="/admin/users", status_code=303)


@router.get("/admin/audit")
def audit_log(request: Request, db: Session = Depends(get_db), user: User = Depends(require_user)):
    _require_admin(user)
    logs = db.query(AuditLog).order_by(AuditLog.timestamp.desc()).limit(500).all()
    return render(request, "admin/audit.html", logs=logs)


# -------- Paramètres généraux --------

@router.get("/admin/settings")
def settings_page(request: Request, db: Session = Depends(get_db), user: User = Depends(require_user)):
    _require_admin(user)
    from app.settings_store import get_company, get_anthropic_key
    company = get_company(db)
    api_key = get_anthropic_key(db) or ""
    # Masque la clé sauf 4 derniers caractères
    masked = ""
    if api_key:
        masked = "•" * max(0, len(api_key) - 6) + api_key[-6:]
    return render(request, "admin/settings.html", company=company, api_key_masked=masked, has_key=bool(api_key))


@router.post("/admin/settings")
def settings_save(
    request: Request, db: Session = Depends(get_db), user: User = Depends(require_user),
    company_name: str = Form(""),
    company_address: str = Form(""),
    company_phone: str = Form(""),
    company_email: str = Form(""),
    company_siret: str = Form(""),
    company_rcs: str = Form(""),
    company_iban: str = Form(""),
    company_tva_intra: str = Form(""),
    anthropic_api_key: str = Form(""),
    clear_anthropic_key: str = Form(""),
):
    _require_admin(user)
    from app.settings_store import set_
    set_(db, "company.name", company_name.strip() or "Mon Entreprise BTP")
    set_(db, "company.address", company_address.strip())
    set_(db, "company.phone", company_phone.strip())
    set_(db, "company.email", company_email.strip())
    set_(db, "company.siret", company_siret.strip())
    set_(db, "company.rcs", company_rcs.strip())
    set_(db, "company.iban", company_iban.strip())
    set_(db, "company.tva_intra", company_tva_intra.strip())
    if clear_anthropic_key:
        set_(db, "anthropic.api_key", "")
        audit(db, user.id, "settings.api_key.cleared")
    elif anthropic_api_key.strip():
        set_(db, "anthropic.api_key", anthropic_api_key.strip())
        audit(db, user.id, "settings.api_key.updated")
    audit(db, user.id, "settings.update")
    db.commit()
    flash(request, "Paramètres enregistrés", "success")
    return RedirectResponse(url="/admin/settings", status_code=303)


@router.post("/admin/settings/test-claude")
async def test_claude(request: Request, db: Session = Depends(get_db), user: User = Depends(require_user)):
    """Petit ping API pour vérifier que la clé fonctionne."""
    _require_admin(user)
    from app.settings_store import get_anthropic_key
    key = get_anthropic_key(db)
    if not key:
        flash(request, "Aucune clé Anthropic configurée", "warning")
        return RedirectResponse(url="/admin/settings", status_code=303)
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=key)
        msg = client.messages.create(
            model="claude-haiku-4-5", max_tokens=20,
            messages=[{"role": "user", "content": "Réponds juste 'OK'"}],
        )
        txt = msg.content[0].text if msg.content else ""
        flash(request, f"Clé Anthropic valide. Réponse Claude : {txt}", "success")
    except Exception as e:
        flash(request, f"Erreur clé Anthropic : {e}", "danger")
    return RedirectResponse(url="/admin/settings", status_code=303)
