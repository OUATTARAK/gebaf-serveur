from typing import Optional, Iterable
from fastapi import Request, HTTPException, status, Depends
from fastapi.responses import RedirectResponse
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import User, UserRole

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(pw: str) -> str:
    return pwd_context.hash(pw)


def verify_password(pw: str, hashed: str) -> bool:
    try:
        return pwd_context.verify(pw, hashed)
    except Exception:
        return False


def current_user(request: Request, db: Session = Depends(get_db)) -> Optional[User]:
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    user = db.query(User).filter(User.id == user_id, User.active == True).first()  # noqa: E712
    return user


def require_user(request: Request, db: Session = Depends(get_db)) -> User:
    user = current_user(request, db)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Login requis")
    return user


def require_roles(*allowed: UserRole):
    """Dépendance : restreint l'accès aux rôles donnés."""
    def _dep(user: User = Depends(require_user)) -> User:
        if user.role == UserRole.ADMIN:
            return user
        if user.role not in allowed:
            raise HTTPException(status_code=403, detail="Accès refusé")
        return user
    return _dep


def can_edit(user: User, area: str) -> bool:
    """Permission d'écriture par zone fonctionnelle."""
    if user.role == UserRole.ADMIN:
        return True
    if user.role == UserRole.VIEWER:
        return False
    if area in ("chantier", "client", "contact", "devis", "intervention"):
        return user.role == UserRole.MANAGER
    if area in ("facture", "paiement"):
        return user.role in (UserRole.MANAGER, UserRole.ACCOUNTANT)
    if area == "depense":
        return user.role in (UserRole.MANAGER, UserRole.ACCOUNTANT, UserRole.WORKER)
    if area in ("heure", "document"):
        return user.role in (UserRole.MANAGER, UserRole.WORKER, UserRole.ACCOUNTANT)
    if area == "admin":
        return False  # seul ADMIN passe en haut
    return False


def can_view(user: User, area: str) -> bool:
    if user.role == UserRole.ADMIN:
        return True
    # Lecture large : tous les rôles voient l'essentiel
    if area == "admin":
        return False
    if area == "facture" and user.role == UserRole.WORKER:
        return False  # ouvrier ne voit pas les factures
    if area == "depense" and user.role == UserRole.WORKER:
        return False  # ouvrier ne voit que ses propres dépenses (filtré au niveau route)
    return True


class AuthGuard:
    """Middleware de redirection : si non-loggé → /login (sauf routes publiques)."""

    PUBLIC_PREFIXES = ("/login", "/static", "/health")

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        path = scope["path"]
        if any(path.startswith(p) for p in self.PUBLIC_PREFIXES):
            await self.app(scope, receive, send)
            return
        # Vérifie session
        # Note : SessionMiddleware doit avoir tourné avant — d'où l'ordre dans main.py
        session = scope.get("session") or {}
        if not session.get("user_id"):
            # redirige
            response = RedirectResponse(url=f"/login?next={path}")
            await response(scope, receive, send)
            return
        await self.app(scope, receive, send)
